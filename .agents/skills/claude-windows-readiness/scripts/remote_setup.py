"""Opt-in Debian/Ubuntu deployment bundles with retained, independent recovery.

Plan/export are portable and offline. Apply operates only on its actual Linux
target; there is deliberately no SSH remote-execution option. The exported and
retained worker is self-contained Python 3.9+ and needs neither this app nor an
online Agent to expire an unconfirmed transaction.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

COMMANDS = ('remote-plan', 'remote-export', 'remote-apply', 'remote-confirm', 'remote-rollback', 'remote-status')
MUTATING_COMMANDS = ('remote-apply', 'remote-confirm', 'remote-rollback')
SCHEMA = 'clearpath-remote-plan/1'
STATE_SCHEMA = 'clearpath-remote-state/1'
MAX_JSON = 1024 * 1024
MAX_BINARY = 128 * 1024 * 1024
MODULES = ('core', 'ssh', 'reverse_tunnel', 'watchdog', 'inbound_guard')


class RemoteError(Exception):
    pass


def need(value, code):
    if not value:
        raise RemoteError(code)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value)).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'REMOTE_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def loads(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=lambda unused: (_ for _ in ()).throw(RemoteError('REMOTE_INVALID_JSON_NUMBER')))
    except (UnicodeError, ValueError, RecursionError):
        raise RemoteError('REMOTE_INVALID_JSON') from None


def _path(value):
    need(type(value) is str and value.startswith('/') and len(value) <= 4096 and
         '\\' not in value and not any(ord(c) < 32 for c in value), 'REMOTE_ABSOLUTE_PATH_REQUIRED')
    p = PurePosixPath(value)
    need(str(p) == value and '..' not in p.parts and p != PurePosixPath('/'), 'REMOTE_PATH_INVALID')
    return value


def _word(value):
    need(type(value) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,23}', value), 'REMOTE_IDENTIFIER_INVALID')
    return value


def _hash(value):
    need(type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value), 'REMOTE_SHA256_REQUIRED')
    return value


def _port(value):
    need(type(value) is int and 1 <= value <= 65535, 'REMOTE_PORT_INVALID')
    return value


def _host(value):
    need(type(value) is str and len(value) <= 253 and
         re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', value), 'REMOTE_SSH_HOST_INVALID')
    return value


def _unit_arg(value):
    need(type(value) is str and not any(x in value for x in ('\n', '\r', '\x00')), 'REMOTE_UNIT_ARGUMENT_INVALID')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def _shape(value, fields, code):
    need(type(value) is dict and not set(value) - set(fields), code)


def validate_input(value):
    _shape(value, ('schema', 'scope', 'platform', 'distribution', 'modules', 'fuse_seconds', 'trusted_python',
                   'core', 'ssh', 'reverse_tunnel', 'watchdog', 'inbound_guard', 'expected_files', 'expected_services', 'expected_inbound_sha256'), 'REMOTE_INPUT_SHAPE')
    need(value.get('schema') == 'clearpath-remote-input/1' and value.get('platform') == 'linux', 'REMOTE_INPUT_SCHEMA')
    scope = _word(value.get('scope'))
    need(value.get('distribution') in ('debian', 'ubuntu'), 'REMOTE_DISTRIBUTION_UNSUPPORTED')
    selected = value.get('modules')
    need(type(selected) is list and selected and len(selected) <= len(MODULES) and
         all(type(x) is str and x in MODULES for x in selected) and len(set(selected)) == len(selected), 'REMOTE_MODULE_SELECTION_REQUIRED')
    seconds = value.get('fuse_seconds', 180)
    need(type(seconds) is int and 60 <= seconds <= 600, 'REMOTE_FUSE_RANGE')
    result = {'schema': value['schema'], 'platform': 'linux', 'scope': scope, 'distribution': value['distribution'],
              'modules': [x for x in MODULES if x in selected], 'fuse_seconds': seconds,
              'trusted_python': _path(value.get('trusted_python', '/usr/bin/python3'))}
    prefix = 'clearpath-remote-' + scope
    if 'core' in selected:
        item = value.get('core')
        _shape(item, ('source', 'configuration_file', 'configuration_sha256', 'tun_interface', 'route_table'), 'REMOTE_CORE_SHAPE')
        source = item.get('source')
        _shape(source, ('kind', 'path', 'url', 'sha256', 'binary_sha256', 'compression'), 'REMOTE_CORE_SOURCE_SHAPE')
        need(source.get('kind') in ('existing', 'https'), 'REMOTE_CORE_SOURCE_REQUIRED')
        source = dict(source)
        _hash(source.get('sha256'))
        if source['kind'] == 'existing':
            need(set(source) == {'kind', 'path', 'sha256'}, 'REMOTE_EXISTING_CORE_SHAPE')
            source['path'] = _path(source['path'])
        else:
            need(set(source) == {'kind', 'url', 'sha256', 'binary_sha256', 'compression'}, 'REMOTE_DOWNLOAD_CORE_SHAPE')
            _hash(source['binary_sha256'])
            parsed = urllib.parse.urlsplit(source.get('url', ''))
            need(parsed.scheme == 'https' and parsed.hostname and parsed.port in (None, 443) and
                 not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and
                 len(source['url']) <= 2048 and not any(ord(x) < 33 for x in source['url']), 'REMOTE_TRUSTED_HTTPS_SOURCE_REQUIRED')
            need(source['compression'] in ('none', 'gzip'), 'REMOTE_CORE_COMPRESSION_UNSUPPORTED')
        interface = item.get('tun_interface')
        need(type(interface) is str and re.fullmatch(r'cp[a-z0-9_-]{1,12}', interface), 'REMOTE_OWNED_TUN_NAME_REQUIRED')
        table = item.get('route_table')
        need(type(table) is int and 20000 <= table <= 60000, 'REMOTE_DEDICATED_ROUTE_TABLE_REQUIRED')
        result['core'] = {'source': source, 'configuration_file': _path(item.get('configuration_file')),
                          'configuration_sha256': _hash(item.get('configuration_sha256')), 'tun_interface': interface, 'route_table': table}
    if 'ssh' in selected:
        item = value.get('ssh')
        _shape(item, ('port', 'password_authentication', 'permit_root_login', 'allow_users', 'validation_contexts', 'activation'), 'REMOTE_SSH_SHAPE')
        need(item.get('activation') == 'restart', 'REMOTE_EXPLICIT_SSH_RESTART_PLAN_REQUIRED')
        need(type(item.get('password_authentication')) is bool and item.get('permit_root_login') in ('no', 'prohibit-password'), 'REMOTE_SSH_AUTHENTICATION_EXPLICIT_REQUIRED')
        users = item.get('allow_users')
        need(type(users) is list and 1 <= len(users) <= 16 and len(set(users)) == len(users), 'REMOTE_SSH_USERS_REQUIRED')
        for user in users:
            need(type(user) is str and re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', user), 'REMOTE_SSH_USER_INVALID')
        contexts = item.get('validation_contexts', [])
        need(type(contexts) is list and len(contexts) <= 16, 'REMOTE_SSH_CONTEXT_BUDGET')
        for context in contexts:
            need(type(context) is dict and set(context) == {'user', 'host', 'address', 'local_address', 'local_port'} and
                 context['user'] in users and context['local_port'] == item['port'], 'REMOTE_SSH_CONTEXT_INVALID')
            _host(context['host'])
            for address in ('address', 'local_address'):
                try:
                    need(type(context[address]) is str, 'REMOTE_SSH_CONTEXT_INVALID')
                    ipaddress.ip_address(context[address])
                except ValueError:
                    raise RemoteError('REMOTE_SSH_CONTEXT_INVALID') from None
        result['ssh'] = {'port': _port(item.get('port')), 'password_authentication': item['password_authentication'],
                         'permit_root_login': item['permit_root_login'], 'allow_users': users, 'validation_contexts': contexts,
                         'activation': 'restart'}
    if 'reverse_tunnel' in selected:
        item = value.get('reverse_tunnel')
        _shape(item, ('user', 'host', 'port', 'remote_user', 'remote_bind_port', 'local_port', 'identity_file', 'known_hosts'), 'REMOTE_TUNNEL_SHAPE')
        for key in ('user', 'remote_user'):
            need(type(item.get(key)) is str and re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', item[key]), 'REMOTE_TUNNEL_USER_INVALID')
        result['reverse_tunnel'] = dict(item, host=_host(item.get('host')), port=_port(item.get('port')),
                                        remote_bind_port=_port(item.get('remote_bind_port')), local_port=_port(item.get('local_port')),
                                        identity_file=_path(item.get('identity_file')), known_hosts=_path(item.get('known_hosts')))
    if 'watchdog' in selected:
        need('core' in selected, 'REMOTE_WATCHDOG_REQUIRES_OWNED_CORE')
        item = value.get('watchdog', {})
        _shape(item, ('interval_seconds',), 'REMOTE_WATCHDOG_SHAPE')
        interval = item.get('interval_seconds', 30)
        need(type(interval) is int and 15 <= interval <= 300, 'REMOTE_WATCHDOG_INTERVAL_INVALID')
        result['watchdog'] = {'interval_seconds': interval}
    if 'inbound_guard' in selected:
        item = value.get('inbound_guard')
        _shape(item, ('management_networks', 'tcp_ports'), 'REMOTE_INBOUND_SHAPE')
        networks, ports = item.get('management_networks'), item.get('tcp_ports')
        need(type(networks) is list and 1 <= len(networks) <= 32 and type(ports) is list and 1 <= len(ports) <= 32, 'REMOTE_INBOUND_MANAGEMENT_REQUIRED')
        normalized = []
        for value_net in networks:
            try:
                net = ipaddress.ip_network(value_net, strict=True)
            except (ValueError, TypeError):
                raise RemoteError('REMOTE_MANAGEMENT_NETWORK_INVALID') from None
            need(net.prefixlen > 0 and not net.is_multicast, 'REMOTE_MANAGEMENT_NETWORK_UNBOUNDED')
            normalized.append(str(net))
        result['inbound_guard'] = {'management_networks': sorted(set(normalized)), 'tcp_ports': sorted(set(_port(x) for x in ports))}
        if 'ssh' in selected:
            need(result['ssh']['port'] in result['inbound_guard']['tcp_ports'], 'REMOTE_SSH_PORT_NOT_ALLOWED')
    for key in MODULES:
        need(key in selected or key not in value, 'REMOTE_UNSELECTED_MODULE_PARAMETERS')
    files = value.get('expected_files', {})
    services = value.get('expected_services', {})
    need(type(files) is dict and len(files) <= 32 and type(services) is dict and len(services) <= 16, 'REMOTE_BASELINE_SHAPE')
    for path, fingerprint in files.items():
        _path(path)
        need(fingerprint is None or (type(fingerprint) is str and re.fullmatch(r'[a-f0-9]{64}', fingerprint)), 'REMOTE_BASELINE_FILE_HASH')
    for name, status in services.items():
        need(type(name) is str and name.startswith(prefix + '-') and name.endswith(('.service', '.timer')) and
             type(status) is dict and set(status) == {'active', 'enabled'} and
             status['active'] in ('active', 'inactive', 'failed') and status['enabled'] in ('enabled', 'disabled', 'static', 'not-found'), 'REMOTE_BASELINE_SERVICE_INVALID')
    result['expected_files'], result['expected_services'] = files, services
    inbound_hash = value.get('expected_inbound_sha256')
    need(inbound_hash is None or (type(inbound_hash) is str and re.fullmatch(r'[a-f0-9]{64}', inbound_hash)), 'REMOTE_BASELINE_INBOUND_HASH')
    result['expected_inbound_sha256'] = inbound_hash
    return result


def _paths(spec):
    scope = spec['scope']
    return {'state': '/var/lib/clearpath/remote/' + scope, 'config': '/etc/clearpath/' + scope + '/mihomo.json',
            'binary': '/usr/local/lib/clearpath/' + scope + '/mihomo', 'prefix': 'clearpath-remote-' + scope,
            'ssh': '/etc/ssh/sshd_config.d/90-clearpath-' + scope + '.conf', 'table': 'clearpath_remote_' + scope.replace('-', '_')}


def _service(spec, module):
    return _paths(spec)['prefix'] + '-' + module.replace('_', '-') + '.service'


def _services(spec):
    result = []
    for module in ('core', 'reverse_tunnel'):
        if module in spec['modules']:
            result.append(_service(spec, module))
    if 'watchdog' in spec['modules']:
        result += [_service(spec, 'watchdog'), _service(spec, 'watchdog').replace('.service', '.timer')]
    if 'inbound_guard' in spec['modules']:
        result.append(_service(spec, 'inbound_guard'))
    return result


def render_files(spec):
    """Own only namespaced files; sensitive input bytes are bound at target preflight."""
    p = _paths(spec)
    worker = p['state'] + '/worker.py'
    python = spec['trusted_python']
    result = {}
    def unit(name, value):
        result['/etc/systemd/system/' + name] = {'text': value, 'mode': 0o644}
    if 'core' in spec['modules']:
        args = ' '.join(_unit_arg(x) for x in (p['binary'], '-d', p['state'] + '/core-data', '-f', p['config']))
        unit(_service(spec, 'core'), '[Unit]\nDescription=Clearpath owned Mihomo TUN\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=simple\nExecStart=' + args + '\nRestart=on-failure\nRestartSec=3s\nUMask=0077\n[Install]\nWantedBy=multi-user.target\n')
    if 'ssh' in spec['modules']:
        item = spec['ssh']
        result[p['ssh']] = {'text': 'Port %d\nPasswordAuthentication %s\nPermitRootLogin %s\nAllowUsers %s\n' %
                           (item['port'], 'yes' if item['password_authentication'] else 'no', item['permit_root_login'], ' '.join(item['allow_users'])), 'mode': 0o600}
    if 'reverse_tunnel' in spec['modules']:
        item = spec['reverse_tunnel']
        args = ['/usr/bin/ssh', '-F', '/dev/null', '-N', '-T', '-oBatchMode=yes', '-oIdentitiesOnly=yes',
                '-oIdentityAgent=none', '-oProxyCommand=none', '-oProxyJump=none', '-oControlMaster=no',
                '-oControlPath=none', '-oControlPersist=no', '-oGlobalKnownHostsFile=/dev/null',
                '-oExitOnForwardFailure=yes', '-oStrictHostKeyChecking=yes',
                '-oUserKnownHostsFile=' + item['known_hosts'], '-oServerAliveInterval=30', '-oServerAliveCountMax=3',
                '-i', item['identity_file'], '-p', str(item['port']), '-R',
                '127.0.0.1:%d:127.0.0.1:%d' % (item['remote_bind_port'], item['local_port']), item['remote_user'] + '@' + item['host']]
        unit(_service(spec, 'reverse_tunnel'), '[Unit]\nDescription=Clearpath loopback reverse management tunnel\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=simple\nUser=' + item['user'] + '\nUnsetEnvironment=SSH_AUTH_SOCK SSH_AGENT_PID\nExecStart=' + ' '.join(_unit_arg(x) for x in args) + '\nRestart=on-failure\nRestartSec=5s\nUMask=0077\n[Install]\nWantedBy=multi-user.target\n')
    if 'watchdog' in spec['modules']:
        unit(_service(spec, 'watchdog'), '[Unit]\nDescription=Clearpath scoped failed-core recovery\n[Service]\nType=oneshot\nExecStart=' + ' '.join(_unit_arg(x) for x in (python, '-I', worker, '_watchdog', p['state'])) + '\n')
        unit(_service(spec, 'watchdog').replace('.service', '.timer'), '[Unit]\nDescription=Clearpath owned-core watchdog timer\n[Timer]\nOnBootSec=30s\nOnUnitActiveSec=%ds\n[Install]\nWantedBy=timers.target\n' % spec['watchdog']['interval_seconds'])
    if 'inbound_guard' in spec['modules']:
        unit(_service(spec, 'inbound_guard'), '[Unit]\nDescription=Clearpath owned inbound firewall\nAfter=local-fs.target\nBefore=network-pre.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=' + ' '.join(_unit_arg(x) for x in (python, '-I', worker, '_inbound', p['state'])) + '\n[Install]\nWantedBy=multi-user.target\n')
    need(set(spec['expected_files']) <= set(result) | ({p['binary'], p['config']} if 'core' in spec['modules'] else set()), 'REMOTE_BASELINE_OUTSIDE_OWNED_FILES')
    need(set(spec['expected_services']) <= set(_services(spec)), 'REMOTE_BASELINE_OUTSIDE_OWNED_SERVICES')
    return result


def make_plan(value):
    spec = validate_input(value)
    files = render_files(spec)
    return {'schema': SCHEMA, 'created_at': stamp(), 'spec': spec, 'files': files,
            'requires_network': bool('core' in spec['modules'] or 'reverse_tunnel' in spec['modules']),
            'requires_second_session': bool('ssh' in spec['modules'] or 'inbound_guard' in spec['modules']),
            'requires_persist': bool('ssh' in spec['modules'] or any(x['enabled'] == 'enabled' for x in spec['expected_services'].values())),
            'requires_customer_terminal': 'ssh' in spec['modules'],
            'ssh_adoption': 'restart_current_reviewed_unit_and_defaults' if 'ssh' in spec['modules'] else 'not_selected',
            'network_verified': False, 'authorization_saved': False}


def validate_plan(value):
    need(type(value) is dict and set(value) == {'schema', 'created_at', 'spec', 'files', 'requires_network', 'requires_second_session', 'requires_persist',
         'requires_customer_terminal', 'ssh_adoption', 'network_verified', 'authorization_saved'} and value.get('schema') == SCHEMA, 'REMOTE_PLAN_SCHEMA')
    fresh = make_plan(value['spec'])
    for key in fresh:
        if key != 'created_at':
            need(fresh[key] == value[key], 'REMOTE_PLAN_RECOMPILE_MISMATCH')
    return value


def _safe_read(path, maximum=MAX_JSON, owner=None):
    p = Path(path)
    need(p.is_absolute(), 'REMOTE_ABSOLUTE_PATH_REQUIRED')
    if os.name == 'nt':
        import ctypes
        need(p.drive and not p.drive.startswith(('\\\\', '//')), 'REMOTE_LOCAL_INPUT_REQUIRED')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        kernel.GetDriveTypeW.restype = ctypes.c_uint
        need(kernel.GetDriveTypeW(p.anchor) == 3, 'REMOTE_LOCAL_FIXED_DRIVE_REQUIRED')
    for part in (p, *p.parents):
        need(not part.is_symlink(), 'REMOTE_SYMLINK_REJECTED')
    before = p.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum, 'REMOTE_REGULAR_INPUT_REQUIRED')
    if owner is not None:
        need(before.st_uid == owner and not before.st_mode & 0o022, 'REMOTE_TRUSTED_FILE_REQUIRED')
    fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        opened = os.fstat(fd)
        need((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'REMOTE_INPUT_CHANGED')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    shape = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    final = p.lstat()
    if os.name == 'nt':
        # Windows path stat may expose birth time while fstat exposes change
        # time; compare those clock domains within their own APIs.
        common = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        stable = common(before) == common(opened) == common(after) == common(final)
        stable &= before.st_ctime_ns == final.st_ctime_ns and opened.st_ctime_ns == after.st_ctime_ns
    else:
        stable = shape(before) == shape(after) == shape(final)
    need(stable and len(raw) <= maximum, 'REMOTE_INPUT_CHANGED')
    return raw


def _sync(folder):
    if os.name == 'nt':
        return  # Portable export only; Linux native transactions fsync dirs.
    fd = os.open(folder, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_new(path, data, mode=0o600):
    p = Path(path)
    need(not p.is_symlink() and p.parent.is_dir() and not p.parent.is_symlink(), 'REMOTE_OUTPUT_PATH_UNSAFE')
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(p, mode)
    _sync(p.parent)


def _save(path, value):
    p = Path(path)
    # A hard interruption may leave an old stage behind. Each subsequent save
    # uses a new owned object; never overwrite or delete an orphan implicitly.
    staged = p.with_name(p.name + '.next-' + uuid.uuid4().hex)
    _write_new(staged, encoded(value))
    os.replace(staged, p)
    _sync(p.parent)


@contextmanager
def operation_lock(folder):
    import fcntl
    path = Path(folder) / '.operation.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'REMOTE_LOCK_UNSAFE')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def export_bundle(plan, pin, output):
    validate_plan(plan)
    need(digest(encoded(plan)) == pin, 'REMOTE_PLAN_DIGEST_MISMATCH')
    out = Path(output)
    need(out.is_absolute() and not out.exists() and not out.is_symlink() and out.parent.is_dir(), 'REMOTE_NEW_PRIVATE_BUNDLE_REQUIRED')
    for item in out.parents:
        need(not item.is_symlink(), 'REMOTE_BUNDLE_PARENT_SYMLINK')
    if os.name == 'nt':
        # Reuse the shipped native ACL helper rather than equating chmod(0700)
        # with a private Windows DACL. The retained Linux worker never needs it.
        try:
            import config_recovery
            from types import SimpleNamespace
        except ImportError:
            raise RemoteError('REMOTE_WINDOWS_PRIVATE_BUNDLE_HELPER_UNAVAILABLE') from None
        config_recovery._private_dir(SimpleNamespace(SetupError=RemoteError, require=need), out, create=True)
    else:
        out.mkdir(mode=0o700)
    plan_raw, runtime = encoded(plan), Path(__file__).read_bytes()
    _write_new(out / 'plan.private.json', plan_raw)
    _write_new(out / 'remote_setup.py', runtime)
    manifest = {'schema': 'clearpath-remote-bundle/1', 'plan_sha256': pin,
                'files': {'plan.private.json': digest(plan_raw), 'remote_setup.py': digest(runtime)}}
    raw = encoded(manifest)
    _write_new(out / 'bundle.json', raw)
    return {'status': 'bundle_exported', 'exit_code': 0, 'bundle_sha256': digest(raw),
            'plan_sha256': pin, 'network_requests': 0, 'system_changes_performed': False}


def read_bundle(folder, pin):
    _hash(pin)
    folder = Path(folder)
    raw = _safe_read(folder / 'bundle.json')
    need(digest(raw) == pin, 'REMOTE_BUNDLE_DIGEST_MISMATCH')
    manifest = loads(raw)
    need(type(manifest) is dict and set(manifest) == {'schema', 'plan_sha256', 'files'} and
         manifest['schema'] == 'clearpath-remote-bundle/1' and
         set(manifest['files']) == {'plan.private.json', 'remote_setup.py'}, 'REMOTE_BUNDLE_INVALID')
    files = {name: _safe_read(folder / name, 4 * 1024 * 1024) for name in manifest['files']}
    need(all(digest(raw_file) == manifest['files'][name] for name, raw_file in files.items()), 'REMOTE_BUNDLE_FILE_CHANGED')
    plan = validate_plan(loads(files['plan.private.json']))
    need(manifest['plan_sha256'] == digest(files['plan.private.json']), 'REMOTE_BUNDLE_PLAN_CHANGED')
    # Exporting a bundle never grants authority to another modified worker.
    need(files['remote_setup.py'] == Path(__file__).read_bytes(), 'REMOTE_WORKER_VERSION_MISMATCH')
    return folder, manifest, plan, files['remote_setup.py']


def _canonical_nft(document):
    def clean(value):
        if isinstance(value, list):
            return [clean(x) for x in value if not (type(x) is dict and 'metainfo' in x)]
        if isinstance(value, dict):
            if set(value) == {'add'}:
                return clean(value['add'])
            return {k: clean(v) for k, v in value.items() if k not in ('handle', 'index', 'packets', 'bytes')}
        return value
    return clean(document)


def inbound_document(spec):
    table = _paths(spec)['table']
    commands = [{'add': {'table': {'family': 'inet', 'name': table}}},
                {'add': {'chain': {'family': 'inet', 'table': table, 'name': 'input', 'type': 'filter',
                                   'hook': 'input', 'prio': 10, 'policy': 'drop'}}}]
    def rule(expr):
        commands.append({'add': {'rule': {'family': 'inet', 'table': table, 'chain': 'input', 'expr': expr + [{'accept': None}]}}})
    rule([{'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'lo'}}])
    rule([{'match': {'op': 'in', 'left': {'ct': {'key': 'state'}}, 'right': {'set': ['established', 'related']}}}])
    rule([{'match': {'op': '==', 'left': {'meta': {'key': 'nfproto'}}, 'right': 'ipv4'}},
          {'match': {'op': '==', 'left': {'meta': {'key': 'l4proto'}}, 'right': 'udp'}},
          {'match': {'op': '==', 'left': {'payload': {'protocol': 'udp', 'field': 'sport'}}, 'right': 67}},
          {'match': {'op': '==', 'left': {'payload': {'protocol': 'udp', 'field': 'dport'}}, 'right': 68}}])
    rule([{'match': {'op': '==', 'left': {'meta': {'key': 'l4proto'}}, 'right': 'ipv6-icmp'}},
          {'match': {'op': 'in', 'left': {'payload': {'protocol': 'icmpv6', 'field': 'type'}}, 'right': {'set': [133, 134, 135, 136]}}}])
    for network in spec['inbound_guard']['management_networks']:
        net = ipaddress.ip_network(network)
        rule([{'match': {'op': '==', 'left': {'payload': {'protocol': 'ip' if net.version == 4 else 'ip6', 'field': 'saddr'}},
                           'right': {'prefix': {'addr': str(net.network_address), 'len': net.prefixlen}}}},
              {'match': {'op': '==', 'left': {'meta': {'key': 'l4proto'}}, 'right': 'tcp'}},
              {'match': {'op': 'in', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}},
                           'right': {'set': spec['inbound_guard']['tcp_ports']}}}])
    return {'nftables': commands}


class NativeHost:
    def __init__(self, spec, runner=None, fetcher=None):
        self.spec = spec
        self.runner = runner or subprocess.run
        self.fetcher = fetcher or self.download
        self.owner = 0

    def path(self, value):
        return Path(value)

    def root(self):
        return self.path(_paths(self.spec)['state'])

    def command(self, argv, data=None, allowed=(0,)):
        try:
            result = self.runner(argv, input=data, text=True, capture_output=True, timeout=15,
                                 check=False, shell=False, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        except (OSError, subprocess.SubprocessError):
            raise RemoteError('REMOTE_NATIVE_COMMAND_FAILED') from None
        need(len(result.stdout) <= 2 * 1024 * 1024 and len(result.stderr) <= 2 * 1024 * 1024, 'REMOTE_NATIVE_OUTPUT_BUDGET')
        need(result.returncode in allowed, 'REMOTE_NATIVE_COMMAND_FAILED')
        return result.stdout.strip()

    def _trusted(self, path, missing=False, allowed_owner=None):
        path = Path(path)
        need(path.is_absolute(), 'REMOTE_NATIVE_ABSOLUTE_PATH_REQUIRED')
        for entry in reversed((path, *path.parents)):
            if not entry.exists():
                need(missing and not entry.is_symlink(), 'REMOTE_NATIVE_PATH_UNAVAILABLE')
                continue
            info = entry.lstat()
            need(not stat.S_ISLNK(info.st_mode) and info.st_uid in (self.owner, allowed_owner) and not info.st_mode & 0o022,
                 'REMOTE_NATIVE_PATH_UNTRUSTED')

    def check(self, folder=None):
        need(platform.system() == 'Linux' and os.geteuid() == 0, 'REMOTE_ACTUAL_LINUX_ROOT_REQUIRED')
        values = {}
        release = self.path('/etc/os-release').resolve(strict=True)
        self._trusted(release)
        for line in _safe_read(release, 65536, owner=self.owner).decode().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                values[key] = value.strip('"')
        need(values.get('ID') == self.spec['distribution'], 'REMOTE_TARGET_DISTRIBUTION_MISMATCH')
        need(self.path('/run/systemd/system').is_dir(), 'REMOTE_SYSTEMD_REQUIRED')
        need(folder is None or Path(folder) == self.root(), 'REMOTE_FIXED_STATE_DIRECTORY_REQUIRED')
        self._trusted(self.root(), missing=True)
        python = self.path(self.spec['trusted_python'])
        for ancestor in (python, *python.parents):
            info = ancestor.lstat()
            need(info.st_uid == self.owner and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022), 'REMOTE_TRUSTED_PYTHON_REQUIRED')
        resolved = python.resolve(strict=True)
        self._trusted(resolved)
        info = resolved.stat()
        need(stat.S_ISREG(info.st_mode) and info.st_mode & 0o111, 'REMOTE_TRUSTED_PYTHON_REQUIRED')
        self.command([str(python), '-I', '-c', 'import sys;raise SystemExit(0 if sys.version_info >= (3,9) else 2)'])

    def boot_id(self):
        return digest(_safe_read('/proc/sys/kernel/random/boot_id', 128))

    def machine_id(self):
        path = self.path('/etc/machine-id').resolve(strict=True)
        self._trusted(path)
        raw = _safe_read(path, 128, owner=self.owner).strip()
        need(re.fullmatch(rb'[a-f0-9]{32}', raw), 'REMOTE_STABLE_MACHINE_ID_UNAVAILABLE')
        return digest(raw)

    def prepare(self, runtime):
        self.check()
        root = self.root()
        need(not root.exists(), 'REMOTE_EXISTING_STATE_REQUIRES_STATUS_OR_ROLLBACK')
        root.mkdir(parents=True, mode=0o700)
        os.chmod(root, 0o700)
        for p in root.parents:
            if p.name in ('clearpath', 'remote'):
                os.chmod(p, 0o700)
        _write_new(root / 'worker.py', runtime)
        (root / 'before').mkdir(mode=0o700)
        (root / 'journal').mkdir(mode=0o700)

    def _file(self, logical):
        p = self.path(logical)
        self._trusted(p, missing=True)
        if not p.exists():
            return None
        raw = _safe_read(p, MAX_BINARY, owner=self.owner)
        info = p.lstat()
        need(not hasattr(os, 'listxattr') or not os.listxattr(p, follow_symlinks=False), 'REMOTE_OWNED_FILE_EXTENDED_METADATA_UNSUPPORTED')
        return {'sha256': digest(raw), 'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid,
                'device': info.st_dev, 'inode': info.st_ino, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns,
                'size': info.st_size}

    def _service_state(self, name):
        active = self.command(['/usr/bin/systemctl', 'is-active', name], allowed=(0, 3, 4))
        enabled = self.command(['/usr/bin/systemctl', 'is-enabled', name], allowed=(0, 1, 3, 4))
        need(active in ('active', 'inactive', 'failed', 'unknown', 'activating', 'deactivating', 'reloading') and
             enabled in ('enabled', 'disabled', 'static', 'not-found', ''), 'REMOTE_SERVICE_STATE_UNKNOWN')
        return {'active': 'inactive' if active == 'unknown' else active, 'enabled': enabled or 'not-found'}

    def _inbound(self):
        table = _paths(self.spec)['table']
        raw = loads(self.command(['/usr/sbin/nft', '-j', 'list', 'tables']).encode())
        present = any(x.get('table', {}).get('family') == 'inet' and x.get('table', {}).get('name') == table for x in raw.get('nftables', []))
        return _canonical_nft(loads(self.command(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', table]).encode())) if present else None

    def _tun(self):
        if 'core' not in self.spec['modules']:
            return None
        item = self.spec['core']
        links = loads(self.command(['/usr/sbin/ip', '-j', 'link', 'show']).encode())
        found = [x for x in links if x.get('ifname') == item['tun_interface']]
        routes = loads(self.command(['/usr/sbin/ip', '-j', 'route', 'show', 'table', str(item['route_table'])]).encode())
        return {'ifindex': found[0]['ifindex'] if len(found) == 1 else None, 'routes': routes}

    def wait_tun(self):
        for unused in range(10):
            tun = self._tun()
            if tun['ifindex'] is not None:
                return tun
            time.sleep(.5)
        raise RemoteError('REMOTE_OWNED_TUN_NOT_READY')

    def snapshot(self, file_names):
        return {'files': {name: self._file(name) for name in file_names},
                'services': {name: self._service_state(name) for name in _services(self.spec)},
                'inbound': self._inbound() if 'inbound_guard' in self.spec['modules'] else None,
                'tun': self._tun(),
                'shared_ssh': self._service_state('ssh.service') if 'ssh' in self.spec['modules'] else None}

    def customer_terminal_ready(self):
        return sys.stdin.isatty()

    def restart_ssh(self, state, recovery=False):
        need(recovery or self.customer_terminal_ready(), 'REMOTE_SSH_CUSTOMER_TERMINAL_REQUIRED')
        for key, source in self.ssh_startup_sources().items():
            need(source == state['sources'].get(key), 'REMOTE_SHARED_SSH_STARTUP_CHANGED')
        # This explicit plan resets the daemon to the currently reviewed unit;
        # HUP cannot establish which historical -f/-o argv a daemon retained.
        self.command(['/usr/bin/systemctl', 'restart', 'ssh.service'])
        self.command(['/usr/bin/systemctl', 'is-active', '--quiet', 'ssh.service'])

    def download(self, url):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *unused, **kwargs):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        initial_host = urllib.parse.urlsplit(url).hostname
        for _ in range(3):
            parsed = urllib.parse.urlsplit(url)
            allowed = {initial_host}
            if initial_host == 'github.com':
                allowed |= {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
            need(parsed.scheme == 'https' and parsed.hostname in allowed and not parsed.username and not parsed.password and parsed.port in (None, 443), 'REMOTE_DOWNLOAD_REDIRECT_REJECTED')
            try:
                response = opener.open(urllib.request.Request(url, headers={'User-Agent': 'Clearpath-Remote/1'}), timeout=20)
            except urllib.error.HTTPError as error:
                if error.code in (301, 302, 303, 307, 308) and error.headers.get('Location'):
                    url = urllib.parse.urljoin(url, error.headers['Location'])
                    continue
                raise RemoteError('REMOTE_CORE_DOWNLOAD_FAILED') from None
            with response:
                raw = response.read(MAX_BINARY + 1)
                need(len(raw) <= MAX_BINARY, 'REMOTE_CORE_DOWNLOAD_BUDGET')
                return raw
        raise RemoteError('REMOTE_DOWNLOAD_REDIRECT_LIMIT')

    def ssh_startup_sources(self):
        """Support only the distro's direct sshd service with empty option input."""
        def show(key):
            return self.command(['/usr/bin/systemctl', 'show', 'ssh.service', '--property=' + key, '--value'])
        raw = show('ExecStart')
        argv = re.findall(r'argv\[\]=(.*?)\s*;', raw)
        paths = re.findall(r'(?:^|[ {;])path=([^ ;]+)', raw)
        need(len(argv) == len(paths) == 1 and paths[0] == '/usr/sbin/sshd' and
             shlex.split(argv[0]) in (['/usr/sbin/sshd', '-D'], ['/usr/sbin/sshd', '-D', '$SSHD_OPTS']),
             'REMOTE_NONSTANDARD_SSH_EXECSTART_UNSUPPORTED')
        need(show('RootDirectory') == '' and show('RootImage') == '' and show('User') in ('', 'root'),
             'REMOTE_SSH_ALTERNATE_ROOT_OR_USER_UNSUPPORTED')
        need(show('DropInPaths') == '', 'REMOTE_CUSTOM_SSH_UNIT_DROPINS_UNSUPPORTED')
        fragment = show('FragmentPath')
        need(fragment in ('/lib/systemd/system/ssh.service', '/usr/lib/systemd/system/ssh.service'),
             'REMOTE_NONSTANDARD_SSH_SERVICE_UNSUPPORTED')
        source = self.path(fragment).resolve(strict=True)
        self._trusted(source)
        result = {'ssh_unit': {'path': str(source), 'sha256': digest(_safe_read(source, MAX_JSON, owner=self.owner))}}
        environment_files = show('EnvironmentFiles')
        need(environment_files in ('', '/etc/default/ssh (ignore_errors=yes)', '/etc/default/ssh (ignore_errors=no)'),
             'REMOTE_SSH_CUSTOM_ENVIRONMENT_UNSUPPORTED')
        empty_options_verified = False
        for token in shlex.split(show('Environment')):
            if token.startswith('SSHD_OPTS='):
                need(token == 'SSHD_OPTS=', 'REMOTE_SSH_NONEMPTY_OPTIONS_UNSUPPORTED')
                empty_options_verified = True
        defaults = self.path('/etc/default/ssh')
        if defaults.exists():
            self._trusted(defaults)
            raw_defaults = _safe_read(defaults, 65536, owner=self.owner)
            for line in raw_defaults.decode().splitlines():
                if re.match(r'^\s*(?:export\s+)?SSHD_OPTS\s*=', line):
                    value = line.split('=', 1)[1].split('#', 1)[0].strip()
                    need(value in ('', "''", '""'), 'REMOTE_SSH_NONEMPTY_OPTIONS_UNSUPPORTED')
                    empty_options_verified = True
            result['ssh_defaults'] = {'path': '/etc/default/ssh', 'sha256': digest(raw_defaults)}
        else:
            need(not defaults.is_symlink(), 'REMOTE_SSH_DEFAULTS_SYMLINK')
            result['ssh_defaults'] = {'path': '/etc/default/ssh', 'sha256': None}
        need('$SSHD_OPTS' not in argv[0] or empty_options_verified, 'REMOTE_SSH_OPTION_VALUE_UNVERIFIED')
        return result

    def account_uid(self, name):
        import pwd
        try:
            return pwd.getpwnam(name).pw_uid
        except KeyError:
            raise RemoteError('REMOTE_EXISTING_LOCAL_ACCOUNT_REQUIRED') from None

    def payload(self, allow_network):
        payload = {name: {'raw': item['text'].encode(), 'mode': item['mode']} for name, item in render_files(self.spec).items()}
        sources = {}
        p = _paths(self.spec)
        if 'core' in self.spec['modules']:
            item, source = self.spec['core'], self.spec['core']['source']
            if source['kind'] == 'existing':
                self._trusted(self.path(source['path']))
                binary = _safe_read(self.path(source['path']), MAX_BINARY, owner=self.owner)
                need(digest(binary) == source['sha256'], 'REMOTE_EXISTING_CORE_HASH_MISMATCH')
            else:
                need(allow_network, 'REMOTE_NETWORK_PERMISSION_REQUIRED')
                downloaded = self.fetcher(source['url'])
                need(type(downloaded) is bytes and len(downloaded) <= MAX_BINARY and digest(downloaded) == source['sha256'], 'REMOTE_CORE_DOWNLOAD_HASH_MISMATCH')
                if source['compression'] == 'gzip':
                    import io
                    with gzip.GzipFile(fileobj=io.BytesIO(downloaded)) as stream:
                        binary = stream.read(MAX_BINARY + 1)
                else:
                    binary = downloaded
                need(len(binary) <= MAX_BINARY and digest(binary) == source['binary_sha256'], 'REMOTE_CORE_BINARY_HASH_MISMATCH')
            need(binary.startswith(b'\x7fELF'), 'REMOTE_LINUX_ELF_CORE_REQUIRED')
            config = _safe_read(self.path(item['configuration_file']), 4 * 1024 * 1024)
            need(digest(config) == item['configuration_sha256'], 'REMOTE_CONFIGURATION_HASH_MISMATCH')
            parsed = loads(config)
            tun = parsed.get('tun', {}) if type(parsed) is dict else {}
            need(tun.get('enable') is True and tun.get('auto-route') is True and
                 tun.get('device') == item['tun_interface'] and tun.get('iproute2-table-index') == item['route_table'], 'REMOTE_EXPLICIT_JSON_TUN_CONFIGURATION_REQUIRED')
            payload[p['binary']] = {'raw': binary, 'mode': 0o755}
            payload[p['config']] = {'raw': config, 'mode': 0o600}
            sources['configuration'] = {'path': item['configuration_file'], 'sha256': digest(config)}
        if 'reverse_tunnel' in self.spec['modules']:
            item = self.spec['reverse_tunnel']
            uid = self.account_uid(item['user'])
            for key in ('identity_file', 'known_hosts'):
                path = self.path(item[key])
                self._trusted(path, allowed_owner=uid)
                raw = _safe_read(path, 1024 * 1024)
                info = path.stat()
                need(info.st_uid in (self.owner, uid) and
                     (key != 'identity_file' or (info.st_uid == uid and info.st_mode & 0o400 and not info.st_mode & 0o077)) and
                     (key != 'known_hosts' or info.st_uid == uid or bool(info.st_mode & 0o004)), 'REMOTE_TUNNEL_KEY_PERMISSION')
                sources[key] = {'path': item[key], 'sha256': digest(raw)}
        if 'ssh' in self.spec['modules']:
            need(self.customer_terminal_ready(), 'REMOTE_SSH_CUSTOMER_TERMINAL_REQUIRED')
            for name in self.spec['ssh']['allow_users']:
                self.account_uid(name)
            need(any(name != 'root' or self.spec['ssh']['permit_root_login'] != 'no' for name in self.spec['ssh']['allow_users']),
                 'REMOTE_SSH_NO_LOGIN_USER_LEFT')
            main = _safe_read(self.path('/etc/ssh/sshd_config'), 1024 * 1024, owner=self.owner).decode()
            need(any(re.fullmatch(r'\s*Include\s+/etc/ssh/sshd_config\.d/\*\.conf\s*', line, re.I) for line in main.splitlines()), 'REMOTE_SSH_DROPIN_INCLUDE_REQUIRED')
            need(self._service_state('ssh.service')['active'] == 'active', 'REMOTE_EXISTING_SSH_SERVICE_REQUIRED')
            socket = self._service_state('ssh.socket')
            need(socket['active'] not in ('active', 'activating') and socket['enabled'] not in ('enabled', 'enabled-runtime'),
                 'REMOTE_SSH_SOCKET_ACTIVATION_UNSUPPORTED')
            sources.update(self.ssh_startup_sources())
            contents = [main]
            directory = self.path('/etc/ssh/sshd_config.d')
            self._trusted(directory)
            with os.scandir(directory) as iterator:
                count = 0
                for entry in iterator:
                    count += 1
                    need(count <= 64, 'REMOTE_SSH_DROPIN_BUDGET')
                    if entry.name.endswith('.conf'):
                        contents.append(_safe_read(Path(entry.path), 256 * 1024, owner=self.owner).decode())
            conditional = any(re.search(r'(?mi)^\s*Match\s+', text) for text in contents)
            conditional |= any(re.search(r'(?mi)^\s*Include\s+(?!/etc/ssh/sshd_config\.d/\*\.conf\s*$)', text) for text in contents)
            if conditional:
                need(set(x['user'] for x in self.spec['ssh']['validation_contexts']) == set(self.spec['ssh']['allow_users']),
                     'REMOTE_SSH_MATCH_CONTEXTS_REQUIRED')
            self.command(['/usr/sbin/sshd', '-t'])
            sources['sshd_config'] = {'path': '/etc/ssh/sshd_config', 'sha256': digest(main.encode())}
        return payload, sources

    def arm(self, state):
        root, prefix = self.root(), _paths(self.spec)['prefix'] + '-recovery'
        challenge = uuid.uuid4().hex
        state['handshake_challenge'] = challenge
        _save(root / 'state.json', state)
        raw_reply = self.command([self.spec['trusted_python'], '-I', str(root / 'worker.py'), '_handshake', str(root), challenge])
        reply = loads(raw_reply.encode())
        need(reply == {'status': 'recovery_worker_ready', 'challenge': challenge,
                       'plan_sha256': state['plan_sha256'], 'worker_sha256': state['worker_sha256'],
                       'binding': state['binding']}, 'REMOTE_INDEPENDENT_WORKER_HANDSHAKE_FAILED')
        service = '[Unit]\nDescription=Clearpath unconfirmed remote deployment recovery\n[Service]\nType=oneshot\nExecStart=' + ' '.join(_unit_arg(x) for x in (self.spec['trusted_python'], '-I', str(root / 'worker.py'), '_expire', str(root))) + '\n'
        timer = '[Unit]\nDescription=Clearpath pending deployment fuse\n[Timer]\nOnBootSec=5s\nOnUnitActiveSec=5s\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n'
        before_units = 'ssh.service sshd.service ' + ' '.join(_services(self.spec))
        boot_service = '[Unit]\nDescription=Clearpath boot rollback before affected services\nDefaultDependencies=no\nAfter=local-fs.target\nBefore=' + before_units + '\n[Service]\nType=oneshot\nExecStart=' + ' '.join(_unit_arg(x) for x in (self.spec['trusted_python'], '-I', str(root / 'worker.py'), '_expire', str(root))) + '\n[Install]\nWantedBy=multi-user.target\n'
        candidates = {'/etc/systemd/system/' + name: text for name, text in
                      ((prefix + '.service', service), (prefix + '.timer', timer), (prefix + '-boot.service', boot_service))}
        state['fuse_files'] = {name: digest(text.encode()) for name, text in candidates.items()}
        state['fuse_enable_attempts'] = []
        _save(root / 'state.json', state)
        for logical, text in candidates.items():
            target = self.path(logical)
            self._trusted(target, missing=True)
            need(not target.exists() and not target.is_symlink(), 'REMOTE_EXISTING_RECOVERY_UNIT_CONFLICT')
            _write_new(target, text.encode(), 0o644)
        self.command(['/usr/bin/systemctl', 'daemon-reload'])
        state['fuse_enable_attempts'].append(prefix + '-boot.service')
        _save(root / 'state.json', state)
        self.command(['/usr/bin/systemctl', 'enable', prefix + '-boot.service'])
        self.command(['/usr/bin/systemctl', 'is-enabled', '--quiet', prefix + '-boot.service'])
        state['fuse_enable_attempts'].append(prefix + '.timer')
        _save(root / 'state.json', state)
        self.command(['/usr/bin/systemctl', 'enable', '--now', prefix + '.timer'])
        self.command(['/usr/bin/systemctl', 'is-active', '--quiet', prefix + '.timer'])

    def disarm(self, state):
        prefix = _paths(self.spec)['prefix'] + '-recovery'
        existing = {}
        for logical, pin in state.get('fuse_files', {}).items():
            current = self._file(logical)
            need(current is None or current['sha256'] == pin, 'REMOTE_RECOVERY_UNIT_CHANGED')
            if current is not None:
                existing[logical] = pin
        for name, stop in ((prefix + '.timer', True), (prefix + '-boot.service', False)):
            logical = '/etc/systemd/system/' + name
            if logical in existing or name in state.get('fuse_enable_attempts', []):
                args = ['/usr/bin/systemctl', 'disable'] + (['--now'] if stop else []) + [name]
                self.command(args, allowed=(0, 1, 5))
                actual = self._service_state(name)
                need(actual['enabled'] not in ('enabled', 'enabled-runtime') and
                     (not stop or actual['active'] != 'active'), 'REMOTE_RECOVERY_UNIT_NOT_DISARMED')
        for logical in existing:
            self.path(logical).unlink()
        self.command(['/usr/bin/systemctl', 'daemon-reload'])

    def install(self, logical, item, state):
        root, target = self.root(), self.path(logical)
        self._trusted(target, missing=True)
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._trusted(target.parent)
        index = str(state['file_order'].index(logical))
        staged = target.with_name('.' + target.name + '.clearpath-' + state['id'])
        _write_new(staged, item['raw'], item['mode'])
        staged_info = self._file(str(staged))
        journal = {'action': 'install', 'target': logical, 'before': state['before']['files'][logical],
                   'staged': staged_info, 'desired_sha256': digest(item['raw']), 'desired_mode': item['mode']}
        _write_new(root / 'journal' / (index + '.prepared.json'), encoded(journal))
        need(self._file(logical) == state['before']['files'][logical], 'REMOTE_FILE_BASELINE_DRIFT')
        os.replace(staged, target)
        _sync(target.parent)
        current = self._file(logical)
        need(current['sha256'] == digest(item['raw']) and current['mode'] == item['mode'], 'REMOTE_FILE_READBACK_FAILED')
        _write_new(root / 'journal' / (index + '.done.json'), encoded({'target': logical, 'after': current}))

    def apply(self, payload, state):
        for logical, item in payload.items():
            self.install(logical, item, state)
        self.command(['/usr/bin/systemctl', 'daemon-reload'])
        if 'core' in self.spec['modules']:
            (self.root() / 'core-data').mkdir(mode=0o700, exist_ok=True)
            p = _paths(self.spec)
            self.command([p['binary'], '-t', '-d', str(self.root() / 'core-data'), '-f', p['config']])
            self.command(['/usr/bin/systemctl', 'restart', _service(self.spec, 'core')])
            self.command(['/usr/bin/systemctl', 'is-active', '--quiet', _service(self.spec, 'core')])
            state['owned_tun'] = self.wait_tun()
            _save(self.root() / 'state.json', state)
        if 'reverse_tunnel' in self.spec['modules']:
            self.command(['/usr/bin/systemctl', 'restart', _service(self.spec, 'reverse_tunnel')])
            self.command(['/usr/bin/systemctl', 'is-active', '--quiet', _service(self.spec, 'reverse_tunnel')])
        if 'ssh' in self.spec['modules']:
            self.command(['/usr/sbin/sshd', '-t'])
            checks = {'port': str(self.spec['ssh']['port']), 'passwordauthentication': 'yes' if self.spec['ssh']['password_authentication'] else 'no',
                      'permitrootlogin': self.spec['ssh']['permit_root_login'], 'allowusers': ' '.join(self.spec['ssh']['allow_users'])}
            commands = [['/usr/sbin/sshd', '-T']]
            for context in self.spec['ssh']['validation_contexts']:
                selected = 'user=%s,host=%s,addr=%s,laddr=%s,lport=%s' % (context['user'], context['host'], context['address'], context['local_address'], context['local_port'])
                commands.append(['/usr/sbin/sshd', '-T', '-C', selected])
            state['ssh_readback'] = []
            for command in commands:
                effective = self.command(command)
                lines = {}
                for line in effective.splitlines():
                    if ' ' in line:
                        key, value = line.split(' ', 1)
                        lines.setdefault(key, []).append(value)
                ports = lines.get('port', [])
                root_login = lines.get('permitrootlogin', [])
                if root_login == ['without-password']:
                    lines['permitrootlogin'] = ['prohibit-password']
                state['ssh_readback'].append({'ports': ports, 'context': 'explicit' if '-C' in command else 'global'})
                _save(self.root() / 'state.json', state)
                need(set(ports) == {checks['port']} and all(lines.get(key) == [value] for key, value in checks.items() if key != 'port'),
                     'REMOTE_SSH_EFFECTIVE_CONFIGURATION_MISMATCH')
            self.restart_ssh(state)
        if 'inbound_guard' in self.spec['modules']:
            state['inbound_attempted'] = True
            state['inbound_expected_sha256'] = digest(_canonical_nft(inbound_document(self.spec)))
            _save(self.root() / 'state.json', state)
            self.apply_inbound(state['before']['inbound'])
            state['inbound_after_sha256'] = digest(self._inbound())
            _save(self.root() / 'state.json', state)
        if 'watchdog' in self.spec['modules']:
            self.command(['/usr/bin/systemctl', 'start', _service(self.spec, 'watchdog').replace('.service', '.timer')])

    def apply_inbound(self, before):
        document = inbound_document(self.spec)
        if before is not None:
            document['nftables'].insert(0, {'delete': {'table': {'family': 'inet', 'name': _paths(self.spec)['table']}}})
        raw = encoded(document).decode()
        self.command(['/usr/sbin/nft', '-j', '-c', '-f', '-'], raw)
        self.command(['/usr/sbin/nft', '-j', '-f', '-'], raw)

    def persist(self, state):
        for name in _services(self.spec):
            if name == _service(self.spec, 'watchdog'):
                continue
            self.command(['/usr/bin/systemctl', 'enable', name])
            need(self._service_state(name)['enabled'] == 'enabled', 'REMOTE_PERSISTENCE_READBACK_FAILED')


