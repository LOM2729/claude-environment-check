"""Explicit Claude-data quarantine with independent backups and replay-safe recovery.

No discovery runs on import. The command host accepts only selected, typed Claude
locations; the portable engine never follows links or erases quarantine/backup.
Stopped-writer attestation and repeated process observations are accident barriers,
not mandatory OS exclusion (in particular, Node-hosted CLI processes can be missed).
"""
from contextlib import ExitStack, closing, contextmanager, nullcontext
import datetime as dt
import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import time
import uuid

import config_recovery as storage
import windows_cleanup as windows

COMMANDS = ('cleanup-inventory', 'cleanup-plan', 'cleanup-quarantine',
            'cleanup-reconcile', 'cleanup-restore')
MUTATING_COMMANDS = ('cleanup-quarantine', 'cleanup-restore')
SCHEMA = 'clearpath-scoped-cleanup/1'
MAX_ROOTS, MAX_ITEMS, MAX_BYTES, MAX_DEPTH = 16, 4096, 64 * 1024 * 1024, 32
MAX_DOCUMENT = 4 * 1024 * 1024
KINDS = {
    'cli-cache': ('cache', ('cache', '.cache')),
    'cli-logs': ('logs', ('debug',)),
    'cli-login': ('login', ('.credentials.json',)),
    'cli-history': ('history', ('history.jsonl', 'projects', 'todos')),
    'cli-configuration': ('configuration', ('settings.json', 'settings.local.json', 'skills', 'plugins', 'hooks', 'agents')),
    'desktop-cache': ('cache', ('Cache', 'Code Cache', 'GPUCache', 'DawnCache', 'DawnGraphiteCache', 'DawnWebGPUCache')),
    'desktop-persistent': ('persistent', ('',)),
}
CATEGORIES = tuple(sorted({v[0] for v in KINDS.values()}))


