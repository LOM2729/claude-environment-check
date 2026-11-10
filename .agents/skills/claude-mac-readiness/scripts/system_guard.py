"""Scoped native firewall transactions; planning is offline, application is opt-in.

No subprocess is run at import or by plan/export. Native operations own only one
anchor/table or exact named rules. A private, independently scheduled rollback is
armed before mutation; confirm is the only path to new boot persistence. This
module can run its retained recovery worker without the rest of the kit.
"""
import argparse
import base64
from contextlib import contextmanager
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid

COMMANDS = ('guard-plan', 'guard-inspect', 'guard-export', 'guard-on', 'guard-confirm', 'guard-off', 'guard-status', 'guard-uninstall', 'guard-launch')
MUTATING_COMMANDS = ('guard-on', 'guard-confirm', 'guard-off', 'guard-uninstall', 'guard-launch')
SCHEMA = 'clearpath-system-guard/1'
STATE_SCHEMA = 'clearpath-system-guard-state/1'
MAX_INPUT = 512 * 1024


class GuardError(Exception):
    pass


def need(value, code):
    if not value:
        raise GuardError(code)


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, 'GUARD_DUPLICATE_KEY')
        result[key] = value
    return result


def read_json(path, maximum=MAX_INPUT):
    p = Path(path)
    need(p.is_absolute(), 'GUARD_ABSOLUTE_PATH_REQUIRED')
    for item in (p, *p.parents):
        need(not item.is_symlink(), 'GUARD_SYMLINK_REJECTED')
    before = p.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum, 'GUARD_UNSAFE_INPUT')
    with p.open('rb') as stream:
        raw = stream.read(maximum + 1)
    after = p.stat()
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and len(raw) <= maximum, 'GUARD_INPUT_CHANGED')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError):
        raise GuardError('GUARD_INVALID_JSON') from None