def _load_state(folder, host):
    host.check(folder)
    state = loads(_safe_read(Path(folder) / 'state.json', 8 * MAX_JSON, owner=host.owner))
    need(state.get('schema') == STATE_SCHEMA and state.get('plan_sha256') == digest(encoded(state.get('plan'))), 'REMOTE_STATE_INVALID')
    validate_plan(state['plan'])
    order = state.get('file_order')
    need(type(order) is list and len(order) == len(set(order)) and set(order) == set(state.get('before', {}).get('files', {})),
         'REMOTE_STATE_FILE_ORDER_INVALID')
    need(state['plan']['spec'] == host.spec and state.get('binding') == _binding(host), 'REMOTE_STATE_BINDING_CHANGED')
    need(digest(_safe_read(Path(folder) / 'worker.py', 4 * MAX_JSON, owner=host.owner)) == state.get('worker_sha256'), 'REMOTE_RETAINED_WORKER_CHANGED')
    return state


def _binding(host):
    return digest(['linux', host.machine_id(), str(host.owner), _paths(host.spec)['state']])


def source_matches(host, source):
    path = host.path(source['path'])
    if source['sha256'] is None:
        return not path.exists() and not path.is_symlink()
    return digest(_safe_read(path, 4 * 1024 * 1024)) == source['sha256']