def register_commands(sub):
    p = sub.add_parser('cleanup-inventory', help='List only explicit Claude roots; no content scan or process check')
    p.add_argument('--config-dir')
    p.add_argument('--desktop-dir')
    p.add_argument('--target-alias', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('cleanup-plan', help='Budget selected data before independent backup; default cache only')
    p.add_argument('--request', required=True)
    p.add_argument('--allow-category', action='append', choices=CATEGORIES, default=[])
    p.add_argument('--out', required=True)
    p = sub.add_parser('cleanup-quarantine', help='Back up and move exactly reviewed roots; never permanently delete')
    p.add_argument('--plan', required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--allow-write', action='store_true')
    p.add_argument('--writers-stopped', action='store_true')
    p.add_argument('--out', required=True, help='New private operation on the same volume, outside every selected root')
    p = sub.add_parser('cleanup-reconcile', help='Observe original/quarantine locations before any retry or restore')
    p.add_argument('--operation', required=True)
    p.add_argument('--operation-sha256', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('cleanup-restore', help='Restore only absent originals and unchanged isolated objects')
    p.add_argument('--observation', required=True)
    p.add_argument('--observation-sha256', required=True)
    p.add_argument('--allow-write', action='store_true')
    p.add_argument('--writers-stopped', action='store_true')
    p.add_argument('--out', required=True)


def _alias(c, value):
    c.require(type(value) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', value), 'CLEANUP_TARGET_ALIAS_REQUIRED')
    return value


def _pin(c, value):
    c.require(type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value), 'CLEANUP_DIGEST_REQUIRED')


def _overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def _path(c, value, missing=False, directory=None):
    c.require(type(value) in (str, Path) or isinstance(value, Path), 'CLEANUP_ABSOLUTE_PATH_REQUIRED')
    p = Path(value)
    c.require(p.is_absolute() and '..' not in p.parts and '\x00' not in str(p), 'CLEANUP_ABSOLUTE_PATH_REQUIRED')
    # Reuse the fixed-drive/reparse/ancestor-link checks of text transactions.
    if os.name == 'nt':
        windows.lexical_path(c, p)
        if directory is None:
            with windows.pinned_directory(c, p.parent):
                try:
                    directory = stat.S_ISDIR(p.lstat().st_mode)
                except FileNotFoundError:
                    directory = False
                except OSError:
                    raise c.SetupError('CLEANUP_WINDOWS_OBJECT_UNAVAILABLE') from None
                return storage._safe_path(c, p, directory=directory, missing=missing)[0]
    if directory is None:
        try:
            directory = stat.S_ISDIR(p.lstat().st_mode)
        except FileNotFoundError:
            directory = False
    return storage._safe_path(c, p, directory=directory, missing=missing)[0]


def _parent(c, p):
    p = _path(c, p, directory=True)
    if os.name == 'nt':
        return windows.parent(c, p)
    s = p.lstat()
    return {'path': str(p), 'device': s.st_dev, 'inode': s.st_ino,
            'mode': stat.S_IMODE(s.st_mode), 'uid': getattr(s, 'st_uid', None)}


def _budget(c, value):
    c.require(value['items'] <= MAX_ITEMS and value['bytes'] <= MAX_BYTES, 'CLEANUP_BUDGET_EXCEEDED')


def _open_content(c, p, directory=False):
    """POSIX ancestor-relative opens; portable fallbacks remain detect-and-fail."""
    _path(c, p, directory=directory)
    if os.name != 'posix' or os.open not in os.supports_dir_fd:
        c.require(not directory, 'CLEANUP_DIRECTORY_HANDLE_UNAVAILABLE')
        return os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    fd = os.open(p.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        result = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW |
                         (os.O_DIRECTORY if directory else os.O_NONBLOCK), dir_fd=fd)
        return result
    finally:
        os.close(fd)


def _read_content(c, p, expected):
    if os.name == 'nt':
        return windows.read(c, p, expected, MAX_BYTES)
    fd = _open_content(c, p)
    try:
        before = os.fstat(fd)
        c.require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                  storage._fingerprint(before) == expected, 'CLEANUP_SOURCE_CHANGED')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_BYTES + 1)
        c.require(len(raw) <= MAX_BYTES and storage._fingerprint(os.fstat(fd)) == expected and
                  storage._fingerprint(p.lstat()) == expected, 'CLEANUP_SOURCE_CHANGED')
        return raw
    finally:
        os.close(fd)


def _names(c, p, expected, remaining):
    if os.name != 'posix':
        raise c.SetupError('CLEANUP_NATIVE_DIRECTORY_TRAVERSAL_UNAVAILABLE')
    fd = _open_content(c, p, directory=True)
    try:
        c.require(storage._fingerprint(os.fstat(fd)) == expected, 'CLEANUP_SOURCE_CHANGED')
        with os.scandir(fd) as iterator:
            names = []
            for entry in iterator:
                c.require(len(names) < remaining, 'CLEANUP_BUDGET_EXCEEDED')
                names.append(entry.name)
            names.sort()
        c.require(storage._fingerprint(os.fstat(fd)) == expected, 'CLEANUP_SOURCE_CHANGED')
        return names
    finally:
        os.close(fd)


def _scan(c, value, counter=None, depth=0):
    """Bounded snapshots include directory identities and every regular file hash."""
    root = _path(c, value)
    counter = counter if counter is not None else {'items': 0, 'bytes': 0}
    if os.name == 'nt':
        return windows.scan(c, root, counter, (MAX_ITEMS, MAX_BYTES, MAX_DEPTH), depth)
    entries = []
    root_device = root.lstat().st_dev
    def visit(p, relative, level):
        c.require(level <= MAX_DEPTH, 'CLEANUP_DEPTH_EXCEEDED')
        c.require(p.name not in ('.git', '.codex'), 'CLEANUP_SOURCE_OR_CODEX_PROTECTED')
        before = p.lstat()
        c.require(not stat.S_ISLNK(before.st_mode) and not (getattr(before, 'st_file_attributes', 0) & 0x400), 'CLEANUP_LINK_REJECTED')
        c.require(before.st_dev == root_device, 'CLEANUP_MOUNT_BOUNDARY_REJECTED')
        c.require(stat.S_ISREG(before.st_mode) or stat.S_ISDIR(before.st_mode), 'CLEANUP_SPECIAL_FILE_REJECTED')
        if os.name != 'nt':
            c.require(before.st_uid == os.getuid() and before.st_gid == root.lstat().st_gid, 'CLEANUP_OWNER_MISMATCH')
        counter['items'] += 1
        if stat.S_ISREG(before.st_mode):
            c.require(before.st_nlink == 1, 'CLEANUP_HARDLINK_REJECTED')
            counter['bytes'] += before.st_size
        _budget(c, counter)
        metadata = storage._metadata(p)
        row = {'relative': relative, 'type': 'directory' if stat.S_ISDIR(before.st_mode) else 'file',
               'identity': storage._fingerprint(before), 'metadata': metadata}
        if row['type'] == 'file':
            row['sha256'] = c.sha(_read_content(c, p, row['identity']))
        else:
            names = _names(c, p, row['identity'], MAX_ITEMS - counter['items'])
            row['children'] = names
        entries.append(row)
        if row['type'] == 'directory':
            for name in row['children']:
                visit(p / name, name if relative == '.' else relative + '/' + name, level + 1)
        c.require(storage._fingerprint(before) == storage._fingerprint(p.lstat()), 'CLEANUP_SOURCE_CHANGED')
        c.require(storage._metadata(p) == metadata, 'CLEANUP_METADATA_CHANGED')
    visit(root, '.', depth)
    return entries


def _same_after_move(expected, current):
    # Rename updates the root ctime; record its new full snapshot after commit.
    # Never discard child identity/content/metadata changes.
    if len(expected) != len(current):
        return False
    import copy
    a, b = copy.deepcopy(expected), copy.deepcopy(current)
    for rows in (a, b):
        for row in rows:
            if row['relative'] == '.':
                row['identity'].pop('ctime_ns', None)
    return a == b


def _content(snapshot):
    return [{'relative': x['relative'], 'type': x['type'],
             'sha256': x.get('sha256'), 'children': x.get('children')} for x in snapshot]


def _pin_directory(c, p, expected=None):
    return windows.pinned_directory(c, p, expected) if os.name == 'nt' else nullcontext()


def _present(p):
    try:
        p.lstat()
    except FileNotFoundError:
        return False
    return True


def _private_dir(c, value, create=False):
    p = _path(c, value, missing=create, directory=True)
    with _pin_directory(c, p.parent if create else p):
        return storage._private_dir(c, p, create=create)


def _write_bytes(c, p, data):
    if os.name == 'nt':
        windows.write_new(c, p, data)
    else:
        storage._write(c, p, data)


def _write(c, p, value, parent=None):
    data = value if isinstance(value, bytes) else c.encode(value)
    c.require(len(data) <= MAX_DOCUMENT, 'CLEANUP_DOCUMENT_BUDGET_EXCEEDED')
    with _pin_directory(c, p.parent, parent):
        _write_bytes(c, p, data)
    return c.sha(data)


def _load(c, folder, name, pin):
    _pin(c, pin)
    folder = _private_dir(c, folder)
    path = _path(c, folder / name)
    raw = windows.read(c, path, None, MAX_DOCUMENT) if os.name == 'nt' else c.read_bytes(path, MAX_DOCUMENT)
    c.require(c.sha(raw) == pin, 'CLEANUP_DOCUMENT_CHANGED')
    value = c.load_json(raw)
    c.require(type(value) is dict and value.get('schema') == SCHEMA, 'CLEANUP_DOCUMENT_INVALID')
    return folder, value


class NativeHost:
    """Fixed command host; explicit API fixtures may substitute it only in tests."""
    def binding(self):
        return storage._binding()

    def supported(self, c):
        c.require((platform.system(), os.name) in (('Darwin', 'posix'), ('Windows', 'nt')),
                  'CLEANUP_NATIVE_PLATFORM_UNSUPPORTED')

    def validate_scope(self, c, request):
        """Only the current selected CLI root and fixed Desktop locations mutate."""
        self.supported(c)
        home = windows.known_folder(c, 'profile') if os.name == 'nt' else Path.home()
        configured = os.environ.get('CLAUDE_CONFIG_DIR')
        expected = Path(configured).expanduser().absolute() if configured else home / '.claude'
        if request.get('config_root') is not None:
            if os.name == 'nt':
                c.require(home in expected.parents, 'CLEANUP_WINDOWS_CONFIG_OUTSIDE_PROFILE')
            c.require(Path(request['config_root']) == expected, 'CLEANUP_EFFECTIVE_CONFIG_ROOT_MISMATCH')
        if request.get('desktop_root') is not None:
            if os.name == 'nt':
                roaming = windows.known_folder(c, 'roaming')
                c.require(home in roaming.parents, 'CLEANUP_WINDOWS_ROAMING_OUTSIDE_PROFILE')
                allowed = (roaming / 'Claude',)
            else:
                allowed = (home / 'Library/Application Support/Claude', home / 'Library/Caches/Claude')
            c.require(Path(request['desktop_root']) in allowed, 'CLEANUP_DESKTOP_ROOT_UNSUPPORTED')

    def guard(self, c):
        self.supported(c)
        if os.name == 'nt':
            with closing(windows.process_images(c)) as images:
                for name in images:
                    c.require(name.casefold() not in ('claude.exe', 'claude-code.exe', 'claudecode.exe',
                                                     'claudedesktop.exe', 'claude-desktop.exe'),
                              'CLEANUP_TARGET_WRITER_RUNNING')
            return
        command = ['/bin/ps', '-axo', 'comm=']
        try:
            done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                  timeout=5, check=False, shell=False)
            c.require(done.returncode == 0 and 0 < len(done.stdout) <= 1024 * 1024, 'CLEANUP_PROCESS_STATE_UNAVAILABLE')
            text = done.stdout.decode('utf-8', 'strict')
        except (OSError, UnicodeError, subprocess.SubprocessError):
            raise c.SetupError('CLEANUP_PROCESS_STATE_UNAVAILABLE') from None
        for line in text.splitlines():
            name = Path(line.strip().split('","')[0].strip('"')).name.lower()
            c.require(not (name in ('claude', 'claude.exe', 'claude-code', 'claude-code.exe') or
                           name.startswith('claude helper') or '/claude.app/' in line.lower()), 'CLEANUP_TARGET_WRITER_RUNNING')