def private_write(path, value, new=False):
    p = Path(path)
    need(not p.is_symlink() and p.parent.is_dir() and not p.parent.is_symlink(), 'GUARD_UNSAFE_STATE_PATH')
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
    if new:
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        # Leave interrupted staging for inspection; a stale .new must not block
        # the independent recovery channel or a later state commit.
        tmp = p.with_name(p.name + '.new-' + uuid.uuid4().hex)
        private_write(tmp, raw, True)
        os.replace(str(tmp), str(p))
    if os.name != 'nt':
        os.chmod(p, 0o600)
        fd = os.open(str(p.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        protected = windows_directory(True) / 'Clearpath' / 'guard'
        if str(p.absolute()).lower().startswith(str(protected).lower() + '\\'):
            _secure_windows_file(p)


def _secure_windows_file(path):
    """Root recovery material is owned by Administrators, not a UAC user's SID."""
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    setter = advapi.SetFileSecurityW
    setter.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    setter.restype = wintypes.BOOL
    descriptor = ctypes.c_void_p()
    need(convert('O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)', 1, ctypes.byref(descriptor), None), 'GUARD_WINDOWS_PRIVATE_ACL_FAILED')
    try:
        need(setter(str(path), 0x80000007, descriptor), 'GUARD_WINDOWS_PRIVATE_ACL_FAILED')
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(descriptor)


def _word(value, code='GUARD_INVALID_IDENTIFIER'):
    need(type(value) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', value), code)
    return value


def _interface(value, windows=False):
    if windows:
        need(type(value) is str and 0 < len(value) <= 100 and not any(ord(c) < 32 or c in '*?[]\"' for c in value), 'GUARD_INVALID_INTERFACE')
    else:
        need(type(value) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,30}', value), 'GUARD_INVALID_INTERFACE')
    return value


def _port(value):
    need(type(value) is int and 1 <= value <= 65535, 'GUARD_INVALID_PORT')
    return value


def _ipv4(value, network=False):
    try:
        result = ipaddress.ip_network(value, strict=True) if network else ipaddress.ip_address(value)
    except (ValueError, TypeError):
        raise GuardError('GUARD_IPV4_REQUIRED') from None
    need(result.version == 4, 'GUARD_IPV4_REQUIRED')
    if network:
        need(result.prefixlen > 0, 'GUARD_UNBOUNDED_EXCEPTION_REJECTED')
    else:
        need(not result.is_unspecified and not result.is_multicast and not result.is_loopback, 'GUARD_NODE_IPV4_REQUIRED')
    return str(result)


def validate_input(value):
    fields = {'schema', 'scope', 'platform', 'mode', 'policy', 'interfaces', 'tunnels', 'nodes',
              'exceptions', 'bootstrap_dns', 'core_path', 'windows_disable_rules', 'fuse_seconds', 'trusted_python'}
    need(type(value) is dict and not set(value) - fields, 'GUARD_INPUT_SHAPE')
    need(value.get('schema') == 'clearpath-guard-input/1', 'GUARD_INPUT_SCHEMA')
    scope = _word(value.get('scope'))
    target = value.get('platform')
    need(target in ('macos', 'windows', 'linux'), 'GUARD_PLATFORM_UNSUPPORTED')
    mode = value.get('mode', 'egress')
    need(mode in ('egress', 'inbound') and (mode != 'inbound' or target == 'linux'), 'GUARD_MODE_UNSUPPORTED')
    policy = value.get('policy')
    need(policy in ('unified-v4', 'explicit-exceptions', 'domestic-v4', 'inbound-management'), 'GUARD_EXPLICIT_POLICY_REQUIRED')
    need(policy != 'domestic-v4', 'GUARD_DOMESTIC_DYNAMIC_POLICY_UNSUPPORTED')
    need((mode == 'inbound') == (policy == 'inbound-management'), 'GUARD_POLICY_MODE_MISMATCH')
    interfaces, tunnels = value.get('interfaces'), value.get('tunnels', [])
    need(type(interfaces) is list and 1 <= len(interfaces) <= 16 and type(tunnels) is list and len(tunnels) <= 16, 'GUARD_INTERFACES_REQUIRED')
    interfaces = [_interface(x, target == 'windows') for x in interfaces]
    tunnels = [_interface(x, target == 'windows') for x in tunnels]
    need(len(set(interfaces + tunnels)) == len(interfaces + tunnels), 'GUARD_INTERFACE_OVERLAP')
    nodes = value.get('nodes', [])
    need(type(nodes) is list and len(nodes) <= 64 and (mode == 'inbound' or nodes), 'GUARD_NODES_REQUIRED')
    normalized_nodes = []
    for node in nodes:
        need(type(node) is dict and set(node) == {'address', 'ports', 'protocol'}, 'GUARD_NODE_SHAPE')
        need(node['protocol'] in ('tcp', 'udp') and type(node['ports']) is list and 1 <= len(node['ports']) <= 64, 'GUARD_NODE_PROTOCOL')
        normalized_nodes.append({'address': _ipv4(node['address']), 'ports': sorted(set(_port(x) for x in node['ports'])), 'protocol': node['protocol']})
    exceptions = value.get('exceptions', [])
    need(type(exceptions) is list and len(exceptions) <= 128, 'GUARD_EXCEPTION_BUDGET')
    normalized_exceptions = []
    for entry in exceptions:
        need(type(entry) is dict and set(entry) == {'network', 'ports', 'protocol', 'direction', 'purpose'}, 'GUARD_EXCEPTION_SHAPE')
        need(entry['protocol'] in ('tcp', 'udp') and entry['direction'] in ('in', 'out') and
             type(entry['ports']) is list and 1 <= len(entry['ports']) <= 64, 'GUARD_EXCEPTION_PROTOCOL')
        need(type(entry['purpose']) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', entry['purpose']), 'GUARD_EXCEPTION_PURPOSE')
        normalized_exceptions.append(dict(entry, network=_ipv4(entry['network'], True), ports=sorted(set(_port(x) for x in entry['ports']))))
    if mode == 'inbound':
        need(any(x['direction'] == 'in' and x['protocol'] == 'tcp' for x in normalized_exceptions), 'GUARD_MANAGEMENT_EXCEPTION_REQUIRED')
    if policy == 'domestic-v4':
        need(any(x['direction'] == 'out' for x in normalized_exceptions), 'GUARD_DOMESTIC_EXCEPTIONS_REQUIRED')
    dns = value.get('bootstrap_dns', [])
    need(type(dns) is list and len(dns) <= 8, 'GUARD_DNS_BUDGET')
    dns = [_ipv4(x) for x in dns]
    seconds = value.get('fuse_seconds', 180)
    need(type(seconds) is int and 60 <= seconds <= 600, 'GUARD_FUSE_RANGE')
    disable = value.get('windows_disable_rules', [])
    need(type(disable) is list and len(disable) <= 4096 and all(type(x) is str and 0 < len(x) <= 256 and not any(ord(c) < 32 or c in '*?[]' for c in x) for x in disable), 'GUARD_INVALID_RULE_NAME')
    core = value.get('core_path')
    if target == 'windows' and mode == 'egress':
        need(type(core) is str and re.fullmatch(r'[A-Za-z]:\\[^\r\n"*?<>|]+\.exe', core) and '..' not in core.split('\\'), 'GUARD_WINDOWS_CORE_PATH_REQUIRED')
    else:
        need(core is None and not disable, 'GUARD_WINDOWS_FIELDS_ON_OTHER_PLATFORM')
    trusted_python = value.get('trusted_python', '/usr/bin/python3')
    need(type(trusted_python) is str and trusted_python.startswith('/') and not any(c in trusted_python for c in '\n\r\x00'), 'GUARD_TRUSTED_PYTHON_PATH')
    return {'schema': 'clearpath-guard-input/1', 'scope': scope, 'platform': target, 'mode': mode, 'policy': policy,
            'interfaces': interfaces, 'tunnels': tunnels, 'nodes': normalized_nodes, 'exceptions': normalized_exceptions,
            'bootstrap_dns': dns, 'core_path': core, 'windows_disable_rules': sorted(set(disable)),
            'fuse_seconds': seconds, 'trusted_python': trusted_python}


def render_pf(spec):
    need(spec['platform'] == 'macos' and spec['mode'] == 'egress', 'GUARD_PF_SCOPE')
    physical = '{ ' + ', '.join(spec['interfaces']) + ' }'
    lines = ['# Clearpath owned anchor; existing PF states are not globally flushed.']
    for node in spec['nodes']:
        lines.append('pass out quick on %s inet proto %s to %s port { %s } keep state' %
                     (physical, node['protocol'], node['address'], ', '.join(map(str, node['ports']))))
    for entry in spec['exceptions']:
        if entry['direction'] == 'out':
            lines.append('pass out quick on %s inet proto %s to %s port { %s } keep state' %
                         (physical, entry['protocol'], entry['network'], ', '.join(map(str, entry['ports']))))
    for address in spec['bootstrap_dns']:
        lines += ['pass out quick on %s inet proto { tcp, udp } to %s port 53 keep state' % (physical, address)]
    lines += ['pass out quick on %s inet proto udp from any port 68 to 255.255.255.255 port 67' % physical,
              'block drop out quick on %s all' % physical]
    return '\n'.join(lines) + '\n'


def render_nft(spec):
    need(spec['platform'] == 'linux', 'GUARD_NFT_SCOPE')
    table = 'clearpath_' + spec['scope'].lower().replace('-', '_')
    chain = 'input' if spec['mode'] == 'inbound' else 'output'
    lines = ['table inet %s {' % table, ' chain %s {' % chain,
             '  type filter hook %s priority 10; policy drop;' % chain,
             '  iifname "lo" accept' if chain == 'input' else '  oifname "lo" accept',
             '  ct state established,related accept']
    if chain == 'output':
        for tunnel in spec['tunnels']:
            lines.append('  oifname "%s" accept' % tunnel)
        for node in spec['nodes']:
            lines.append('  ip daddr %s %s dport { %s } accept' %
                         (node['address'], node['protocol'], ', '.join(map(str, node['ports']))))
        for address in spec['bootstrap_dns']:
            lines += ['  ip daddr %s %s dport 53 accept' % (address, proto) for proto in ('tcp', 'udp')]
        lines.append('  udp sport 68 udp dport 67 ip daddr 255.255.255.255 accept')
    else:
        lines.append('  udp sport 67 udp dport 68 accept')
    for entry in spec['exceptions']:
        if entry['direction'] == ('in' if chain == 'input' else 'out'):
            lines.append('  ip %s %s %s dport { %s } accept' %
                         ('saddr' if chain == 'input' else 'daddr', entry['network'], entry['protocol'], ', '.join(map(str, entry['ports']))))
    return '\n'.join(lines + [' }', '}']) + '\n'


def nft_document(spec):
    """Native JSON transaction also defines a crash-reconciliation expectation."""
    table = 'clearpath_' + spec['scope'].lower().replace('-', '_')
    chain = 'input' if spec['mode'] == 'inbound' else 'output'
    objects = [{'table': {'family': 'inet', 'name': table}},
               {'chain': {'family': 'inet', 'table': table, 'name': chain, 'type': 'filter',
                          'hook': chain, 'prio': 10, 'policy': 'drop'}}]
    def match(left, right, op='=='):
        return {'match': {'op': op, 'left': left, 'right': right}}
    def meta(key):
        return {'meta': {'key': key}}
    def payload(protocol, field):
        return {'payload': {'protocol': protocol, 'field': field}}
    def rule(expr):
        protocols = {entry['match']['left']['payload']['protocol'] for entry in expr
                     if isinstance(entry.get('match', {}).get('left'), dict) and 'payload' in entry['match']['left']}
        # Give libnftables the full protocol context explicitly. Otherwise its
        # implicit dependency matches may differ from the requested JSON AST.
        context = []
        if 'ip' in protocols:
            context.append(match(meta('nfproto'), 'ipv4'))
        for proto in ('tcp', 'udp'):
            if proto in protocols:
                context.append(match(meta('l4proto'), proto))
        objects.append({'rule': {'family': 'inet', 'table': table, 'chain': chain, 'expr': context + expr + [{'accept': None}]}})
    rule([match(meta('iifname' if chain == 'input' else 'oifname'), 'lo')])
    rule([match({'ct': {'key': 'state'}}, {'set': ['established', 'related']}, 'in')])
    if chain == 'output':
        for tunnel in spec['tunnels']:
            rule([match(meta('oifname'), tunnel)])
        for node in spec['nodes']:
            rule([match(payload('ip', 'daddr'), node['address']),
                  match(payload(node['protocol'], 'dport'), {'set': node['ports']}, 'in')])
        for address in spec['bootstrap_dns']:
            for proto in ('tcp', 'udp'):
                rule([match(payload('ip', 'daddr'), address), match(payload(proto, 'dport'), 53)])
        rule([match(payload('ip', 'daddr'), '255.255.255.255'), match(payload('udp', 'sport'), 68), match(payload('udp', 'dport'), 67)])
    else:
        rule([match(payload('udp', 'sport'), 67), match(payload('udp', 'dport'), 68)])
    for entry in spec['exceptions']:
        if entry['direction'] != ('in' if chain == 'input' else 'out'):
            continue
        network = ipaddress.ip_network(entry['network'])
        rule([match(payload('ip', 'saddr' if chain == 'input' else 'daddr'),
                    {'prefix': {'addr': str(network.network_address), 'len': network.prefixlen}}),
              match(payload(entry['protocol'], 'dport'), {'set': entry['ports']}, 'in')])
    return {'nftables': [{'add': item} for item in objects]}


def canonical_nft(document):
    def clean(value):
        if isinstance(value, list):
            return [clean(x) for x in value]
        if isinstance(value, dict):
            if set(value) == {'set'} and len(value['set']) == 1:
                return clean(value['set'][0])
            if set(value) == {'prefix'} and value['prefix'].get('len') in (32, 128):
                return value['prefix']['addr']
            result = {k: clean(v) for k, v in value.items() if k not in ('handle', 'index', 'position')}
            if set(result) == {'match'} and result['match'].get('op') in ('in', '=='):
                result['match']['op'] = 'member'
            return result
        return value
    items = []
    need(type(document) is dict and type(document.get('nftables')) is list, 'GUARD_NFT_INVALID_READBACK')
    for item in document['nftables']:
        if 'metainfo' in item:
            continue
        item = item.get('add', item)
        need(set(item) in ({'table'}, {'chain'}, {'rule'}), 'GUARD_NFT_UNKNOWN_READBACK')
        items.append(clean(item))
    return items


def canonical_pf(value):
    return '\n'.join(line.strip() for line in value.splitlines() if line.strip().startswith(('pass ', 'block ')))


def make_plan(value):
    spec = validate_input(value)
    rendered = render_pf(spec) if spec['platform'] == 'macos' else render_nft(spec) if spec['platform'] == 'linux' else None
    return {'schema': SCHEMA, 'created_at': stamp(), 'spec': spec, 'rules': rendered,
            'rules_sha256': digest(rendered.encode()) if rendered is not None else None,
            'runtime_sha256': digest(Path(__file__).read_bytes()),
            'windows_backend_sha256': digest(Path(__file__).with_name('system_guard_windows.ps1').read_bytes()) if spec['platform'] == 'windows' else None,
            'scope': 'owned_rules_only', 'network_verified': False,
            'limitations': ['existing_connections_not_terminated', 'new_interfaces_and_node_changes_require_replan',
                            'host_firewall_third_party_layers_not_certified']}


def validate_plan(value):
    need(type(value) is dict and value.get('schema') == SCHEMA, 'GUARD_PLAN_SCHEMA')
    regenerated = make_plan(value.get('spec'))
    for key in ('spec', 'rules', 'rules_sha256', 'runtime_sha256', 'windows_backend_sha256', 'scope', 'network_verified', 'limitations'):
        need(value.get(key) == regenerated[key], 'GUARD_PLAN_CONTENT_CHANGED')
    return value


def native_platform():
    return {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}.get(platform.system(), 'unsupported')


def windows_directory(common_data=False):
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if common_data:
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x23, None, 0, buffer)
        need(result == 0 and buffer.value, 'GUARD_WINDOWS_DIRECTORY_UNAVAILABLE')
    else:
        result = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        need(0 < result < len(buffer), 'GUARD_WINDOWS_DIRECTORY_UNAVAILABLE')
    return Path(buffer.value)


@contextmanager
def operation_lock(folder):
    """Serialize this tool's processes; does not exclude unrelated OS writers."""
    path = Path(folder) / '.operation.lock'
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'GUARD_LOCK_UNSAFE')
        if info.st_size == 0:
            os.write(fd, b'0')
            os.fsync(fd)
        if os.name == 'nt':
            import msvcrt
            _secure_windows_file(path)
            # The independent PowerShell expiry worker locks the same byte.
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(.1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if os.name == 'nt':
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _machine_identity():
    target = native_platform()
    if target == 'linux':
        p = Path('/etc/machine-id')
        info = p.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022 and info.st_size <= 128, 'GUARD_STABLE_DEVICE_ID_UNAVAILABLE')
        raw = p.read_bytes().strip()
        need(re.fullmatch(b'[0-9a-fA-F]{32}', raw), 'GUARD_STABLE_DEVICE_ID_UNAVAILABLE')
        return raw.lower()
    if target == 'macos':
        try:
            result = subprocess.run(['/usr/sbin/ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                capture_output=True, timeout=5, check=False, env={'PATH': '/usr/bin:/usr/sbin:/bin:/sbin', 'LC_ALL': 'C'})
        except (OSError, subprocess.SubprocessError):
            raise GuardError('GUARD_STABLE_DEVICE_ID_UNAVAILABLE') from None
        need(result.returncode == 0 and len(result.stdout) <= 65536, 'GUARD_STABLE_DEVICE_ID_UNAVAILABLE')
        match = re.search(rb'"IOPlatformUUID"\s*=\s*"([0-9a-fA-F-]{36})"', result.stdout)
        need(match, 'GUARD_STABLE_DEVICE_ID_UNAVAILABLE')
        return match[1].lower()
    if target == 'windows':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                value, kind = winreg.QueryValueEx(key, 'MachineGuid')
            need(kind == winreg.REG_SZ and re.fullmatch(r'[0-9a-fA-F-]{36}', value), 'GUARD_STABLE_DEVICE_ID_UNAVAILABLE')
            return value.lower().encode('ascii')
        except OSError:
            raise GuardError('GUARD_STABLE_DEVICE_ID_UNAVAILABLE') from None
    raise GuardError('GUARD_STABLE_DEVICE_ID_UNAVAILABLE')


def binding():
    return digest([native_platform(), digest(_machine_identity()),
                   str(getattr(os, 'geteuid', lambda: 'administrative_machine_scope')())])


class NativeHost:
    """Fixed native commands. runner injection is for tests, never a CLI flag."""
    def __init__(self, spec, runner=None, expected_backend_sha256=None):
        self.spec = validate_input(spec)
        self.runner = runner or subprocess.run
        self.platform = spec['platform']
        self.scope = spec['scope'].lower()
        self.table = 'clearpath_' + self.scope.replace('-', '_')
        self.anchor = 'com.apple/clearpath-' + self.scope
        self.label = 'com.clearpath.guard.' + self.scope
        self.expected_backend_sha256 = expected_backend_sha256

    def command(self, argv, data=None, allow_absent=False, combined=False):
        try:
            environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
            if self.platform == 'windows':
                system = windows_directory()
                environment = {'SystemRoot': str(system), 'WINDIR': str(system),
                    'PATH': str(system / 'System32'),
                    'PSModulePath': str(system / 'System32/WindowsPowerShell/v1.0/Modules')}
            result = self.runner(argv, input=data, capture_output=True, text=True, timeout=15,
                                 check=False, shell=False, env=environment, cwd=str(Path(argv[0]).parent))
        except (OSError, subprocess.SubprocessError):
            raise GuardError('GUARD_NATIVE_COMMAND_FAILED') from None
        need(len(result.stdout) <= 2 * 1024 * 1024 and len(result.stderr) <= 2 * 1024 * 1024, 'GUARD_NATIVE_OUTPUT_BUDGET')
        if result.returncode and allow_absent:
            return None
        need(result.returncode == 0, 'GUARD_NATIVE_COMMAND_FAILED')
        return result.stdout + ('\n' + result.stderr if combined else '')

    def root(self):
        if self.platform == 'macos':
            return Path('/Library/Application Support/Clearpath/guard') / self.scope
        if self.platform == 'linux':
            return Path('/var/lib/clearpath/guard') / self.scope
        return windows_directory(True) / 'Clearpath' / 'guard' / self.scope

    def check(self, folder):
        need(native_platform() == self.platform, 'GUARD_WRONG_NATIVE_PLATFORM')
        if self.platform != 'windows':
            need(os.geteuid() == 0, 'GUARD_ADMIN_REQUIRED')
        else:
            import ctypes
            need(ctypes.windll.shell32.IsUserAnAdmin(), 'GUARD_ADMIN_REQUIRED')
        need(Path(folder) == self.root(), 'GUARD_FIXED_PRIVATE_STATE_REQUIRED')
        for p in (Path(folder), *Path(folder).parents):
            if p.exists():
                need(not p.is_symlink() and (self.platform == 'windows' or (p.stat().st_uid == 0 and not p.stat().st_mode & 0o022)), 'GUARD_STATE_OWNER_OR_MODE')
        if self.platform == 'windows':
            # This is the shipped source captured and hash-checked in this
            # process, never a script found in an untrusted state directory.
            self._windows(folder, 'Audit', source=True)
        if self.platform != 'windows':
            original = Path(self.spec['trusted_python'])
            for entry in (original, *original.parents):
                info = entry.lstat()
                need(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022), 'GUARD_ROOT_OWNED_PYTHON_REQUIRED')
            executable = original.resolve(strict=True)
            need(executable.stat().st_uid == 0 and not executable.stat().st_mode & 0o022, 'GUARD_ROOT_OWNED_PYTHON_REQUIRED')
            for ancestor in executable.parents:
                need(ancestor.stat().st_uid == 0 and not ancestor.stat().st_mode & 0o022, 'GUARD_ROOT_OWNED_PYTHON_REQUIRED')
            self.command([str(original), '-I', '-c', 'import sys;raise SystemExit(0 if sys.version_info >= (3,9) else 2)'])

    def prepare(self, folder):
        folder = Path(folder)
        self.check(folder)
        if self.platform == 'windows':
            self._windows(folder, 'Secure', source=True)
        else:
            folder.mkdir(parents=True, mode=0o700, exist_ok=False)
        if self.platform != 'windows':
            os.chmod(folder, 0o700)
        if self.platform == 'macos':
            need(not (Path('/Library/LaunchDaemons') / (self.label + '.boot.plist')).exists(), 'GUARD_EXISTING_STARTUP_CONFLICT')
            need(not self.pf_token_path().exists(), 'GUARD_PF_TOKEN_CONFLICT')
        elif self.platform == 'linux':
            need(not Path('/etc/systemd/system/clearpath-guard-' + self.scope + '.service').exists(), 'GUARD_EXISTING_STARTUP_CONFLICT')
        self.install_runtime(folder)

    def install_runtime(self, folder):
        folder = Path(folder)
        private_write(folder / 'runtime.py', Path(__file__).read_bytes(), True)
        if self.platform == 'windows':
            private_write(folder / 'backend.ps1', Path(__file__).with_name('system_guard_windows.ps1').read_bytes(), True)
            private_write(folder / 'system_guard_windows.ps1', Path(__file__).with_name('system_guard_windows.ps1').read_bytes(), True)

    def secure(self, folder):
        if self.platform == 'windows':
            self._windows(folder, 'Secure')

    def pf_token_path(self):
        return Path('/private/var/run') / ('clearpath-guard-' + self.scope + '.pf-token')

    def _await_recovery(self, folder):
        state = read_json(Path(folder) / 'state.json')
        ready = Path(folder) / 'recovery-ready.json'
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if ready.exists():
                value = read_json(ready)
                if value.get('nonce') == state['recovery_nonce'] and value.get('binding') == state['binding']:
                    return
            time.sleep(.1)
        raise GuardError('GUARD_INDEPENDENT_RECOVERY_WORKER_NOT_READY')

    def _record_artifacts(self, folder, kind, artifacts):
        for path in artifacts:
            need(not Path(path).exists() and not Path(path).is_symlink(), 'GUARD_STARTUP_TARGET_EXISTS')
        record = {'schema': 'clearpath-guard-owned-files/1', 'files':
                  {str(path): digest(raw.encode() if isinstance(raw, str) else raw) for path, raw in artifacts.items()}}
        private_write(Path(folder) / (kind + '.files.json'), record, True)

    def _checked_artifacts(self, folder, kind):
        manifest = Path(folder) / (kind + '.files.json')
        if not manifest.exists():
            return []
        record = read_json(manifest)
        need(record.get('schema') == 'clearpath-guard-owned-files/1' and type(record.get('files')) is dict, 'GUARD_STARTUP_MANIFEST_INVALID')
        paths = []
        for name, expected in record['files'].items():
            p = Path(name)
            if self.platform == 'macos':
                allowed = p.parent == Path('/Library/LaunchDaemons') and p.name in (self.label + '.boot.plist', self.label + '.fuse.plist')
            else:
                base = 'clearpath-guard-' + self.scope
                allowed = p.parent == Path('/etc/systemd/system') and p.name in (base + '.service', base + '-fuse.service', base + '-fuse.timer')
            need(allowed, 'GUARD_STARTUP_MANIFEST_SCOPE')
            if p.exists():
                need(not p.is_symlink() and p.is_file() and digest(p.read_bytes()) == expected, 'GUARD_STARTUP_LATER_EDIT_CONFLICT')
                paths.append(p)
        return paths

    def _windows(self, folder, action, extra=None, source=False):
        exe = str(windows_directory() / 'System32/WindowsPowerShell/v1.0/powershell.exe')
        helper = Path(__file__).with_name('system_guard_windows.ps1') if source else Path(folder) / 'backend.ps1'
        need(not helper.is_symlink() and helper.is_file() and helper.stat().st_nlink == 1, 'GUARD_WINDOWS_BACKEND_IDENTITY')
        raw = helper.read_bytes()
        need(len(raw) <= MAX_INPUT, 'GUARD_WINDOWS_BACKEND_BUDGET')
        expected = self.expected_backend_sha256
        if expected is None:
            expected = digest(Path(__file__).with_name('system_guard_windows.ps1').read_bytes())
        need(digest(raw) == expected, 'GUARD_WINDOWS_BACKEND_HASH_CHANGED')
        if source:
            need(action in ('Secure', 'Audit') and not extra, 'GUARD_WINDOWS_SOURCE_ACTION')
            encoded_source = base64.b64encode(raw).decode('ascii')
            quoted_folder = str(folder).replace("'", "''")
            script = "& ([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s')))) -Action '%s' -StateDir '%s'" % (encoded_source, action, quoted_folder)
            encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            return self.command([exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded])
        return self.command([exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(helper),
                             '-Action', action, '-StateDir', str(folder)] + (extra or []))

    def snapshot(self, folder):
        if self.platform == 'macos':
            main = self.command(['/sbin/pfctl', '-sr'])
            need('anchor "com.apple/*"' in main, 'GUARD_PF_MAIN_ANCHOR_REQUIRED')
            rules = self.command(['/sbin/pfctl', '-a', self.anchor, '-sr'])
            return {'rules': canonical_pf(rules)}
        if self.platform == 'linux':
            tables = json.loads(self.command(['/usr/sbin/nft', '-j', 'list', 'tables']))
            present = any(x.get('table', {}).get('family') == 'inet' and x.get('table', {}).get('name') == self.table for x in tables['nftables'])
            if not present:
                return {'rules': None}
            raw = self.command(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', self.table])
            return {'rules': canonical_nft(json.loads(raw))}
        return json.loads(self._windows(folder, 'Snapshot'))

    def coverage(self, folder):
        if self.platform == 'macos':
            raw = self.command(['/usr/sbin/networksetup', '-listallhardwareports'])
            names = sorted(set(re.findall(r'^Device:\s*([A-Za-z][A-Za-z0-9_.-]*)\s*$', raw, re.M)))
            need(names, 'GUARD_PHYSICAL_INTERFACE_DISCOVERY_FAILED')
            return {'physical_interfaces': names, 'uncovered_interfaces': sorted(set(names) - set(self.spec['interfaces']))}
        if self.platform == 'linux':
            links = json.loads(self.command(['/usr/sbin/ip', '-j', 'link', 'show']))
            names = sorted(x['ifname'] for x in links if x['ifname'] != 'lo' and x['ifname'] not in self.spec['tunnels'])
            return {'observed_interfaces': names, 'missing_declared_interfaces': sorted(set(self.spec['interfaces']) - set(names))}
        value = json.loads(self._windows(folder, 'Coverage'))
        names = value['physical_interfaces']
        return {'physical_interfaces': sorted(names), 'uncovered_interfaces': sorted(set(names) - set(self.spec['interfaces']))}

    def validate(self, folder):
        coverage = self.coverage(folder)
        need(not coverage.get('uncovered_interfaces') and not coverage.get('missing_declared_interfaces'), 'GUARD_INTERFACE_SCOPE_INCOMPLETE')
        if self.platform == 'macos':
            parsed = self.command(['/sbin/pfctl', '-nv', '-a', self.anchor, '-f', str(Path(folder) / 'rules.conf')], combined=True)
            result = canonical_pf(parsed)
            need(result and 'block ' in result, 'GUARD_PF_NORMALIZED_READBACK_REQUIRED')
            return {'rules': result}
        elif self.platform == 'linux':
            self.command(['/usr/sbin/nft', '-j', '-c', '-f', str(Path(folder) / 'rules.nft.json')])
            return {'rules': canonical_nft(nft_document(self.spec))}
        else:
            self._windows(folder, 'Validate')
            return None  # Windows keeps a per-setter native rollback journal.

    def arm(self, folder):
        folder = Path(folder)
        seconds = self.spec['fuse_seconds']
        if self.platform == 'macos':
            plist = Path('/Library/LaunchDaemons') / (self.label + '.fuse.plist')
            need(not plist.exists(), 'GUARD_RECOVERY_TIMER_EXISTS')
            raw = plistlib.dumps({'Label': self.label + '.fuse', 'ProgramArguments': [self.spec['trusted_python'], '-I', str(folder / 'runtime.py'), '_expire', str(folder)],
                                  'StartInterval': 5, 'RunAtLoad': True})
            self._record_artifacts(folder, 'fuse', {plist: raw})
            private_write(plist, raw, True)
            self.command(['/bin/launchctl', 'bootstrap', 'system', str(plist)])
            self.command(['/bin/launchctl', 'print', 'system/' + self.label + '.fuse'])
            self._await_recovery(folder)
        elif self.platform == 'linux':
            unit = 'clearpath-guard-' + self.scope + '-fuse'
            # Persistent pending timer also covers a reboot before confirmation.
            service = '[Unit]\nDescription=Clearpath pending firewall rollback\n[Service]\nType=oneshot\nExecStart=%s -I %s _expire %s\n' % tuple(_systemd_arg(x) for x in [self.spec['trusted_python'], str(folder / 'runtime.py'), str(folder)])
            timer = '[Unit]\nDescription=Clearpath recovery timer\n[Timer]\nOnBootSec=5s\nOnUnitActiveSec=5s\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n'
            self._record_artifacts(folder, 'fuse', {Path('/etc/systemd/system/' + unit + '.service'): service,
                                                  Path('/etc/systemd/system/' + unit + '.timer'): timer})
            _new_system_file('/etc/systemd/system/' + unit + '.service', service)
            _new_system_file('/etc/systemd/system/' + unit + '.timer', timer)
            self.command(['/usr/bin/systemctl', 'daemon-reload'])
            self.command(['/usr/bin/systemctl', 'enable', '--now', unit + '.timer'])
            self.command(['/usr/bin/systemctl', 'is-active', '--quiet', unit + '.timer'])
            # OnBootSec may already be in the past; trigger the harmless readiness
            # worker explicitly rather than trusting an active timer label.
            self.command(['/usr/bin/systemctl', 'start', '--no-block', unit + '.service'])
            self._await_recovery(folder)
        else:
            self._windows(folder, 'Arm')

    def apply(self, folder):
        folder = Path(folder)
        if self.platform == 'macos':
            # Acquire only this tool's PF reference, never disable all PF.
            token_file = self.pf_token_path()
            need(not token_file.exists(), 'GUARD_PF_TOKEN_CONFLICT')
            enabled = self.command(['/sbin/pfctl', '-E'], combined=True)
            match = re.search(r'Token\s*:\s*(\d+)', enabled)
            need(match, 'GUARD_PF_TOKEN_UNAVAILABLE')
            try:
                private_write(token_file, match[1].encode(), True)
            except Exception:
                self.command(['/sbin/pfctl', '-X', match[1]])
                raise
            self.command(['/sbin/pfctl', '-a', self.anchor, '-f', str(folder / 'rules.conf')])
        elif self.platform == 'linux':
            self.command(['/usr/sbin/nft', '-j', '-f', str(folder / 'rules.nft.json')])
        else:
            self._windows(folder, 'Apply')

    def restore(self, folder, state):
        current = self.snapshot(folder)
        if self.platform != 'windows':
            acceptable = [state['before']]
            if state.get('desired') is not None:
                acceptable.append(state['desired'])
            if state.get('applied') is not None:
                acceptable.append(state['applied'])
            need(any(digest(current) == digest(x) for x in acceptable), 'GUARD_RESTORE_CONFLICT')
        if self.platform == 'macos':
            self.command(['/sbin/pfctl', '-a', self.anchor, '-F', 'rules'])
            token_file = self.pf_token_path()
            if token_file.exists():
                token = token_file.read_text().strip()
                need(re.fullmatch(r'\d+', token), 'GUARD_PF_TOKEN_INVALID')
                self.command(['/sbin/pfctl', '-X', token])
                token_file.unlink()
        elif self.platform == 'linux':
            if current['rules'] is not None:
                self.command(['/usr/sbin/nft', 'delete', 'table', 'inet', self.table])
        else:
            self._windows(folder, 'Restore')
        if state.get('persisted') or state.get('startup_pending'):
            self.unpersist(folder)

    def persist(self, folder):
        folder = Path(folder)
        if self.platform == 'macos':
            p = Path('/Library/LaunchDaemons') / (self.label + '.boot.plist')
            content = plistlib.dumps({'Label': self.label + '.boot', 'RunAtLoad': True,
                'ProgramArguments': [self.spec['trusted_python'], '-I', str(folder / 'runtime.py'), '_boot', str(folder)]})
            self._record_artifacts(folder, 'startup', {p: content})
            _new_system_file(p, content)
            # File is installed after confirm. Do not bootstrap and apply twice now.
        elif self.platform == 'linux':
            name = 'clearpath-guard-' + self.scope
            p = Path('/etc/systemd/system/' + name + '.service')
            content = '[Unit]\nDescription=Clearpath owned firewall\nAfter=local-fs.target\nBefore=network-pre.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=%s -I %s _boot %s\n[Install]\nWantedBy=multi-user.target\n' % tuple(_systemd_arg(x) for x in [self.spec['trusted_python'], str(folder / 'runtime.py'), str(folder)])
            self._record_artifacts(folder, 'startup', {p: content})
            _new_system_file(p, content)
            self.command(['/usr/bin/systemctl', 'daemon-reload'])
            self.command(['/usr/bin/systemctl', 'enable', name + '.service'])
        else:
            self._windows(folder, 'Persist')

    def unpersist(self, folder):
        checked = self._checked_artifacts(folder, 'startup') if self.platform != 'windows' else []
        if self.platform == 'macos':
            p = Path('/Library/LaunchDaemons') / (self.label + '.boot.plist')
            if p.exists():
                need(p in checked, 'GUARD_STARTUP_UNOWNED_CONFLICT')
                self.command(['/bin/launchctl', 'bootout', 'system', str(p)], allow_absent=True)
                p.unlink()
        elif self.platform == 'linux':
            name = 'clearpath-guard-' + self.scope
            p = Path('/etc/systemd/system/' + name + '.service')
            if p.exists():
                need(p in checked, 'GUARD_STARTUP_UNOWNED_CONFLICT')
                self.command(['/usr/bin/systemctl', 'disable', name + '.service'])
                p.unlink()
                self.command(['/usr/bin/systemctl', 'daemon-reload'])
        else:
            self._windows(folder, 'Unpersist')

    def persistence_status(self, folder):
        checked = self._checked_artifacts(folder, 'startup') if self.platform != 'windows' else []
        if self.platform == 'macos':
            p = Path('/Library/LaunchDaemons') / (self.label + '.boot.plist')
            return p in checked
        if self.platform == 'linux':
            unit = 'clearpath-guard-' + self.scope + '.service'
            return bool(checked) and self.command(['/usr/bin/systemctl', 'is-enabled', '--quiet', unit], allow_absent=True) is not None
        return True  # Windows setters are inherently persistent; recovery commits them.

    def disarm(self, folder):
        checked = self._checked_artifacts(folder, 'fuse') if self.platform != 'windows' else []
        if self.platform == 'macos':
            p = Path('/Library/LaunchDaemons') / (self.label + '.fuse.plist')
            if p.exists():
                need(p in checked, 'GUARD_RECOVERY_TIMER_UNOWNED_CONFLICT')
                self.command(['/bin/launchctl', 'bootout', 'system', str(p)], allow_absent=True)
                p.unlink()
        elif self.platform == 'linux':
            name = 'clearpath-guard-' + self.scope + '-fuse'
            timer = Path('/etc/systemd/system/' + name + '.timer')
            service = Path('/etc/systemd/system/' + name + '.service')
            changed = False
            if timer.exists():
                need(timer in checked, 'GUARD_RECOVERY_TIMER_UNOWNED_CONFLICT')
                self.command(['/usr/bin/systemctl', 'disable', '--now', name + '.timer'])
                timer.unlink()
                changed = True
            if service.exists():
                need(service in checked, 'GUARD_RECOVERY_TIMER_UNOWNED_CONFLICT')
                service.unlink()
                changed = True
            if changed:
                self.command(['/usr/bin/systemctl', 'daemon-reload'])
        else:
            self._windows(folder, 'Disarm')


def _systemd_arg(value):
    need('\n' not in value and '\r' not in value and '\x00' not in value, 'GUARD_UNIT_ARGUMENT')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def _new_system_file(path, content):
    p = Path(path)
    private_write(p, content.encode() if isinstance(content, str) else content, True)
    os.chmod(p, 0o644)


def _load_state(folder):
    value = read_json(Path(folder) / 'state.json', 4 * 1024 * 1024)
    need(value.get('schema') == STATE_SCHEMA and value.get('binding') == binding(), 'GUARD_STATE_BINDING')
    validate_plan(value['plan'])
    need(value.get('plan_sha256') == digest(value['plan']), 'GUARD_STATE_PLAN_CHANGED')
    return value


def activate(plan, folder, host):
    """Transaction orchestration; host injection never bypasses CLI native admission."""
    validate_plan(plan)
    folder = Path(folder)
    if not folder.exists():
        host.prepare(folder)
    else:
        host.check(folder)
        need((folder / 'state.json').is_file(), 'GUARD_EXISTING_STATE_DIRECTORY_UNBOUND')
    with operation_lock(folder):
        return _activate_locked(plan, folder, host)


def _activate_locked(plan, folder, host):
    state_path = folder / 'state.json'
    if state_path.exists():
        previous = _load_state(folder)
        need(previous['phase'] in ('restored', 'uninstalled'), 'GUARD_ACTIVE_STATE_EXISTS')
        need(digest(host.snapshot(folder)) == digest(previous['before']), 'GUARD_REACTIVATION_BASELINE_DRIFT')
        history = folder / ('history-' + uuid.uuid4().hex)
        history.mkdir(mode=0o700)
        for name in ('state.json', 'plan.json', 'runtime.py', 'backend.ps1', 'rules.conf', 'rules.nft.json',
                     'system_guard_windows.ps1',
                     'native-journal.json', 'native-restored.json', 'recovery-ready.json', 'recovery-challenge.json',
                     'fuse.files.json', 'startup.files.json'):
            p = folder / name
            if p.exists():
                need(not p.is_symlink(), 'GUARD_STATE_SYMLINK')
                os.replace(str(p), str(history / name))
        host.install_runtime(folder)
    private_write(folder / 'plan.json', plan, True)
    if hasattr(host, 'secure'):
        host.secure(folder)
    if plan['rules'] is not None:
        private_write(folder / 'rules.conf', plan['rules'].encode(), True)
    if plan['spec']['platform'] == 'linux':
        private_write(folder / 'rules.nft.json', nft_document(plan['spec']), True)
    before = host.snapshot(folder)
    if plan['spec']['platform'] != 'windows':
        need(before.get('rules') in (None, ''), 'GUARD_EXISTING_OWNED_RULES_REQUIRE_RECOVERY')
    state = {'schema': STATE_SCHEMA, 'binding': binding(), 'plan': plan, 'plan_sha256': digest(plan),
             'phase': 'prepared', 'created_at': stamp(), 'expires_at': time.time() + plan['spec']['fuse_seconds'],
             'recovery_nonce': uuid.uuid4().hex,
             'before': before, 'applied': None, 'persisted': False}
    if hasattr(host, 'coverage'):
        state['coverage'] = host.coverage(folder)
    private_write(folder / 'state.json', state, True)
    state['desired'] = host.validate(folder)
    private_write(folder / 'state.json', state)
    host.arm(folder)
    state['phase'] = 'armed'
    private_write(folder / 'state.json', state)
    try:
        state['phase'] = 'applying'
        private_write(folder / 'state.json', state)
        host.apply(folder)
        observed = host.snapshot(folder)
        if state['desired'] is not None:
            need(digest(observed) == digest(state['desired']), 'GUARD_APPLY_READBACK_MISMATCH')
        state['applied'] = observed
        state['phase'] = 'pending_confirmation'
        private_write(folder / 'state.json', state)
    except Exception:
        # Durable applying intent stays available. Unknown mutation is never replayed.
        state['phase'] = 'apply_uncertain'
        private_write(folder / 'state.json', state)
        raise
    return {'status': 'applied_pending_confirmation', 'exit_code': 2, 'plan_sha256': digest(plan),
            'transaction_id': state['recovery_nonce'],
            'recovery_armed': True, 'persistent': False, 'network_verified': False,
            'pending_native_persistence': plan['spec']['platform'] == 'windows',
            'existing_connections_terminated': False}


def finish(folder, expected, host, verification, persist, transaction_id=None):
    with operation_lock(folder):
        return _finish_locked(folder, expected, host, verification, persist, transaction_id)


def _finish_locked(folder, expected, host, verification, persist, transaction_id=None):
    state = _load_state(folder)
    need(state['plan_sha256'] == expected, 'GUARD_EXPECTED_PLAN_DIGEST')
    need(transaction_id is None or state.get('recovery_nonce') == transaction_id, 'GUARD_TRANSACTION_MISMATCH')
    need(state['phase'] == 'pending_confirmation' and time.time() < state['expires_at'], 'GUARD_CONFIRMATION_EXPIRED_OR_UNAVAILABLE')
    need(type(verification) is dict and verification.get('schema') == 'clearpath-guard-verification/1' and
         verification.get('plan_sha256') == expected and verification.get('normal_path') == 'observed' and
         verification.get('management_path') == 'observed', 'GUARD_VERIFICATION_REQUIRED')
    need(digest(host.snapshot(folder)) == digest(state['applied']), 'GUARD_CONFIGURATION_DRIFT')
    if 'coverage' in state:
        need(host.coverage(folder) == state['coverage'], 'GUARD_INTERFACE_DRIFT')
    # Keep the independently armed rollback eligible until persistence and its
    # readback finish. A partial startup write is covered by startup_pending.
    state['phase'] = 'confirming'
    state['verification'] = verification
    state['startup_pending'] = bool(persist)
    private_write(Path(folder) / 'state.json', state)
    if persist:
        host.persist(folder)
        need(host.persistence_status(folder), 'GUARD_STARTUP_READBACK_FAILED')
        state['persisted'] = True
    need(time.time() < state['expires_at'], 'GUARD_CONFIRMATION_EXPIRED_DURING_COMMIT')
    state['startup_pending'] = False
    state['phase'] = 'confirmed'
    private_write(Path(folder) / 'state.json', state)
    host.disarm(folder)
    return {'status': 'configuration_confirmed', 'persistent': persist, 'network_verified': False,
            'verification_source': 'operator_supplied_not_independently_authenticated', 'exit_code': 0}


def deactivate(folder, expected, host, uninstall=False):
    with operation_lock(folder):
        return _deactivate_locked(folder, expected, host, uninstall)


def _deactivate_locked(folder, expected, host, uninstall=False):
    state = _load_state(folder)
    need(state['plan_sha256'] == expected, 'GUARD_EXPECTED_PLAN_DIGEST')
    already_restored = state['phase'] in ('restored', 'uninstalled')
    if already_restored:
        need(digest(host.snapshot(folder)) == digest(state['before']), 'GUARD_RESTORED_BASELINE_DRIFT')
        if not uninstall or state['phase'] == 'uninstalled':
            return {'status': state['phase'], 'changes': [], 'exit_code': 0}
    else:
        host.restore(folder, state)
        restored = host.snapshot(folder)
        need(digest(restored) == digest(state['before']), 'GUARD_RESTORE_READBACK_MISMATCH')
        state['phase'] = 'restored'
        state['persisted'] = False
        state['startup_pending'] = False
        private_write(Path(folder) / 'state.json', state)
        host.disarm(folder)
    if uninstall:
        # Keep the receipt and baseline for audit/recovery; delete only executable copies.
        for name in ('runtime.py', 'backend.ps1', 'system_guard_windows.ps1', 'rules.conf', 'rules.nft.json'):
            p = Path(folder) / name
            if p.exists():
                p.unlink()
        state['phase'] = 'uninstalled'
        private_write(Path(folder) / 'state.json', state)
    return {'status': state['phase'], 'runtime_restored': True, 'startup_restored': True,
            'private_receipt_retained': True, 'network_verified': False, 'exit_code': 0}


def register_commands(subparsers):
    for command in COMMANDS:
        if command == 'guard-launch':
            continue
        p = subparsers.add_parser(command, help='Scoped native firewall plan, switch and independently armed recovery')
        if command in ('guard-plan', 'guard-inspect'):
            p.add_argument('--input', required=True)
            p.add_argument('--output', required=True)
        elif command == 'guard-export':
            p.add_argument('--plan', required=True)
            p.add_argument('--plan-sha256', required=True)
            p.add_argument('--out', required=True)
            p.add_argument('--check-plan', help='Optional exact approved bootstrap network plan for customer-terminal checks')
        else:
            p.add_argument('--state-dir', required=True)
            if command == 'guard-on':
                p.add_argument('--plan', required=True)
            if command != 'guard-status':
                p.add_argument('--plan-sha256', required=True)
                p.add_argument('--allow-system-change', action='store_true')
                p.add_argument('--control-channel-independent', action='store_true')
                p.add_argument('--recovery-ready', action='store_true')
            if command == 'guard-confirm':
                p.add_argument('--verification-file', required=True)
                p.add_argument('--persist', action='store_true')
                p.add_argument('--transaction-id', help='Optional pending-generation binding; never authorization')
    import guard_handoff
    guard_handoff.register_commands(subparsers)


def run(c, args):
    try:
        command = args.command
        if command == 'guard-launch':
            import guard_handoff
            return guard_handoff.run(c, args)
        if command == 'guard-plan':
            plan = make_plan(c.load_json(c.read_bytes(args.input, MAX_INPUT)))
            c.write_new(args.output, c.encode(plan))
            return {'status': 'guard_plan_written', 'plan_sha256': digest(plan), 'system_changes': False,
                    'network_requests': 0, 'platform': plan['spec']['platform'], 'requires_native_acceptance': True}
        if command == 'guard-inspect':
            import tempfile
            spec = validate_input(c.load_json(c.read_bytes(args.input, MAX_INPUT)))
            need(native_platform() == spec['platform'], 'GUARD_WRONG_NATIVE_PLATFORM')
            host = NativeHost(spec)
            with tempfile.TemporaryDirectory(prefix='clearpath-guard-inspect-') as temporary:
                folder = Path(temporary)
                if spec['platform'] == 'windows':
                    private_write(folder / 'plan.json', make_plan(spec), True)
                    private_write(folder / 'backend.ps1', Path(__file__).with_name('system_guard_windows.ps1').read_bytes(), True)
                snapshot = host.snapshot(folder)
            c.write_new(args.output, c.encode({'schema': 'clearpath-guard-inspection/1', 'snapshot': snapshot,
                                             'binding': binding(), 'observed_at': stamp(), 'spec_sha256': digest(spec)}))
            return {'status': 'guard_private_inspection_written', 'system_changes': False, 'network_requests': 0,
                    'native_firewall_read_only': True, 'network_verified': False}
        if command == 'guard-export':
            plan = validate_plan(c.load_json(c.read_bytes(args.plan, MAX_INPUT)))
            need(digest(plan) == args.plan_sha256, 'GUARD_EXPECTED_PLAN_DIGEST')
            import config_recovery
            out = config_recovery._private_dir(c, args.out, create=True)
            private_write(out / 'plan.json', plan, True)
            private_write(out / 'system_guard.py', Path(__file__).read_bytes(), True)
            private_write(out / 'system_guard_windows.ps1', Path(__file__).with_name('system_guard_windows.ps1').read_bytes(), True)
            import guard_handoff
            checks = c.load_json(c.read_bytes(args.check_plan, MAX_INPUT)) if getattr(args, 'check_plan', None) else None
            launchers = guard_handoff.export_launchers(c, plan, out, checks)
            return dict(launchers, status='guard_bundle_exported', system_changes=False,
                        plan_sha256=digest(plan), network_requests=0, private_bundle=True)
        if command in MUTATING_COMMANDS:
            need(args.allow_system_change and args.control_channel_independent and args.recovery_ready,
                 'GUARD_EXPLICIT_CHANGE_AND_INDEPENDENT_RECOVERY_REQUIRED')
        state = None if command == 'guard-on' else _load_state(args.state_dir)
        plan = validate_plan(c.load_json(c.read_bytes(args.plan, MAX_INPUT))) if command == 'guard-on' else state['plan']
        if command != 'guard-status':
            need(digest(plan) == args.plan_sha256, 'GUARD_EXPECTED_PLAN_DIGEST')
        host = NativeHost(plan['spec'], expected_backend_sha256=plan.get('windows_backend_sha256'))
        host.check(args.state_dir)
        if command == 'guard-on':
            return activate(plan, args.state_dir, host)
        if command == 'guard-confirm':
            return finish(args.state_dir, args.plan_sha256, host,
                          c.load_json(c.read_bytes(args.verification_file, 65536)), args.persist,
                          getattr(args, 'transaction_id', None))
        if command in ('guard-off', 'guard-uninstall'):
            return deactivate(args.state_dir, args.plan_sha256, host, command == 'guard-uninstall')
        current = host.snapshot(args.state_dir)
        inactive = state['phase'] in ('restored', 'uninstalled')
        expected_native = state['before'] if inactive else state.get('applied')
        matches = expected_native is not None and digest(current) == digest(expected_native)
        coverage_matches = 'coverage' not in state or host.coverage(args.state_dir) == state['coverage']
        return {'status': state['phase'], 'configuration_matches': matches, 'persistent': state['persisted'],
                'interface_coverage_matches': coverage_matches,
                'protection_configured': matches and coverage_matches and state['phase'] == 'confirmed',
                'network_verified': False, 'exit_code': 0 if matches and (inactive or (coverage_matches and state['phase'] == 'confirmed')) else 2,
                'plan_sha256': state['plan_sha256'], 'next_step': 'Verify actual paths and selected lifecycle events separately.'}
    except GuardError as error:
        raise c.SetupError(str(error)) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise c.SetupError('GUARD_IO_OR_STATE_INVALID') from None


def _worker(action, folder):
    state = _load_state(folder)
    host = NativeHost(state['plan']['spec'], expected_backend_sha256=state['plan'].get('windows_backend_sha256'))
    host.check(folder)
    if action == '_expire':
        # Readiness acknowledgement deliberately precedes the operation lock:
        # activate holds that lock while verifying the independent worker.
        private_write(Path(folder) / 'recovery-ready.json', {'nonce': state['recovery_nonce'], 'binding': state['binding']})
    with operation_lock(folder):
        state = _load_state(folder)
        if action == '_expire':
            if state['phase'] not in ('confirmed', 'restored', 'uninstalled') and time.time() >= state['expires_at']:
                _deactivate_locked(folder, state['plan_sha256'], host)
        elif action == '_boot':
            need(state['phase'] == 'confirmed' and state['persisted'], 'GUARD_BOOT_NOT_CONFIRMED')
            plan = state['plan']
            if plan['spec']['platform'] == 'linux':
                need(digest(read_json(Path(folder) / 'rules.nft.json')) == digest(nft_document(plan['spec'])), 'GUARD_RETAINED_RULES_CHANGED')
            else:
                rule_file = Path(folder) / 'rules.conf'
                need(not rule_file.is_symlink() and digest(rule_file.read_bytes()) == plan['rules_sha256'], 'GUARD_RETAINED_RULES_CHANGED')
            desired = host.validate(folder)
            need(digest(desired) == digest(state['desired']), 'GUARD_NATIVE_COMPILER_DRIFT')
            before = host.snapshot(folder)
            need(before.get('rules') in ('', None), 'GUARD_BOOT_OWNED_STATE_CONFLICT')
            attempt = {'schema': 'clearpath-guard-boot-intent/1', 'plan_sha256': state['plan_sha256'],
                       'observed_at': stamp(), 'before': before, 'desired': desired}
            private_write(Path(folder) / ('boot-' + uuid.uuid4().hex + '.intent.json'), attempt, True)
            host.apply(folder)
            observed = host.snapshot(folder)
            need(digest(observed) == digest(state['desired']), 'GUARD_BOOT_READBACK_MISMATCH')
            state['applied'] = observed
            state['last_boot_apply'] = stamp()
            private_write(Path(folder) / 'state.json', state)


if __name__ == '__main__':
    # Only the retained root-owned recovery/startup worker is standalone.
    try:
        if len(sys.argv) == 8 and sys.argv[1] == '_recover':
            need(set(sys.argv[5:]) == {'--allow-system-change', '--control-channel-independent', '--recovery-ready'}, 'GUARD_EXPLICIT_CHANGE_AND_INDEPENDENT_RECOVERY_REQUIRED')
            need(sys.argv[3] == '--plan-sha256', 'GUARD_EXPECTED_PLAN_DIGEST')
            folder, expected = sys.argv[2], sys.argv[4]
            state = _load_state(folder)
            host = NativeHost(state['plan']['spec'], expected_backend_sha256=state['plan'].get('windows_backend_sha256'))
            host.check(folder)
            print(json.dumps(deactivate(folder, expected, host)))
        else:
            need(len(sys.argv) == 3 and sys.argv[1] in ('_expire', '_boot'), 'GUARD_INTERNAL_WORKER_ONLY')
            _worker(sys.argv[1], sys.argv[2])
    except Exception:
        sys.exit(2)