def _baseline(spec, before):
    expected = spec['expected_files']
    for logical, actual in before['files'].items():
        pin = expected.get(logical)
        need((actual is None and pin is None) or (actual is not None and pin == actual['sha256']), 'REMOTE_EXISTING_OWNED_FILE_REQUIRES_EXACT_BASELINE')
    for name, actual in before['services'].items():
        expected_service = spec['expected_services'].get(name)
        if expected_service is None:
            need(actual['active'] == 'inactive' and actual['enabled'] == 'not-found', 'REMOTE_EXISTING_SERVICE_REQUIRES_BASELINE')
        else:
            need(actual == expected_service, 'REMOTE_SERVICE_BASELINE_DRIFT')
    expected_nft = spec['expected_inbound_sha256']
    need((before['inbound'] is None and expected_nft is None) or
         (before['inbound'] is not None and digest(before['inbound']) == expected_nft), 'REMOTE_EXISTING_INBOUND_REQUIRES_BASELINE')
    if 'core' in spec['modules']:
        need(before['tun']['ifindex'] is None and before['tun']['routes'] == [], 'REMOTE_TUN_OR_ROUTE_TABLE_ALREADY_OWNED_ELSEWHERE')


def activate(folder, bundle_pin, allow_network=False, second_session=False, host=None):
    _, manifest, plan, runtime = read_bundle(folder, bundle_pin)
    spec = plan['spec']
    host = host or NativeHost(spec)
    host.check()
    need(not plan['requires_network'] or allow_network, 'REMOTE_NETWORK_PERMISSION_REQUIRED')
    need(not plan['requires_second_session'] or second_session, 'REMOTE_SECOND_SESSION_REQUIRED')
    payload, sources = host.payload(allow_network)
    before = host.snapshot(list(payload))
    need(sum(x['size'] for x in before['files'].values() if x is not None) <= 256 * 1024 * 1024,
         'REMOTE_BACKUP_TOTAL_BUDGET')
    _baseline(spec, before)
    host.prepare(runtime)
    root = host.root()
    with operation_lock(root):
        need(host.snapshot(list(payload)) == before, 'REMOTE_BASELINE_CHANGED_BEFORE_ARM')
        for index, logical in enumerate(payload):
            if before['files'][logical] is not None:
                _write_new(root / 'before' / str(index), _safe_read(host.path(logical), MAX_BINARY, owner=host.owner))
        state = {'schema': STATE_SCHEMA, 'id': uuid.uuid4().hex, 'created_at': stamp(), 'binding': _binding(host),
                 'plan': plan, 'plan_sha256': manifest['plan_sha256'], 'bundle_sha256': bundle_pin,
                 'worker_sha256': digest(runtime), 'sources': sources, 'before': before,
                 'file_order': list(payload),
                 'desired': {name: {'sha256': digest(item['raw']), 'mode': item['mode']} for name, item in payload.items()},
                 'phase': 'prepared', 'expires_at': time.time() + spec['fuse_seconds'], 'prepared_boot_id': host.boot_id(),
                 'recovery_armed': False, 'persisted': False, 'startup_pending': False, 'applied': None}
        _write_new(root / 'state.json', encoded(state))
        try:
            state['phase'] = 'arming'
            _save(root / 'state.json', state)
            host.arm(state)
            state.update(phase='armed', recovery_armed=True)
            _save(root / 'state.json', state)
            need(time.time() < state['expires_at'], 'REMOTE_FUSE_EXPIRED_BEFORE_APPLY')
            state['phase'] = 'applying'
            _save(root / 'state.json', state)
            host.apply(payload, state)
            state['applied'] = host.snapshot(list(payload))
            for logical, expected in state['desired'].items():
                actual = state['applied']['files'][logical]
                need(actual is not None and actual['sha256'] == expected['sha256'] and actual['mode'] == expected['mode'], 'REMOTE_APPLY_READBACK_FAILED')
            state['phase'] = 'pending_confirmation'
            _save(root / 'state.json', state)
        except (Exception, KeyboardInterrupt) as error:
            state['phase'] = 'apply_uncertain'
            state['error_code'] = str(error) if isinstance(error, RemoteError) else 'REMOTE_APPLY_IO_OR_INTERRUPTED'
            _save(root / 'state.json', state)
            return {'status': 'partial_or_unconfirmed', 'exit_code': 2, 'phase': state['phase'],
                    'reason_code': state['error_code'], 'operation_id': state['id'], 'plan_sha256': state['plan_sha256'],
                    'recovery_armed': state['recovery_armed'], 'changes_state': 'inspect_before_retry', 'network_verified': False}
    return {'status': 'applied_pending_confirmation', 'exit_code': 2, 'plan_sha256': state['plan_sha256'],
            'operation_id': state['id'], 'recovery_armed': True, 'persistent': False,
            'network_verified': False, 'selected_modules': spec['modules'],
            'ssh_adoption': plan['ssh_adoption'], 'old_unpersisted_sshd_arguments_retained': False}