def _validate_request(c, request, allowed, existing=True):
    c.require(type(request) is dict and set(request) <= {'schema', 'target_alias', 'config_root', 'desktop_root', 'roots', 'protected'} and
              request.get('schema') == 'claude-cleanup-scope/1', 'CLEANUP_SCOPE_INVALID')
    _alias(c, request.get('target_alias'))
    roots = request.get('roots')
    c.require(type(roots) is list and 1 <= len(roots) <= MAX_ROOTS, 'CLEANUP_ROOT_COUNT_INVALID')

    def scope_path(value, directory=None, missing=False):
        if os.name == 'nt' and not existing:
            # A receipt can name a replaced or missing parent. Reconciliation
            # verifies its identity before touching any selected child.
            c.require(isinstance(value, (str, Path)), 'CLEANUP_ABSOLUTE_PATH_REQUIRED')
            return windows.lexical_path(c, Path(value))
        return _path(c, value, directory=directory, missing=missing)

    contexts = {}
    for key in ('config_root', 'desktop_root'):
        if request.get(key) is not None:
            contexts[key] = scope_path(request[key], directory=True, missing=not existing)
            c.require(contexts[key] != Path.home() and len(contexts[key].parts) > 2, 'CLEANUP_WHOLE_HOME_REJECTED')
    requested_protected = request.get('protected', [])
    c.require(type(requested_protected) is list and len(requested_protected) <= 64, 'CLEANUP_PROTECTED_SCOPE_INVALID')
    protected = [scope_path(x, missing=True) for x in requested_protected]
    # These are protection identities, not an invitation to scan the whole home.
    homes = (Path.home(), windows.known_folder(c, 'profile')) if os.name == 'nt' else (Path.home(),)
    protected += [home / name for home in dict.fromkeys(homes) for name in ('.codex', '.agents')]
    selected = []
    for row in roots:
        c.require(type(row) is dict and set(row) == {'kind', 'path'} and row['kind'] in KINDS, 'CLEANUP_ROOT_KIND_INVALID')
        category, suffixes = KINDS[row['kind']]
        c.require(category in allowed, 'CLEANUP_CATEGORY_NOT_SELECTED')
        context = contexts.get('config_root' if row['kind'].startswith('cli-') else 'desktop_root')
        c.require(context is not None, 'CLEANUP_CONTEXT_REQUIRED')
        p = scope_path(row['path'], missing=not existing)
        c.require(any(p == context / suffix for suffix in suffixes), 'CLEANUP_ROOT_OUTSIDE_TYPED_SCOPE')
        c.require(not any(_overlap(p, x) for x in protected), 'CLEANUP_PROTECTED_PATH_OVERLAP')
        c.require(not any(_overlap(p, x['path_object']) for x in selected), 'CLEANUP_ROOT_OVERLAP')
        # Projects/history can contain source repositories; a Git marker always wins.
        selected.append({'path_object': p, 'path': str(p), 'kind': row['kind'], 'category': category})
    return selected, protected


