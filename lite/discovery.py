"""Bounded, read-only discovery of Clash text profiles; never contacts a client.

The returned paths are private service inputs. ``active`` means a unique profile
is selected in allowlisted on-disk metadata, not that a running core adopted it.
No filename, profile name, subscription URL, or parser error is exposed as a label.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import sys

import claude_setup as config

MAX_ENTRIES = 512
MAX_FILES = 64
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 256 * 1024
EXTENSIONS = {'.yaml', '.yml', '.json'}
SKIP_NAMES = {'profiles.yaml', 'verge.yaml', 'settings.yaml', 'settings.json'}
SELECTION_EVIDENCE = 'clash_verge_profiles_current'


class _Unsafe(Exception):
    pass


class _TooLarge(Exception):
    pass


def _fixed_local(path):
    value = str(path)
    if not path.is_absolute() or value.startswith(('\\\\', '//')):
        return False
    if path.parts[:2] in (('/', 'Volumes'), ('/', 'Network'), ('/', 'net')):
        return False
    if os.name == 'nt':
        # Fixed disks only; no UNC, mapped remote drive, or removable media probe.
        import ctypes
        from ctypes import wintypes
        get_type = ctypes.windll.kernel32.GetDriveTypeW
        get_type.argtypes = [wintypes.LPCWSTR]
        get_type.restype = wintypes.UINT
        return get_type(path.anchor) == 3
    return True


def _common_fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns)


def _fingerprint(info):
    return (*_common_fingerprint(info), info.st_ctime_ns)


def _safe_path(path, directory=False):
    if not _fixed_local(path) or '..' in path.parts:
        raise _Unsafe()
    chain = []
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise _Unsafe()
        if part != path or directory:
            if not stat.S_ISDIR(info.st_mode):
                raise _Unsafe()
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _Unsafe()
        # Directory timestamps legitimately change; their identity must not.
        chain.append((info.st_dev, info.st_ino, info.st_mode))
    return chain, info


def _open_local(path, directory=False):
    """Use no-follow handles for every ancestor where dir_fd is supported."""
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    flags |= getattr(os, 'O_NONBLOCK', 0)
    if directory:
        flags |= getattr(os, 'O_DIRECTORY', 0)
    if os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'):
        parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in path.parts[1:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=parent)
                os.close(parent)
                parent = next_fd
            return os.open(path.name, flags, dir_fd=parent)
        finally:
            os.close(parent)
    return os.open(path, flags)


def _read(path, limit):
    chain, before = _safe_path(path)
    if before.st_size > limit:
        raise _TooLarge()
    fd = _open_local(path)
    try:
        opened = os.fstat(fd)
        # Windows path stat and fstat can use different ctime domains
        # (cpython#157671). Compare ctime only within the same API below.
        if _common_fingerprint(before) != _common_fingerprint(opened):
            raise _Unsafe()
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise _TooLarge()
        if _fingerprint(opened) != _fingerprint(os.fstat(fd)):
            raise _Unsafe()
        final_chain, final = _safe_path(path)
        if chain != final_chain or _fingerprint(before) != _fingerprint(final):
            raise _Unsafe()
        return data
    finally:
        os.close(fd)


def _locations(home, platform, environ):
    roots = [(home / '.config/clash', 'Clash', False),
             (home / '.config/mihomo', 'Mihomo', False),
             (home / '.config/clash-verge', 'Clash Verge', True)]
    names = [('io.github.clash-verge-rev.clash-verge-rev', 'Clash Verge Rev', True),
             ('io.github.clash-verge-rev.clash-verge', 'Clash Verge Rev', True),
             ('io.github.clash-verge.clash-verge', 'Clash Verge', True),
             ('com.clash-verge.clash-verge', 'Clash Verge', True)]
    if platform == 'darwin':
        support = home / 'Library/Application Support'
        roots.extend((support / name, label, metadata) for name, label, metadata in names)
        roots.append((support / 'com.metacubex.ClashX.meta', 'ClashX Meta', False))
    elif platform == 'win32':
        base = Path(environ.get('APPDATA', str(home / 'AppData/Roaming')))
        roots.extend((base / name, label, metadata) for name, label, metadata in names)
        roots.extend([(base / 'clash-verge', 'Clash Verge', True),
                      (base / 'Clash for Windows', 'Clash for Windows', False)])
    return roots


def _selected(root):
    """Only current UID and its local file in Clash Verge profiles.yaml matter."""
    data = _read(root / 'profiles.yaml', MAX_METADATA_BYTES)
    metadata = config.parse_config(data, 'yaml')
    current = metadata.get('current')
    items = metadata.get('items')
    if not isinstance(current, str) or not current or not isinstance(items, list):
        raise _Unsafe()
    matches = [item for item in items if isinstance(item, dict) and item.get('uid') == current]
    if len(matches) != 1:
        raise _Unsafe()
    filename = matches[0].get('file')
    if (not isinstance(filename, str) or not filename or filename.startswith('.')
            or '/' in filename or '\\' in filename or ':' in filename
            or Path(filename).suffix.lower() not in EXTENSIONS):
        raise _Unsafe()
    return root / 'profiles' / filename


def _supported(obj):
    """Exclude settings, node-only subscriptions, and empty merge fragments."""
    rules = obj.get('rules')
    nodes = obj.get('proxies')
    if not isinstance(rules, list) or not rules or not all(isinstance(x, str) and x for x in rules):
        return False
    if isinstance(nodes, list) and nodes and all(
            isinstance(x, dict) and isinstance(x.get('name'), str) and x['name']
            and isinstance(x.get('type'), str) and x['type'] for x in nodes):
        return True
    providers = obj.get('proxy-providers')
    groups = obj.get('proxy-groups')
    if not isinstance(groups, list):
        return False
    for group in groups:
        if not isinstance(group, dict) or not group.get('name') or not group.get('type'):
            continue
        uses = group.get('use')
        if (isinstance(providers, dict) and isinstance(uses, list)
                and any(isinstance(x, str) and isinstance(providers.get(x), dict) for x in uses)):
            return True
    return False


def discover(home=None, platform=None, environ=None):
    """Return candidates, fixed warning codes and a scan-limit indicator.

    Candidate keys: id, path (service-private), label, client, active,
    selection_evidence. Metadata selection never authorizes an import or write.
    """
    home = Path.home() if home is None else Path(home)
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    warnings, candidates, seen, folders, selected = set(), [], set(), set(), set()
    entries = reads = total = 0
    limited = False
    for root, client, has_metadata in _locations(home, platform, environ):
        if not _fixed_local(root):
            warnings.add('UNSAFE_LOCATION_SKIPPED')
            continue
        if has_metadata:
            try:
                selected.add(str(_selected(root)))
            except FileNotFoundError:
                pass
            except _TooLarge:
                limited = True
                warnings.add('SELECTION_METADATA_UNAVAILABLE')
            except config.SetupError as exc:
                warnings.add('DEPENDENCY_REQUIRED' if str(exc) == 'YAML_DEPENDENCY_MISSING'
                             else 'SELECTION_METADATA_UNAVAILABLE')
            except (OSError, _Unsafe, RecursionError):
                warnings.add('SELECTION_METADATA_UNAVAILABLE')
        for folder in (root, root / 'profiles', root / 'Profiles'):
            fd = None
            try:
                _, info = _safe_path(folder, directory=True)
                identity = (info.st_dev, info.st_ino)
                if identity in folders:
                    continue
                folders.add(identity)
                fd = _open_local(folder, directory=True)
                if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != identity:
                    raise _Unsafe()
                # scandir(fd) avoids a directory replacement race on POSIX.
                children = os.scandir(fd if os.scandir in os.supports_fd else folder)
                with children:
                    for item in children:
                        entries += 1
                        if entries > MAX_ENTRIES or reads >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                            limited = True
                            break
                        path = folder / item.name
                        if (path.suffix.lower() not in EXTENSIONS or path.name.lower() in SKIP_NAMES
                                or path.name.startswith('.') or str(path) in seen):
                            continue
                        seen.add(str(path))
                        try:
                            reads += 1
                            data = _read(path, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total))
                            total += len(data)
                            obj = config.parse_config(data, 'json' if path.suffix.lower() == '.json' else 'yaml')
                            if not _supported(obj):
                                continue
                            token = hashlib.sha256(os.fsencode(str(path)) + b'\0' + data).hexdigest()
                            kind = '运行配置候选' if path.name.lower() == 'clash-verge.yaml' else '配置'
                            candidates.append({'id': token, 'path': str(path),
                                               'label': f'{client} {kind} {len(candidates) + 1}',
                                               'client': client, 'active': False,
                                               'selection_evidence': None})
                        except _TooLarge:
                            limited = True
                        except config.SetupError as exc:
                            warnings.add('DEPENDENCY_REQUIRED' if str(exc) == 'YAML_DEPENDENCY_MISSING'
                                         else 'UNREADABLE_OR_UNSUPPORTED_CONFIG_SKIPPED')
                        except (OSError, _Unsafe, RecursionError):
                            warnings.add('UNREADABLE_OR_UNSUPPORTED_CONFIG_SKIPPED')
            except FileNotFoundError:
                pass
            except (OSError, _Unsafe):
                warnings.add('UNSAFE_LOCATION_SKIPPED')
            finally:
                if fd is not None:
                    os.close(fd)
            if entries > MAX_ENTRIES or reads >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                break
        if entries > MAX_ENTRIES or reads >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            limited = True
            break
    matching = [item for item in candidates if item['path'] in selected]
    for item in matching:
        item['selection_evidence'] = SELECTION_EVIDENCE
    if (len(matching) == 1 and len(selected) == 1 and not limited
            and not warnings.intersection({'SELECTION_METADATA_UNAVAILABLE', 'DEPENDENCY_REQUIRED'})):
        matching[0]['active'] = True
    elif len(selected) > 1:
        warnings.add('MULTIPLE_SELECTED_PROFILES')
    if not any(item['active'] for item in candidates):
        warnings.add('ACTIVE_PROFILE_NOT_CONFIRMED')
    if limited:
        warnings.add('DISCOVERY_LIMIT_REACHED')
    return {'candidates': candidates, 'warnings': sorted(warnings), 'limited': limited}