def _accepted_current(host, state, logical, current):
    before = state['before']['files'][logical]
    if current == before:
        return True
    if logical in state.get('restored_files', {}) and current == state['restored_files'][logical]:
        return True
    restore_prepared = state.get('restore_prepared', {}).get(logical)
    if current is not None and restore_prepared is not None:
        keys = ('sha256', 'mode', 'uid', 'gid', 'device', 'inode', 'mtime_ns')
        if all(current.get(key) == restore_prepared.get(key) for key in keys):
            return True
    after = state.get('applied', {}).get('files', {}).get(logical) if state.get('applied') else None
    if after is not None and current == after:
        return True
    index = str(state['file_order'].index(logical))
    done = host.root() / 'journal' / (index + '.done.json')
    if done.exists():
        return current == loads(_safe_read(done, MAX_JSON, owner=host.owner)).get('after')
    prepared = host.root() / 'journal' / (index + '.prepared.json')
    if current is not None and prepared.exists():
        candidate = loads(_safe_read(prepared, MAX_JSON, owner=host.owner)).get('staged', {})
        keys = ('sha256', 'mode', 'uid', 'gid', 'device', 'inode', 'mtime_ns')
        return all(current.get(key) == candidate.get(key) for key in keys)
    return False


def restore(folder, expected, host, pending_only=False):
    with operation_lock(folder):
        state = _load_state(folder, host)
        need(state['plan_sha256'] == expected, 'REMOTE_EXPECTED_PLAN_DIGEST')
        if pending_only and (state['phase'] in ('confirmed', 'restored') or
                             (time.time() < state['expires_at'] and host.boot_id() == state['prepared_boot_id'])):
            return {'status': 'not_due', 'exit_code': 0}
        if state['phase'] == 'restored':
            return {'status': 'restored', 'exit_code': 0, 'runtime_restored': state.get('runtime_restored', False),
                    'startup_restored': True, 'old_unpersisted_sshd_arguments_restored': False}
        names = state['file_order']
        current = host.snapshot(names)
        boot_recovery = host.boot_id() != state['prepared_boot_id']
        if 'ssh' in host.spec['modules']:
            source = state.get('sources', {}).get('sshd_config')
            need(source and digest(_safe_read(host.path(source['path']), 1024 * 1024, owner=host.owner)) == source['sha256'], 'REMOTE_SHARED_SSH_CONFIG_CHANGED')
            for key, source in host.ssh_startup_sources().items():
                need(source == state.get('sources', {}).get(key), 'REMOTE_SHARED_SSH_STARTUP_CHANGED')
            need(current['shared_ssh']['enabled'] == state['before']['shared_ssh']['enabled'], 'REMOTE_SHARED_SSH_STARTUP_STATE_CHANGED')
        # Complete preflight before changing any surviving current configuration.
        need(all(_accepted_current(host, state, name, current['files'][name]) for name in names), 'REMOTE_RESTORE_FILE_CONFLICT')
        for index, name in enumerate(names):
            before_file = state['before']['files'][name]
            if before_file is not None:
                need(digest(_safe_read(Path(folder) / 'before' / str(index), MAX_BINARY, owner=host.owner)) == before_file['sha256'],
                     'REMOTE_BACKUP_CORRUPT')
        for name, actual in current['services'].items():
            old = state['before']['services'][name]['enabled']
            accepted = {old}
            if state.get('applied'):
                accepted.add(state['applied']['services'][name]['enabled'])
            else:
                accepted.add('disabled')  # our created, not-yet-enabled unit
            if state.get('startup_pending'):
                accepted.add('enabled')
            need(actual['enabled'] in accepted, 'REMOTE_RESTORE_STARTUP_CONFLICT')
        if 'inbound_guard' in host.spec['modules']:
            allowed = [state['before']['inbound']]
            if state.get('applied'):
                allowed.append(state['applied']['inbound'])
            # A recorded pending nft change has its own expected generation.
            if current['inbound'] not in allowed:
                need((boot_recovery and current['inbound'] is None) or (state.get('inbound_attempted') and
                     digest(current['inbound']) in (state.get('inbound_after_sha256'), state.get('inbound_expected_sha256'))), 'REMOTE_RESTORE_INBOUND_CONFLICT')
        state['phase'] = 'restoring'
        _save(Path(folder) / 'state.json', state)
        for name in _services(host.spec):
            if not boot_recovery and (name.endswith('.timer') or name in (_service(host.spec, 'core'), _service(host.spec, 'reverse_tunnel'))):
                host.command(['/usr/bin/systemctl', 'stop', name], allowed=(0, 5))
            before_service = state['before']['services'][name]
            host.command(['/usr/bin/systemctl', 'enable' if before_service['enabled'] == 'enabled' else 'disable', name], allowed=(0, 1, 5))
        if 'core' in host.spec['modules'] and not boot_recovery:
            tun = host._tun()
            if tun != state['before']['tun']:
                owned = state.get('owned_tun') or (state.get('applied') or {}).get('tun')
                need(owned is not None and tun == owned, 'REMOTE_RESTORE_TUN_OWNERSHIP_CONFLICT')
                item = host.spec['core']
                if tun['routes']:
                    host.command(['/usr/sbin/ip', 'route', 'flush', 'table', str(item['route_table'])])
                if tun['ifindex'] is not None:
                    host.command(['/usr/sbin/ip', 'link', 'delete', 'dev', item['tun_interface']])
                need(host._tun() == state['before']['tun'], 'REMOTE_RESTORE_TUN_READBACK_FAILED')
        if 'inbound_guard' in host.spec['modules'] and current['inbound'] != state['before']['inbound']:
            table = _paths(host.spec)['table']
            commands = [{'delete': {'table': {'family': 'inet', 'name': table}}}] if current['inbound'] is not None else []
            if state['before']['inbound'] is not None:
                commands += [{'add': item} for row in state['before']['inbound'].get('nftables', []) for item in [row] if 'metainfo' not in row]
            host.command(['/usr/sbin/nft', '-j', '-f', '-'], encoded({'nftables': commands}).decode())
        for index, name in enumerate(names):
            target, before_file = host.path(name), state['before']['files'][name]
            actual = host._file(name)
            if actual == before_file:
                continue
            need(_accepted_current(host, state, name, actual), 'REMOTE_RESTORE_FILE_CONFLICT')
            if before_file is not None and actual is not None and all(actual[k] == before_file[k] for k in ('sha256', 'mode', 'uid', 'gid')):
                # A prior interrupted restore may already have committed this
                # exact old object. Its recorded identity was checked above.
                state.setdefault('restored_files', {})[name] = actual
                _save(Path(folder) / 'state.json', state)
                continue
            if before_file is None:
                target.unlink()
                _sync(target.parent)
            else:
                raw = _safe_read(Path(folder) / 'before' / str(index), MAX_BINARY, owner=host.owner)
                need(digest(raw) == before_file['sha256'], 'REMOTE_BACKUP_CORRUPT')
                staged = target.with_name('.' + target.name + '.restore-' + state['id'])
                _write_new(staged, raw, before_file['mode'])
                os.chown(staged, before_file['uid'], before_file['gid'])
                state.setdefault('restore_prepared', {})[name] = host._file(str(staged))
                _save(Path(folder) / 'state.json', state)
                os.replace(staged, target)
                _sync(target.parent)
            state.setdefault('restored_files', {})[name] = host._file(name)
            _save(Path(folder) / 'state.json', state)
        host.command(['/usr/bin/systemctl', 'daemon-reload'])
        if 'ssh' in host.spec['modules'] and not boot_recovery:
            host.command(['/usr/sbin/sshd', '-t'])
            host.restart_ssh(state, recovery=True)
        for name, old in state['before']['services'].items():
            if old['active'] == 'active' and not boot_recovery:
                host.command(['/usr/bin/systemctl', 'start', name])
        restored = host.snapshot(names)
        for name, before_file in state['before']['files'].items():
            actual = restored['files'][name]
            need((before_file is None and actual is None) or (before_file is not None and actual is not None and
                 all(actual[key] == before_file[key] for key in ('sha256', 'mode', 'uid', 'gid'))), 'REMOTE_RESTORE_READBACK_FAILED')
        need(restored['inbound'] == state['before']['inbound'], 'REMOTE_RESTORE_INBOUND_READBACK_FAILED')
        need(all(actual['enabled'] == state['before']['services'][name]['enabled'] for name, actual in restored['services'].items()),
             'REMOTE_RESTORE_STARTUP_READBACK_FAILED')
        if 'ssh' in host.spec['modules']:
            need(restored['shared_ssh']['enabled'] == state['before']['shared_ssh']['enabled'], 'REMOTE_SHARED_SSH_STARTUP_READBACK_FAILED')
            if not boot_recovery:
                need(restored['shared_ssh']['active'] == state['before']['shared_ssh']['active'], 'REMOTE_SHARED_SSH_RUNTIME_READBACK_FAILED')
        if not boot_recovery:
            need(restored['services'] == state['before']['services'], 'REMOTE_RESTORE_RUNTIME_OR_STARTUP_FAILED')
        state.update(phase='restoring', persisted=False, startup_pending=False, restored=restored)
        _save(Path(folder) / 'state.json', state)
        host.disarm(state)
        state.update(phase='restored', recovery_armed=False, runtime_restored=not boot_recovery and 'ssh' not in host.spec['modules'])
        _save(Path(folder) / 'state.json', state)
        return {'status': 'restored', 'exit_code': 0, 'startup_restored': True,
                'private_backups_retained': True, 'network_verified': False, 'post_boot_runtime_recheck': boot_recovery,
                'runtime_restored': state['runtime_restored'], 'saved_files_restored': True,
                'service_states_restored': not boot_recovery, 'old_unpersisted_sshd_arguments_restored': False,
                'restore_scope': 'saved_files_and_service_states_not_old_sshd_argv'}