def inventory(c, config_dir, desktop_dir, target_alias, output):
    _alias(c, target_alias)
    c.require(config_dir or desktop_dir, 'CLEANUP_EXPLICIT_CONTEXT_REQUIRED')
    found = []
    for kind, (category, names) in KINDS.items():
        source = config_dir if kind.startswith('cli-') else desktop_dir
        if source is None:
            continue
        context = _path(c, source, directory=True)
        for name in names:
            p = context / name
            # lstat only; never traverse or open candidate contents here.
            try:
                p.lstat()
            except FileNotFoundError:
                continue
            _path(c, p)
            found.append({'kind': kind, 'category': category, 'path': str(p), 'selected_by_default': category == 'cache'})
    folder = _private_dir(c, output, create=True)
    pin = _write(c, folder / 'inventory.private.json', {'schema': SCHEMA, 'kind': 'inventory',
                 'target_alias': target_alias, 'entries': found, 'created_at': c.now(), 'authorization_saved': False})
    return {'status': 'inventory_written', 'exit_code': 0, 'candidate_count': len(found),
            'inventory_sha256': pin, 'target_content_read': False, 'system_changes_performed': False,
            'network_requests': 0}


def plan(c, request, output, allowed=(), host=None):
    host = host or NativeHost()
    host.supported(c)
    allowed = set(allowed) | {'cache'}
    c.require(allowed <= set(CATEGORIES), 'CLEANUP_CATEGORY_INVALID')
    selected, protected = _validate_request(c, request, allowed)
    host.validate_scope(c, request)
    output = _path(c, output, missing=True, directory=True)
    c.require(not any(_overlap(output, row['path_object']) for row in selected), 'CLEANUP_OUTPUT_OVERLAP')
    counter = {'items': 0, 'bytes': 0}
    roots = []
    for index, row in enumerate(selected):
        p = row.pop('path_object')
        snapshot = _scan(c, p, counter)
        c.require(not any(Path(x['relative']).name in ('.git', '.codex') for x in snapshot), 'CLEANUP_SOURCE_OR_CODEX_PROTECTED')
        roots.append(dict(row, index=index, parent=_parent(c, p.parent), snapshot=snapshot))
    value = {'schema': SCHEMA, 'kind': 'plan', 'id': uuid.uuid4().hex,
             'created_at': c.now(), 'binding': host.binding(), 'target_alias': request['target_alias'],
             'scope': request, 'allowed_categories': sorted(allowed), 'roots': roots,
             'protected': [str(x) for x in protected], 'budget': counter,
             'authorization_saved': False, 'writers_exclusion': 'operator_attestation_and_detect_only',
             'node_hosted_cli_detection': 'not_guaranteed'}
    c.require(len(c.encode(value)) <= MAX_DOCUMENT, 'CLEANUP_DOCUMENT_BUDGET_EXCEEDED')
    folder = _private_dir(c, output, create=True)
    pin = _write(c, folder / 'plan.private.json', value)
    return {'status': 'cleanup_plan_written', 'exit_code': 0, 'plan_sha256': pin,
            'selected_roots': len(roots), 'items': counter['items'], 'bytes': counter['bytes'],
            'system_changes_performed': False, 'target_data_changed': False, 'network_requests': 0,
            'authorization_saved': False}