def confirm(folder, expected, verification, persist, host):
    with operation_lock(folder):
        state = _load_state(folder, host)
        need(state['plan_sha256'] == expected and state['phase'] == 'pending_confirmation' and
             time.time() < state['expires_at'] and state['prepared_boot_id'] == host.boot_id(), 'REMOTE_CONFIRMATION_EXPIRED_OR_UNAVAILABLE')
        need(persist or not state['plan']['requires_persist'], 'REMOTE_SHARED_CONFIGURATION_REQUIRES_PERSIST_CONFIRMATION')
        need(type(verification) is dict and verification.get('schema') == 'clearpath-remote-verification/1' and
             verification.get('plan_sha256') == expected and verification.get('normal_path') == 'observed' and
             verification.get('management_path') == 'observed', 'REMOTE_VERIFICATION_REQUIRED')
        if state['plan']['requires_second_session']:
            need(verification.get('second_session') == 'observed', 'REMOTE_SECOND_SESSION_VERIFICATION_REQUIRED')
        for source in state.get('sources', {}).values():
            need(source_matches(host, source), 'REMOTE_APPROVED_SOURCE_CHANGED')
        need(host.snapshot(list(state['before']['files'])) == state['applied'], 'REMOTE_CONFIGURATION_DRIFT')
        state.update(phase='confirming', startup_pending=bool(persist), verification=verification)
        _save(Path(folder) / 'state.json', state)
        approved = state['applied']
        if persist:
            host.persist(state)
        need(time.time() < state['expires_at'], 'REMOTE_EXPIRED_DURING_CONFIRMATION')
        after = host.snapshot(list(state['before']['files']))
        need(after['files'] == approved['files'] and after['inbound'] == approved['inbound'] and after['tun'] == approved['tun'] and
             after.get('shared_ssh') == approved.get('shared_ssh'),
             'REMOTE_CONFIGURATION_CHANGED_DURING_PERSISTENCE')
        need(set(after['services']) == set(approved['services']), 'REMOTE_SERVICE_SCOPE_CHANGED_DURING_PERSISTENCE')
        for name, old in approved['services'].items():
            enabled = 'enabled' if persist and name != _service(host.spec, 'watchdog') else old['enabled']
            need(after['services'][name] == dict(old, enabled=enabled), 'REMOTE_SERVICE_STATE_CHANGED_DURING_PERSISTENCE')
        for source in state.get('sources', {}).values():
            need(source_matches(host, source),
                 'REMOTE_APPROVED_SOURCE_CHANGED_DURING_PERSISTENCE')
        state.update(phase='confirmed', persisted=bool(persist), startup_pending=False, recovery_armed=False)
        state['applied'] = after
        _save(Path(folder) / 'state.json', state)
        host.disarm(state)
        return {'status': 'configuration_confirmed', 'exit_code': 0, 'persistent': bool(persist),
                'network_verified': False, 'verification_source': 'operator_supplied_not_authenticated'}


def status(folder, host):
    state = _load_state(folder, host)
    current = host.snapshot(list(state['before']['files']))
    expected = dict(state.get('restored', state['before']), services=state['before']['services']) if state['phase'] == 'restored' else state.get('applied')
    matches = current == expected
    return {'status': state['phase'], 'exit_code': 0 if matches and state['phase'] in ('confirmed', 'restored') else 2,
            'plan_sha256': state['plan_sha256'], 'configuration_matches': matches, 'persistent': state['persisted'],
            'recovery_armed': state['recovery_armed'], 'network_verified': False}


def watchdog(folder, host):
    with operation_lock(folder):
        state = _load_state(folder, host)
        need(state['phase'] in ('pending_confirmation', 'confirmed') and 'watchdog' in host.spec['modules'], 'REMOTE_WATCHDOG_NOT_SELECTED_OR_ACTIVE')
        need(state['phase'] == 'confirmed' or (time.time() < state['expires_at'] and host.boot_id() == state['prepared_boot_id']),
             'REMOTE_PENDING_WATCHDOG_EXPIRED')
        core = _service(host.spec, 'core')
        if host._service_state(core)['active'] != 'failed':
            return {'status': 'no_failed_owned_core', 'exit_code': 0}
        now = host.snapshot(list(state['before']['files']))
        approved = state['applied']
        need(now['files'] == approved['files'] and now['inbound'] == approved['inbound'], 'REMOTE_WATCHDOG_CONFIGURATION_DRIFT')
        for name, current_service in now['services'].items():
            if name == core:
                need(current_service['enabled'] == approved['services'][name]['enabled'], 'REMOTE_WATCHDOG_SERVICE_DRIFT')
            elif name == _service(host.spec, 'watchdog'):
                need(current_service['enabled'] == approved['services'][name]['enabled'] and
                     current_service['active'] in ('inactive', 'activating', 'active'), 'REMOTE_WATCHDOG_SERVICE_DRIFT')
            else:
                need(current_service == approved['services'][name], 'REMOTE_WATCHDOG_SERVICE_DRIFT')
        for source in state.get('sources', {}).values():
            need(source_matches(host, source), 'REMOTE_WATCHDOG_APPROVED_SOURCE_CHANGED')
        expected_tun = approved['tun']
        clean_crash = now['tun'] == {'ifindex': None, 'routes': []}
        need(clean_crash or (now['tun'] == expected_tun and expected_tun is not None), 'REMOTE_WATCHDOG_ROUTE_OWNERSHIP_CHANGED')
        item = host.spec['core']
        _save(Path(folder) / 'watchdog-intent.json', {'schema': 'clearpath-watchdog-attempt/1', 'created_at': stamp(),
              'plan_sha256': state['plan_sha256'], 'approved_sha256': digest(approved), 'observed_before': now})
        if host._service_state(core)['active'] != 'failed':
            return {'status': 'owned_core_recovered_before_intervention', 'exit_code': 0, 'network_verified': False}
        # A manual stop suppresses systemd Restart=on-failure for this exact unit.
        # Do not race automatic restarts while deleting a previously owned TUN.
        host.command(['/usr/bin/systemctl', 'stop', core])
        paused = host.snapshot(list(state['before']['files']))
        need(paused['files'] == now['files'] and paused['inbound'] == now['inbound'], 'REMOTE_WATCHDOG_CONFIGURATION_CHANGED_WHILE_STOPPING')
        fresh_tun = paused['tun']
        clean_crash = fresh_tun == {'ifindex': None, 'routes': []}
        need(clean_crash or fresh_tun == expected_tun, 'REMOTE_WATCHDOG_FRESH_ROUTE_OWNERSHIP_CHANGED')
        if not clean_crash and fresh_tun['routes']:
            host.command(['/usr/sbin/ip', 'route', 'flush', 'table', str(item['route_table'])])
        if not clean_crash and fresh_tun['ifindex'] is not None:
            host.command(['/usr/sbin/ip', 'link', 'delete', 'dev', item['tun_interface']])
        host.command(['/usr/bin/systemctl', 'restart', core])
        host.command(['/usr/bin/systemctl', 'is-active', '--quiet', core])
        host.wait_tun()
        after = host.snapshot(list(state['before']['files']))
        need(after['files'] == now['files'] and after['inbound'] == now['inbound'], 'REMOTE_WATCHDOG_POST_RESTART_CONFIGURATION_DRIFT')
        for name, old in now['services'].items():
            wanted = dict(old, active='active') if name == core else old
            need(after['services'][name] == wanted, 'REMOTE_WATCHDOG_POST_RESTART_SERVICE_DRIFT')
        for source in state.get('sources', {}).values():
            need(source_matches(host, source), 'REMOTE_WATCHDOG_POST_RESTART_SOURCE_DRIFT')
        need(after['tun'] is not None and after['tun']['ifindex'] is not None, 'REMOTE_WATCHDOG_TUN_NOT_READY')
        import copy
        updated = copy.deepcopy(approved)
        updated['services'][core] = after['services'][core]
        updated['tun'] = after['tun']
        state['applied'], state['owned_tun'] = updated, after['tun']
        _save(Path(folder) / 'state.json', state)
        return {'status': 'owned_core_restarted', 'exit_code': 0, 'network_verified': False}