def _load_plan(c, folder, pin, host):
    folder, value = _load(c, folder, 'plan.private.json', pin)
    c.require(value.get('kind') == 'plan' and value.get('binding') == host.binding(), 'CLEANUP_TARGET_BINDING_CHANGED')
    selected, _ = _validate_request(c, value.get('scope'), set(value.get('allowed_categories', [])), existing=False)
    c.require(len(selected) == len(value.get('roots', [])), 'CLEANUP_PLAN_INVALID')
    for index, (selected_root, root) in enumerate(zip(selected, value['roots'])):
        c.require(root.get('path') == str(selected_root['path_object']) and root.get('kind') == selected_root['kind'] and
                  root.get('index') == index and type(root.get('snapshot')) is list and root['snapshot'], 'CLEANUP_PLAN_INVALID')
        for item in root['snapshot']:
            relative = item.get('relative')
            c.require(type(relative) is str and (relative == '.' or
                      (relative and not relative.startswith('/') and '\\' not in relative and
                       all(part not in ('', '.', '..') for part in relative.split('/')))), 'CLEANUP_PLAN_INVALID')
            c.require(item.get('type') in ('file', 'directory') and type(item.get('identity')) is dict,
                      'CLEANUP_PLAN_INVALID')
    return folder, value


@contextmanager
def _locks(c, roots):
    if os.name == 'nt':
        with ExitStack() as stack:
            for row in sorted(roots, key=lambda r: r['path'].casefold()):
                path = Path(row['path'])
                key = hashlib.sha256(str(path).casefold().encode()).hexdigest()[:24]
                stack.enter_context(windows.lock(c, path.parent / ('.clearpath-cleanup-' + key + '.lock'), row['parent']))
            yield
        return
    locks = []
    try:
        for row in sorted(roots, key=lambda r: r['path']):
            parent = _path(c, Path(row['path']).parent, directory=True)
            name = '.clearpath-cleanup-' + hashlib.sha256(row['path'].encode()).hexdigest()[:24] + '.lock'
            path = parent / name
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            except OSError:
                raise c.SetupError('CLEANUP_LOCK_EXISTS_OR_UNAVAILABLE') from None
            info = os.fstat(fd)
            os.close(fd)
            locks.append((path, info.st_dev, info.st_ino))
        yield
    finally:
        for path, device, inode in locks:
            try:
                info = path.lstat()
                if (info.st_dev, info.st_ino) == (device, inode):
                    path.unlink()
            except OSError:
                pass


def _copy_backup(c, source, dest, expected, parent=None):
    with _pin_directory(c, dest.parent, parent):
        c.require(not _present(dest), 'CLEANUP_BACKUP_EXISTS')
        for row in expected:
            relative = row['relative']
            target = dest if relative == '.' else dest / relative
            origin = source if relative == '.' else source / relative
            if row['type'] == 'directory':
                if os.name == 'nt':
                    _private_dir(c, target, create=True)
                else:
                    target.mkdir(mode=0o700)
            else:
                raw = _read_content(c, origin, row['identity'])
                c.require(c.sha(raw) == row['sha256'], 'CLEANUP_SOURCE_CHANGED')
                with _pin_directory(c, target.parent):
                    _write_bytes(c, target, raw)
        # Every backup is independent (not hardlinked), bounded and fully rehashed.
        c.require(_content(_scan(c, dest)) == _content(expected), 'CLEANUP_BACKUP_INTEGRITY_MISMATCH')