def _host_from_state(folder):
    # No user-selected module import; only our retained self-contained worker.
    record = loads(_safe_read(Path(folder) / 'state.json', 8 * MAX_JSON, owner=0))
    validate_plan(record.get('plan'))
    return NativeHost(record['plan']['spec'])


def _worker(action, folder, challenge=None):
    host = _host_from_state(folder)
    state = _load_state(folder, host)
    if action == '_handshake':
        need(type(challenge) is str and re.fullmatch(r'[a-f0-9]{32}', challenge) and
             challenge == state.get('handshake_challenge') and state['phase'] == 'arming', 'REMOTE_HANDSHAKE_CHALLENGE_INVALID')
        return {'status': 'recovery_worker_ready', 'challenge': challenge, 'plan_sha256': state['plan_sha256'],
                'worker_sha256': state['worker_sha256'], 'binding': state['binding']}
    if action == '_expire':
        # Recheck phase/expiry under the same lock used by confirm. A worker
        # queued before confirmation must not undo a confirmation that won it.
        return restore(folder, state['plan_sha256'], host, pending_only=True)
    if action == '_watchdog':
        return watchdog(folder, host)
    if action == '_inbound':
        with operation_lock(folder):
            state = _load_state(folder, host)
            need(state['phase'] == 'confirmed' and state['persisted'], 'REMOTE_BOOT_NOT_CONFIRMED')
            before = host._inbound()
            need(before in (None, state['applied']['inbound']), 'REMOTE_BOOT_INBOUND_CONFLICT')
            host.apply_inbound(before)
        return {'status': 'owned_inbound_loaded', 'exit_code': 0}
    raise RemoteError('REMOTE_WORKER_ACTION_INVALID')