def _observations(c, operation):
    rows = []
    folder = _path(c, operation['operation_path'], directory=True)
    storage_parents = operation.get('storage_parents', {})

    def observed_snapshot(path, expected_parent):
        with _pin_directory(c, path.parent, expected_parent):
            return _scan(c, path) if _present(path) else None

    for item in operation['roots']:
        original, isolated = Path(item['path']), folder / 'quarantine' / str(item['index'])
        parent = _parent(c, original.parent)
        parent_matches = parent == item['parent']
        # A replacement directory at the same spelling is a different target;
        # do not even inspect its children under the old cleanup scope.
        a = observed_snapshot(original, parent) if parent_matches else None
        b = observed_snapshot(isolated, storage_parents.get('quarantine'))
        backup = folder / 'backup' / str(item['index'])
        backup_snapshot = observed_snapshot(backup, storage_parents.get('backup'))
        backup_ok = backup_snapshot is not None and _content(backup_snapshot) == _content(item['snapshot'])
        if not parent_matches:
            state = 'parent_conflict'
        elif a is None and b is not None and _same_after_move(item['snapshot'], b):
            state = 'isolated' if backup_ok else 'backup_conflict'
        elif b is None and a is not None and _same_after_move(item['snapshot'], a):
            state = 'original_present'
        elif a is None and b is None:
            state = 'missing_both'
        else:
            state = 'conflict'
        rows.append({'index': item['index'], 'state': state, 'original_snapshot': a,
                     'isolated_snapshot': b, 'backup_intact': backup_ok,
                     'original_parent': parent})
    return rows


def _move(c, source, target, expected, source_parent, target_parent, mover):
    if mover is not None:
        mover(source, target)  # API-only synthetic interruption hook.
    elif os.name == 'nt':
        windows.move(c, source, target, expected, source_parent, target_parent, (MAX_ITEMS, MAX_BYTES, MAX_DEPTH))
    else:
        os.rename(source, target)


def quarantine(c, folder, pin, output, allow=False, stopped=False, host=None, mover=None):
    host = host or NativeHost()
    host.supported(c)
    c.require(allow and stopped, 'CLEANUP_CURRENT_WRITE_AND_STOPPED_CONFIRMATION_REQUIRED')
    folder, value = _load_plan(c, folder, pin, host)
    host.validate_scope(c, value['scope'])
    try:
        created = dt.datetime.fromisoformat(value['created_at'])
        current = dt.datetime.fromisoformat(c.now())
        c.require(created.tzinfo is not None and current.tzinfo is not None and
                  0 <= (current - created).total_seconds() <= 600, 'CLEANUP_PLAN_EXPIRED')
    except (ValueError, KeyError, TypeError):
        raise c.SetupError('CLEANUP_PLAN_TIME_INVALID') from None
    output = _path(c, output, missing=True, directory=True)
    c.require(not any(_overlap(output, Path(row['path'])) for row in value['roots']) and
              not _overlap(output, folder), 'CLEANUP_OPERATION_OVERLAP')
    if os.name == 'nt':
        volume = windows.volume(c, output.parent)
        c.require(all(row['parent'].get('volume') == volume for row in value['roots']), 'CLEANUP_SAME_VOLUME_REQUIRED')
    else:
        c.require(all(Path(row['path']).lstat().st_dev == output.parent.stat().st_dev for row in value['roots']), 'CLEANUP_SAME_VOLUME_REQUIRED')
    host.guard(c)
    counter = {'items': 0, 'bytes': 0}
    for row in value['roots']:
        c.require(_parent(c, Path(row['path']).parent) == row['parent'] and _scan(c, row['path'], counter) == row['snapshot'], 'CLEANUP_SOURCE_CHANGED')
    dest = _private_dir(c, output, create=True)
    for name in ('backup', 'quarantine', 'journal'):
        _private_dir(c, dest / name, create=True)
    operation = {'schema': SCHEMA, 'kind': 'operation', 'id': uuid.uuid4().hex,
                 'created_at': c.now(), 'binding': host.binding(), 'target_alias': value['target_alias'],
                 'operation_path': str(dest), 'plan_path': str(folder), 'plan_sha256': pin,
                 'roots': value['roots'], 'authorization_saved': False}
    parents = {}
    if os.name == 'nt':
        parents = {name: _parent(c, dest / name) for name in ('.', 'backup', 'quarantine', 'journal')}
        operation['storage_parents'] = parents
    operation_pin = _write(c, dest / 'operation.private.json', operation, parent=parents.get('.'))
    attempted, done, stage, error = 0, 0, 'backup', None
    try:
        with _locks(c, value['roots']):
            # Entire selected set is budgeted and backed up before its first move.
            for row in value['roots']:
                host.guard(c)
                c.require(_scan(c, row['path']) == row['snapshot'], 'CLEANUP_SOURCE_CHANGED')
                _copy_backup(c, Path(row['path']), dest / 'backup' / str(row['index']), row['snapshot'], parents.get('backup'))
                c.require(_scan(c, row['path']) == row['snapshot'], 'CLEANUP_SOURCE_CHANGED')
            for row in value['roots']:
                host.guard(c)
                source = Path(row['path'])
                c.require(_parent(c, source.parent) == row['parent'] and _scan(c, source) == row['snapshot'], 'CLEANUP_SOURCE_CHANGED')
                target = dest / 'quarantine' / str(row['index'])
                stage = 'prepared'
                _write(c, dest / 'journal' / ('%04d.prepared.json' % row['index']),
                       {'schema': SCHEMA, 'index': row['index'], 'operation_sha256': operation_pin, 'action': 'quarantine'},
                       parent=parents.get('journal'))
                stage = 'rename_attempted'
                attempted += 1
                with _pin_directory(c, target.parent, parents.get('quarantine')):
                    c.require(not _present(target), 'CLEANUP_QUARANTINE_CONFLICT')
                _move(c, source, target, row['snapshot'], row['parent'], parents.get('quarantine'), mover)
                storage._sync_dir(source.parent)
                storage._sync_dir(target.parent)
                stage = 'readback'
                moved = _scan(c, target)
                c.require(not _present(source) and _same_after_move(row['snapshot'], moved), 'CLEANUP_MOVE_READBACK_FAILED')
                host.guard(c)
                _write(c, dest / 'journal' / ('%04d.done.json' % row['index']),
                       {'schema': SCHEMA, 'index': row['index'], 'operation_sha256': operation_pin,
                        'action': 'quarantine', 'isolated_snapshot': moved},
                       parent=parents.get('journal'))
                done += 1
            stage = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        error = str(exc) if isinstance(exc, c.SetupError) else 'CLEANUP_IO_OR_INTERRUPTED'
    result = {'status': 'quarantined' if error is None else 'partial_or_unconfirmed', 'exit_code': 0 if error is None else 2,
              'operation_id': operation['id'], 'operation_sha256': operation_pin,
              'selected_roots': len(value['roots']), 'completed_roots': done, 'attempted_roots': attempted,
              'stage': stage, 'reason_code': error, 'changes_state': 'isolated' if error is None else 'reconcile_required',
              'target_data_changed': bool(attempted), 'permanent_deletion': False, 'network_requests': 0,
              'writer_exclusion': 'operator_attestation_and_detect_only', 'node_hosted_cli_detection': 'not_guaranteed',
              'next_step': '保留私有备份与操作目录；需要恢复时先 cleanup-reconcile，再审阅精确恢复。'}
    try:
        _write(c, dest / 'result.json', result, parent=parents.get('.'))
    except Exception:
        result.update(status='partial_or_unconfirmed', exit_code=2, reason_code='CLEANUP_RESULT_WRITE_FAILED', changes_state='reconcile_required')
    return result


def _operation(c, folder, pin, host):
    folder, operation = _load(c, folder, 'operation.private.json', pin)
    c.require(operation.get('kind') == 'operation' and operation.get('binding') == host.binding() and
              operation.get('operation_path') == str(folder), 'CLEANUP_OPERATION_BINDING_CHANGED')
    c.require(type(operation.get('id')) is str and re.fullmatch(r'[a-f0-9]{32}', operation['id']),
              'CLEANUP_OPERATION_INVALID')
    _, plan_value = _load_plan(c, operation['plan_path'], operation['plan_sha256'], host)
    c.require(plan_value['roots'] == operation.get('roots'), 'CLEANUP_OPERATION_PLAN_CHANGED')
    for name in ('backup', 'quarantine', 'journal'):
        _path(c, folder / name, directory=True)
    if os.name == 'nt':
        parents = operation.get('storage_parents')
        c.require(type(parents) is dict and set(parents) == {'.', 'backup', 'quarantine', 'journal'},
                  'CLEANUP_OPERATION_INVALID')
        for name, expected in parents.items():
            _private_dir(c, folder / name)
            c.require(_parent(c, folder / name) == expected, 'CLEANUP_OPERATION_STORAGE_CHANGED')
    return folder, operation


def reconcile(c, folder, pin, output, host=None):
    host = host or NativeHost()
    host.supported(c)
    folder, operation = _operation(c, folder, pin, host)
    observed = _observations(c, operation)
    value = {'schema': SCHEMA, 'kind': 'observation', 'created_at': c.now(),
             'binding': host.binding(), 'operation_path': str(folder), 'operation_sha256': pin,
             'operation_id': operation['id'], 'roots': observed, 'authorization_saved': False}
    output = _path(c, output, missing=True, directory=True)
    c.require(not _overlap(output, folder) and not _overlap(output, Path(operation['plan_path'])) and
              not any(_overlap(output, Path(x['path'])) for x in operation['roots']), 'CLEANUP_OBSERVATION_OUTPUT_OVERLAP')
    dest = _private_dir(c, output, create=True)
    digest = _write(c, dest / 'observation.private.json', value)
    states = [x['state'] for x in observed]
    return {'status': 'observed', 'exit_code': 0 if all(x in ('isolated', 'original_present') for x in states) else 2,
            'observation_sha256': digest, 'isolated_roots': states.count('isolated'),
            'original_present_roots': states.count('original_present'),
            'conflict_roots': sum(x not in ('isolated', 'original_present') for x in states),
            'target_data_changed': False, 'network_requests': 0,
            'restoration_authorized': False}