def register_commands(sub):
    p = sub.add_parser('remote-plan', help='Offline Debian/Ubuntu module plan; no SSH or target reads')
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p = sub.add_parser('remote-export', help='Export pinned self-contained deployment/recovery bundle')
    p.add_argument('--plan', required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('remote-apply', help='Apply only on actual Linux root target; arm independent recovery first')
    p.add_argument('--bundle', required=True)
    p.add_argument('--bundle-sha256', required=True)
    p.add_argument('--allow-network', action='store_true')
    p.add_argument('--second-session-verified', action='store_true')
    for flag in ('allow-system-change', 'control-channel-independent', 'recovery-ready'):
        p.add_argument('--' + flag, action='store_true')
    for command in ('remote-confirm', 'remote-rollback', 'remote-status'):
        p = sub.add_parser(command, help='Confirm, restore or inspect one retained remote deployment')
        p.add_argument('--state-dir', required=True)
        p.add_argument('--plan-sha256', required=command != 'remote-status')
        if command == 'remote-confirm':
            p.add_argument('--verification-file', required=True)
            p.add_argument('--persist', action='store_true')
        if command != 'remote-status':
            for flag in ('allow-system-change', 'control-channel-independent', 'recovery-ready'):
                p.add_argument('--' + flag, action='store_true')


def run(c, args):
    try:
        if args.command == 'remote-plan':
            plan = make_plan(c.load_json(c.read_bytes(args.input, MAX_JSON)))
            raw = encoded(plan)
            c.write_new(args.output, raw)
            return {'status': 'remote_plan_written', 'exit_code': 0, 'plan_sha256': digest(raw),
                    'selected_modules': plan['spec']['modules'], 'network_requests': 0, 'system_changes_performed': False}
        if args.command == 'remote-export':
            raw = c.read_bytes(args.plan, MAX_JSON)
            need(digest(raw) == args.plan_sha256, 'REMOTE_PLAN_DIGEST_MISMATCH')
            return export_bundle(loads(raw), args.plan_sha256, args.out)
        if args.command in MUTATING_COMMANDS:
            need(args.allow_system_change and args.control_channel_independent and args.recovery_ready,
                 'REMOTE_EXACT_CHANGE_AND_INDEPENDENT_RECOVERY_REQUIRED')
        if args.command == 'remote-apply':
            return activate(args.bundle, args.bundle_sha256, args.allow_network, args.second_session_verified)
        host = _host_from_state(args.state_dir)
        if args.command == 'remote-confirm':
            return confirm(args.state_dir, args.plan_sha256, c.load_json(c.read_bytes(args.verification_file, 65536)), args.persist, host)
        if args.command == 'remote-rollback':
            return restore(args.state_dir, args.plan_sha256, host)
        if args.command == 'remote-status':
            return status(args.state_dir, host)
        raise RemoteError('REMOTE_COMMAND_UNKNOWN')
    except RemoteError as error:
        raise c.SetupError(str(error)) from None
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise c.SetupError('REMOTE_IO_OR_STATE_INVALID') from None


if __name__ == '__main__':
    # The exported file supports both ordinary CLI use and retained worker use.
    if (len(sys.argv) == 3 and sys.argv[1] in ('_expire', '_watchdog', '_inbound')) or (len(sys.argv) == 4 and sys.argv[1] == '_handshake'):
        try:
            result = _worker(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
            print(json.dumps(result, sort_keys=True))
            raise SystemExit(result.get('exit_code', 0))
        except (RemoteError, OSError, ValueError, KeyError, TypeError):
            print('{"status":"recovery_incomplete","reason_code":"REMOTE_WORKER_REQUIRES_REVIEW","exit_code":2}')
            raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    register_commands(sub)
    args = parser.parse_args()
    class Context:
        SetupError = RemoteError
        read_bytes = staticmethod(_safe_read)
        load_json = staticmethod(loads)
        write_new = staticmethod(_write_new)
    try:
        result = run(Context, args)
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(result.get('exit_code', 0))
    except RemoteError as error:
        print(json.dumps({'status': 'unavailable', 'reason_code': str(error), 'exit_code': 2}))
        raise SystemExit(2)