def restore(c, observation_folder, pin, output, allow=False, stopped=False, host=None, mover=None):
    host = host or NativeHost()
    host.supported(c)
    c.require(allow and stopped, 'CLEANUP_CURRENT_WRITE_AND_STOPPED_CONFIRMATION_REQUIRED')
    _, record = _load(c, observation_folder, 'observation.private.json', pin)
    c.require(record.get('kind') == 'observation' and record.get('binding') == host.binding(), 'CLEANUP_OBSERVATION_INVALID')
    folder, operation = _operation(c, record['operation_path'], record['operation_sha256'], host)
    current = _observations(c, operation)
    c.require(current == record.get('roots'), 'CLEANUP_OBSERVATION_CHANGED')
    c.require(all(x['state'] in ('isolated', 'original_present') for x in current), 'CLEANUP_RESTORE_CONFLICT')
    c.require(any(x['state'] == 'isolated' for x in current), 'CLEANUP_NOTHING_TO_RESTORE')
    output = _path(c, output, missing=True, directory=True)
    c.require(not any(_overlap(output, Path(row['path'])) for row in operation['roots']) and
              not _overlap(output, folder) and not _overlap(output, Path(operation['plan_path'])), 'CLEANUP_RESTORE_OUTPUT_OVERLAP')
    dest = _private_dir(c, output, create=True)
    parents = operation.get('storage_parents', {})
    journal_parent = _parent(c, dest) if os.name == 'nt' else None
    restore_id = uuid.uuid4().hex
    restored, attempted, error, stage = 0, 0, None, 'prepared'
    try:
        with _locks(c, operation['roots']):
            for root, observed in zip(operation['roots'], current):
                if observed['state'] == 'original_present':
                    continue
                host.guard(c)
                source = folder / 'quarantine' / str(root['index'])
                target = Path(root['path'])
                with _pin_directory(c, target.parent, observed['original_parent']):
                    c.require(not _present(target), 'CLEANUP_RESTORE_DESTINATION_EXISTS')
                c.require(_parent(c, target.parent) == observed['original_parent'] and
                          _scan(c, source) == observed['isolated_snapshot'], 'CLEANUP_OBSERVATION_CHANGED')
                c.require(_content(_scan(c, folder / 'backup' / str(root['index']))) == _content(root['snapshot']), 'CLEANUP_BACKUP_INTEGRITY_MISMATCH')
                stage = 'prepared'
                _write(c, dest / ('%04d.prepared.json' % root['index']),
                       {'schema': SCHEMA, 'action': 'restore', 'index': root['index'],
                        'operation_sha256': record['operation_sha256'], 'observation_sha256': pin}, parent=journal_parent)
                stage = 'rename_attempted'
                attempted += 1
                _move(c, source, target, observed['isolated_snapshot'], parents.get('quarantine'),
                      observed['original_parent'], mover)
                storage._sync_dir(source.parent)
                storage._sync_dir(target.parent)
                stage = 'readback'
                c.require(not _present(source) and _same_after_move(observed['isolated_snapshot'], _scan(c, target)), 'CLEANUP_RESTORE_READBACK_FAILED')
                host.guard(c)
                _write(c, dest / ('%04d.done.json' % root['index']),
                       {'schema': SCHEMA, 'action': 'restore', 'index': root['index'], 'restore_id': restore_id}, parent=journal_parent)
                restored += 1
            stage = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        error = str(exc) if isinstance(exc, c.SetupError) else 'CLEANUP_IO_OR_INTERRUPTED'
    result = {'status': 'restored' if error is None else 'partial_or_unconfirmed', 'exit_code': 0 if error is None else 2,
              'operation_id': operation['id'], 'restore_id': restore_id, 'stage': stage, 'reason_code': error,
              'restored_roots': restored, 'attempted_roots': attempted,
              'target_data_changed': bool(attempted), 'changes_state': 'restored' if error is None else 'reconcile_required',
              'permanent_deletion': False, 'network_requests': 0,
              'next_step': '保留双方材料；中断后用原操作重新对账，不能重放旧观察或覆盖新增数据。'}
    try:
        _write(c, dest / 'result.json', result, parent=journal_parent)
    except Exception:
        result.update(status='partial_or_unconfirmed', exit_code=2, reason_code='CLEANUP_RESULT_WRITE_FAILED', changes_state='reconcile_required')
    return result


def run(c, args):
    if args.command == 'cleanup-inventory':
        return inventory(c, args.config_dir, args.desktop_dir, args.target_alias, args.out)
    if args.command == 'cleanup-plan':
        request = c.load_json(c.read_bytes(args.request, MAX_DOCUMENT))
        return plan(c, request, args.out, args.allow_category)
    if args.command == 'cleanup-quarantine':
        return quarantine(c, args.plan, args.plan_sha256, args.out, args.allow_write, args.writers_stopped)
    if args.command == 'cleanup-reconcile':
        return reconcile(c, args.operation, args.operation_sha256, args.out)
    if args.command == 'cleanup-restore':
        return restore(c, args.observation, args.observation_sha256, args.out, args.allow_write, args.writers_stopped)
    raise c.SetupError('CLEANUP_COMMAND_UNKNOWN')
