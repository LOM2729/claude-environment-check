"""Handle-relative NTFS adapter for the explicit scoped-cleanup engine."""
from contextlib import ExitStack, contextmanager
import ctypes as ct
from ctypes import wintypes as w
from functools import lru_cache
from pathlib import Path
import re
import struct
import uuid

import config_recovery as storage


READ_DATA, TRAVERSE, READ_ATTRIBUTES = 1, 0x20, 0x80
DELETE, READ_CONTROL, SYNCHRONIZE = 0x10000, 0x20000, 0x100000
SHARE_READ, SHARE_WRITE = 1, 2
DIRECTORY, REPARSE = 0x10, 0x400
# Common ordinary NTFS attributes only. Unrecognized attributes fail closed.
SUPPORTED_ATTRIBUTES = 0x2 | DIRECTORY | 0x20 | 0x80 | 0x2000
INVALID_HANDLE = ct.c_void_p(-1).value


class UnicodeString(ct.Structure):
    _fields_ = [('length', w.USHORT), ('maximum_length', w.USHORT), ('buffer', w.LPWSTR)]


class ObjectAttributes(ct.Structure):
    _fields_ = [('size', w.ULONG), ('root', w.HANDLE), ('name', ct.POINTER(UnicodeString)),
                ('flags', w.ULONG), ('security', ct.c_void_p), ('quality', ct.c_void_p)]


class IoStatus(ct.Structure):
    _fields_ = [('status', ct.c_void_p), ('information', ct.c_size_t)]


class BasicInfo(ct.Structure):
    _fields_ = [('creation', ct.c_int64), ('access', ct.c_int64), ('write', ct.c_int64),
                ('change', ct.c_int64), ('attributes', w.DWORD)]


class StandardInfo(ct.Structure):
    _fields_ = [('allocation', ct.c_int64), ('size', ct.c_int64), ('links', w.DWORD),
                ('delete_pending', w.BYTE), ('directory', w.BYTE)]


class FileIdInfo(ct.Structure):
    _fields_ = [('volume', ct.c_uint64), ('id', w.BYTE * 16)]


class RenameInfo(ct.Structure):
    _fields_ = [('flags', w.DWORD), ('parent', w.HANDLE), ('length', w.DWORD), ('name', w.WCHAR * 1)]


class AclInfo(ct.Structure):
    _fields_ = [('count', w.DWORD), ('bytes_used', w.DWORD), ('free', w.DWORD)]


class SecurityAttributes(ct.Structure):
    _fields_ = [('size', w.DWORD), ('descriptor', ct.c_void_p), ('inherit', w.BOOL)]


class ProcessEntry(ct.Structure):
    _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
                ('heap', ct.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                ('parent_pid', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD),
                ('image', w.WCHAR * 260)]


@lru_cache(maxsize=1)
def _api():
    _, kernel, advapi = storage._windows()
    nt = ct.WinDLL('ntdll', use_last_error=True)
    functions = (
        (kernel, 'CloseHandle', w.BOOL, [w.HANDLE]),
        (kernel, 'CreateFileW', w.HANDLE, [w.LPCWSTR, w.DWORD, w.DWORD, ct.c_void_p, w.DWORD, w.DWORD, w.HANDLE]),
        (kernel, 'GetDriveTypeW', w.UINT, [w.LPCWSTR]),
        (kernel, 'GetFileInformationByHandleEx', w.BOOL, [w.HANDLE, ct.c_int, ct.c_void_p, w.DWORD]),
        (kernel, 'GetFinalPathNameByHandleW', w.DWORD, [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]),
        (kernel, 'GetVolumeInformationByHandleW', w.BOOL, [w.HANDLE, w.LPWSTR, w.DWORD, ct.c_void_p,
                                                         ct.c_void_p, ct.c_void_p, w.LPWSTR, w.DWORD]),
        (kernel, 'ReadFile', w.BOOL, [w.HANDLE, ct.c_void_p, w.DWORD, ct.POINTER(w.DWORD), ct.c_void_p]),
        (kernel, 'WriteFile', w.BOOL, [w.HANDLE, ct.c_void_p, w.DWORD, ct.POINTER(w.DWORD), ct.c_void_p]),
        (kernel, 'FlushFileBuffers', w.BOOL, [w.HANDLE]),
        (kernel, 'CreateToolhelp32Snapshot', w.HANDLE, [w.DWORD, w.DWORD]),
        (kernel, 'Process32FirstW', w.BOOL, [w.HANDLE, ct.POINTER(ProcessEntry)]),
        (kernel, 'Process32NextW', w.BOOL, [w.HANDLE, ct.POINTER(ProcessEntry)]),
        (advapi, 'GetSecurityInfo', w.DWORD, [w.HANDLE, ct.c_int, w.DWORD, ct.POINTER(ct.c_void_p),
                                             ct.c_void_p, ct.POINTER(ct.c_void_p), ct.c_void_p,
                                             ct.POINTER(ct.c_void_p)]),
        (advapi, 'GetAclInformation', w.BOOL, [ct.c_void_p, ct.c_void_p, w.DWORD, ct.c_int]),
        (advapi, 'GetAce', w.BOOL, [ct.c_void_p, w.DWORD, ct.POINTER(ct.c_void_p)]),
        (advapi, 'ConvertSidToStringSidW', w.BOOL, [ct.c_void_p, ct.POINTER(w.LPWSTR)]),
        (advapi, 'ConvertStringSecurityDescriptorToSecurityDescriptorW', w.BOOL,
         [w.LPCWSTR, w.DWORD, ct.POINTER(ct.c_void_p), ct.POINTER(w.ULONG)]),
        (advapi, 'IsValidSid', w.BOOL, [ct.c_void_p]),
        (advapi, 'GetLengthSid', w.DWORD, [ct.c_void_p]),
        (nt, 'NtOpenFile', w.LONG, [ct.POINTER(w.HANDLE), w.ULONG, ct.POINTER(ObjectAttributes),
                                    ct.POINTER(IoStatus), w.ULONG, w.ULONG]),
        (nt, 'NtQueryInformationFile', w.LONG, [w.HANDLE, ct.POINTER(IoStatus), ct.c_void_p, w.ULONG, ct.c_int]),
        (nt, 'NtSetInformationFile', w.LONG, [w.HANDLE, ct.POINTER(IoStatus), ct.c_void_p, w.ULONG, ct.c_int]),
    )
    for dll, name, result, args in functions:
        function = getattr(dll, name)
        function.restype = result
        function.argtypes = args
    return kernel, advapi, nt


@contextmanager
def _handle(value):
    try:
        yield value
    finally:
        _api()[0].CloseHandle(value)


def _component(c, name):
    c.require(name and name not in ('.', '..') and name.rstrip(' .') == name and
              not any(ord(ch) < 32 or ch in '<>:"/\\|?*' for ch in name) and
              not re.match(r'^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', name, re.I),
              'CLEANUP_WINDOWS_NAME_UNSUPPORTED')
    try:
        raw = name.encode('utf-16-le')
    except UnicodeError:
        raise c.SetupError('CLEANUP_WINDOWS_NAME_UNSUPPORTED') from None
    c.require(len(raw) <= 510, 'CLEANUP_WINDOWS_NAME_UNSUPPORTED')
    return raw


def lexical_path(c, path):
    c.require(path.is_absolute() and re.fullmatch(r'[A-Za-z]:\\', path.anchor), 'CLEANUP_WINDOWS_FIXED_VOLUME_REQUIRED')
    for component in path.parts[1:]:
        _component(c, component)
    return path


def _info(c, handle, kind, value):
    c.require(_api()[0].GetFileInformationByHandleEx(handle, kind, ct.byref(value), ct.sizeof(value)),
              'CLEANUP_WINDOWS_HANDLE_METADATA_UNAVAILABLE')
    return value


def _nt_info(c, handle, kind, value):
    result = _api()[2].NtQueryInformationFile(handle, ct.byref(IoStatus()), ct.byref(value), ct.sizeof(value), kind)
    c.require(result == 0, 'CLEANUP_WINDOWS_HANDLE_METADATA_UNAVAILABLE')
    return value


def _directory(c, handle):
    attrs = _info(c, handle, 0, BasicInfo()).attributes
    c.require(not attrs & REPARSE, 'CLEANUP_LINK_REJECTED')
    c.require(attrs & DIRECTORY, 'CLEANUP_WINDOWS_PARENT_REQUIRED')
    c.require(_nt_info(c, handle, 71, w.ULONG()).value == 0, 'CLEANUP_WINDOWS_CASE_SENSITIVE_UNSUPPORTED')


def _canonical(c, handle, path):
    value = ct.create_unicode_buffer(32768)
    size = _api()[0].GetFinalPathNameByHandleW(handle, value, len(value), 0)
    c.require(0 < size < len(value) and Path(value.value.removeprefix('\\\\?\\')) == path,
              'CLEANUP_WINDOWS_CANONICAL_PATH_REQUIRED')


@contextmanager
def _child(c, parent, name, access, share):
    raw = _component(c, name)
    buffer = ct.create_unicode_buffer(name)
    string = UnicodeString(len(raw), len(raw) + 2, ct.cast(buffer, w.LPWSTR))
    attrs = ObjectAttributes(ct.sizeof(ObjectAttributes), parent, ct.pointer(string), 0x1040, None, None)
    handle = w.HANDLE()
    # Open one name relative to a pinned directory. Never resolve a reparse point.
    status = _api()[2].NtOpenFile(ct.byref(handle), access | SYNCHRONIZE, ct.byref(attrs), ct.byref(IoStatus()),
                                  share, 0x00200020)
    if status & 0xFFFFFFFF == 0xC000050B:  # STATUS_REPARSE_POINT_ENCOUNTERED
        raise c.SetupError('CLEANUP_LINK_REJECTED')
    c.require(status == 0 and handle.value, 'CLEANUP_WINDOWS_OBJECT_UNAVAILABLE')
    with _handle(handle.value) as opened:
        yield opened


@contextmanager
def _chain(c, path, access=TRAVERSE | READ_ATTRIBUTES, directory=True, share=SHARE_READ | SHARE_WRITE):
    kernel = _api()[0]
    c.require(path.is_absolute() and re.fullmatch(r'[A-Za-z]:\\', path.anchor) and
              kernel.GetDriveTypeW(path.anchor) == 3, 'CLEANUP_WINDOWS_FIXED_VOLUME_REQUIRED')
    drive = kernel.CreateFileW(path.anchor, TRAVERSE | READ_ATTRIBUTES, SHARE_READ | SHARE_WRITE,
                               None, 3, 0x02200000, None)
    c.require(drive not in (None, INVALID_HANDLE), 'CLEANUP_WINDOWS_VOLUME_UNAVAILABLE')
    with ExitStack() as stack:
        handle = stack.enter_context(_handle(drive))
        filesystem = ct.create_unicode_buffer(16)
        c.require(kernel.GetVolumeInformationByHandleW(handle, None, 0, None, None, None,
                                                      filesystem, len(filesystem)) and filesystem.value == 'NTFS',
                  'CLEANUP_WINDOWS_NTFS_REQUIRED')
        _directory(c, handle)
        for index, part in enumerate(path.parts[1:], 2):
            leaf = index == len(path.parts)
            rights = access if leaf else TRAVERSE | READ_ATTRIBUTES
            handle = stack.enter_context(_child(c, handle, part, rights, share if leaf else SHARE_READ | SHARE_WRITE))
            if directory or not leaf:
                _directory(c, handle)
        _canonical(c, handle, path)
        yield handle


def _sid(c, pointer):
    kernel, advapi, _ = _api()
    text = w.LPWSTR()
    c.require(pointer and advapi.IsValidSid(pointer) and advapi.ConvertSidToStringSidW(pointer, ct.byref(text)),
              'CLEANUP_WINDOWS_SECURITY_UNAVAILABLE')
    try:
        return text.value
    finally:
        kernel.LocalFree(text)


def _security(c, handle, user):
    kernel, advapi, _ = _api()
    owner, dacl, descriptor = (ct.c_void_p() for _ in range(3))
    result = advapi.GetSecurityInfo(handle, 1, 7, ct.byref(owner), None, ct.byref(dacl), None, ct.byref(descriptor))
    c.require(result == 0 and descriptor.value, 'CLEANUP_WINDOWS_SECURITY_UNAVAILABLE')
    try:
        c.require(_sid(c, owner) == user, 'CLEANUP_OWNER_MISMATCH')
        size = AclInfo()
        c.require(dacl.value and advapi.GetAclInformation(dacl, ct.byref(size), ct.sizeof(size), 2) and
                  0 < size.count <= 1024, 'CLEANUP_WINDOWS_ACL_UNSUPPORTED')
        trusted = (user, 'S-1-5-18', 'S-1-5-32-544')
        for index in range(size.count):
            ace = ct.c_void_p()
            c.require(advapi.GetAce(dacl, index, ct.byref(ace)) and ace.value, 'CLEANUP_WINDOWS_ACL_UNSUPPORTED')
            kind, flags, length = struct.unpack('<BBH', ct.string_at(ace, 4))
            c.require(kind == 0 and not flags & ~0x1F and length >= 16, 'CLEANUP_WINDOWS_ACL_UNSUPPORTED')
            sid = ct.c_void_p(ace.value + 8)
            c.require(advapi.IsValidSid(sid) and advapi.GetLengthSid(sid) <= length - 8 and
                      _sid(c, sid) in trusted, 'CLEANUP_WINDOWS_ACL_UNSUPPORTED')
        text = w.LPWSTR()
        c.require(advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 7, ct.byref(text), None),
                  'CLEANUP_WINDOWS_SECURITY_UNAVAILABLE')
        try:
            c.require(len(text.value) <= 4096, 'CLEANUP_WINDOWS_SECURITY_UNAVAILABLE')
            return text.value
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.LocalFree(descriptor)


def _user(c):
    try:
        return storage._win_sid()
    except OSError:
        raise c.SetupError('CLEANUP_WINDOWS_SECURITY_UNAVAILABLE') from None


def _identity(c, handle):
    value = _info(c, handle, 18, FileIdInfo())
    return {'volume': value.volume, 'file_id': bytes(value.id).hex()}


def _parent_identity(c, handle, path, user):
    return dict(_identity(c, handle), path=str(path), creation_time_100ns=_info(c, handle, 0, BasicInfo()).creation,
                security=_security(c, handle, user))


def parent(c, path):
    with _chain(c, path, TRAVERSE | READ_ATTRIBUTES | READ_CONTROL) as handle:
        return _parent_identity(c, handle, path, _user(c))


def volume(c, path):
    with _chain(c, path) as handle:
        return _identity(c, handle)['volume']


@contextmanager
def pinned_directory(c, path, expected=None):
    access = TRAVERSE | READ_ATTRIBUTES
    if expected is not None:
        access |= READ_CONTROL
    with _chain(c, path, access) as handle:
        if expected is not None:
            c.require(_parent_identity(c, handle, path, _user(c)) == expected,
                      'CLEANUP_SOURCE_OR_DESTINATION_PARENT_CHANGED')
        yield


@contextmanager
def lock(c, path, expected_parent):
    with pinned_directory(c, path.parent, expected_parent):
        _component(c, path.name)
        # CREATE_NEW and delete-on-close tie cleanup to this exact empty handle.
        handle = _api()[0].CreateFileW(str(path), DELETE | 0x40000000, 0, None, 1, 0x04200002, None)
        c.require(handle not in (None, INVALID_HANDLE), 'CLEANUP_LOCK_EXISTS_OR_UNAVAILABLE')
    with _handle(handle):
        yield


def write_new(c, path, data):
    """Parent is pinned by the caller; writes are private from creation."""
    _component(c, path.name)
    kernel, advapi, _ = _api()
    descriptor = ct.c_void_p()
    user = _user(c)
    sddl = 'O:' + user + 'D:P(A;;FA;;;' + user + ')(A;;FA;;;SY)'
    c.require(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ct.byref(descriptor), None),
              'CLEANUP_WINDOWS_SECURITY_UNAVAILABLE')
    try:
        attributes = SecurityAttributes(ct.sizeof(SecurityAttributes), descriptor, False)
        # CREATE_NEW, WRITE_THROUGH, OPEN_REPARSE_POINT. Existing names are never replaced.
        handle = kernel.CreateFileW(str(path), 0x40000000, 0, ct.byref(attributes), 1, 0x80200080, None)
    finally:
        kernel.LocalFree(descriptor)
    c.require(handle not in (None, INVALID_HANDLE), 'CLEANUP_WINDOWS_PRIVATE_WRITE_FAILED')
    with _handle(handle):
        if data:
            count = w.DWORD()
            c.require(kernel.WriteFile(handle, data, len(data), ct.byref(count), None) and count.value == len(data),
                      'CLEANUP_WINDOWS_PRIVATE_WRITE_FAILED')
        c.require(kernel.FlushFileBuffers(handle), 'CLEANUP_WINDOWS_PRIVATE_WRITE_FAILED')


def _ordinary_streams(c, handle):
    buffer = ct.create_string_buffer(65536)
    success = _api()[0].GetFileInformationByHandleEx(handle, 7, buffer, len(buffer))
    if not success and ct.get_last_error() == 38:  # No stream entries.
        return
    c.require(success, 'CLEANUP_WINDOWS_STREAMS_UNAVAILABLE')
    next_entry, length = struct.unpack_from('<II', buffer)
    c.require(not next_entry and length == 14 and buffer[24:38] == '::$DATA'.encode('utf-16-le'),
              'CLEANUP_WINDOWS_NAMED_STREAM_REJECTED')


def _state(c, handle, user):
    basic = _info(c, handle, 0, BasicInfo())
    standard = _info(c, handle, 1, StandardInfo())
    c.require(not basic.attributes & REPARSE, 'CLEANUP_LINK_REJECTED')
    c.require(not standard.delete_pending and not basic.attributes & ~SUPPORTED_ATTRIBUTES and
              bool(basic.attributes & DIRECTORY) == bool(standard.directory), 'CLEANUP_WINDOWS_ATTRIBUTES_UNSUPPORTED')
    if standard.directory:
        _directory(c, handle)
    else:
        c.require(standard.links == 1 and standard.size >= 0, 'CLEANUP_HARDLINK_REJECTED')
    c.require(_nt_info(c, handle, 7, w.ULONG()).value == 0, 'CLEANUP_WINDOWS_EXTENDED_ATTRIBUTES_UNSUPPORTED')
    _ordinary_streams(c, handle)
    identity = dict(_identity(c, handle), size=0 if standard.directory else standard.size,
                    mtime_ns=basic.write * 100, ctime_ns=basic.change * 100, links=standard.links)
    metadata = {'creation_time_100ns': basic.creation, 'attributes': basic.attributes,
                'security': _security(c, handle, user)}
    return ('directory' if standard.directory else 'file'), identity, metadata


def _read(c, handle, size):
    kernel = _api()[0]
    buffer = ct.create_string_buffer(65536)
    pieces = []
    remaining = size
    while remaining:
        count = w.DWORD()
        wanted = min(len(buffer), remaining)
        c.require(kernel.ReadFile(handle, buffer, wanted, ct.byref(count), None) and 0 < count.value <= wanted,
                  'CLEANUP_SOURCE_CHANGED')
        pieces.append(buffer[:count.value])
        remaining -= count.value
    return b''.join(pieces)


def _names(c, handle, remaining):
    buffer = ct.create_string_buffer(65536)
    kernel = _api()[0]
    kind = 11  # FileIdBothDirectoryRestartInfo, then FileIdBothDirectoryInfo.
    names = []
    while kernel.GetFileInformationByHandleEx(handle, kind, buffer, len(buffer)):
        kind = 10
        offset = 0
        while True:
            c.require(offset + 104 <= len(buffer), 'CLEANUP_WINDOWS_ENUMERATION_INVALID')
            next_offset, = struct.unpack_from('<I', buffer, offset)
            length, = struct.unpack_from('<I', buffer, offset + 60)
            c.require(0 < length <= 510 and length % 2 == 0 and offset + 104 + length <= len(buffer),
                      'CLEANUP_WINDOWS_ENUMERATION_INVALID')
            try:
                name = buffer[offset + 104:offset + 104 + length].decode('utf-16-le')
            except UnicodeError:
                raise c.SetupError('CLEANUP_WINDOWS_NAME_UNSUPPORTED') from None
            if name not in ('.', '..'):
                _component(c, name)
                c.require(len(names) < remaining, 'CLEANUP_BUDGET_EXCEEDED')
                names.append(name)
            if not next_offset:
                break
            c.require(next_offset >= 104 + length and next_offset % 8 == 0, 'CLEANUP_WINDOWS_ENUMERATION_INVALID')
            offset += next_offset
    c.require(ct.get_last_error() == 18, 'CLEANUP_WINDOWS_ENUMERATION_UNAVAILABLE')
    c.require(len({name.casefold() for name in names}) == len(names), 'CLEANUP_WINDOWS_NAME_UNSUPPORTED')
    return sorted(names)


def _snapshot(c, handle, name, counter, limits, user, depth=0):
    max_items, max_bytes, max_depth = limits
    root_volume = _identity(c, handle)['volume']
    rows = []

    def visit(opened, name, relative, level):
        c.require(level <= max_depth, 'CLEANUP_DEPTH_EXCEEDED')
        c.require(name.casefold() not in ('.git', '.codex', '.agents'), 'CLEANUP_SOURCE_OR_CODEX_PROTECTED')
        kind, identity, metadata = before = _state(c, opened, user)
        c.require(identity['volume'] == root_volume, 'CLEANUP_MOUNT_BOUNDARY_REJECTED')
        counter['items'] += 1
        counter['bytes'] += identity['size']
        c.require(counter['items'] <= max_items and counter['bytes'] <= max_bytes, 'CLEANUP_BUDGET_EXCEEDED')
        row = {'relative': relative, 'type': kind, 'identity': identity, 'metadata': metadata}
        rows.append(row)
        if kind == 'file':
            row['sha256'] = c.sha(_read(c, opened, identity['size']))
        else:
            row['children'] = _names(c, opened, max_items - counter['items'])
            for child in row['children']:
                child_relative = child if relative == '.' else relative + '/' + child
                with _child(c, opened, child, READ_DATA | TRAVERSE | READ_ATTRIBUTES | READ_CONTROL, SHARE_READ) as item:
                    visit(item, child, child_relative, level + 1)
        c.require(_state(c, opened, user) == before, 'CLEANUP_SOURCE_CHANGED')

    visit(handle, name, '.', depth)
    return rows


def scan(c, path, counter, limits, depth=0):
    with _chain(c, path, READ_DATA | TRAVERSE | READ_ATTRIBUTES | READ_CONTROL, directory=False, share=SHARE_READ) as handle:
        return _snapshot(c, handle, path.name, counter, limits, _user(c), depth)


def read(c, path, expected, max_bytes):
    with _chain(c, path, READ_DATA | READ_ATTRIBUTES | READ_CONTROL, directory=False, share=SHARE_READ) as handle:
        user = _user(c)
        kind, identity, _ = before = _state(c, handle, user)
        c.require(kind == 'file' and (expected is None or identity == expected) and identity['size'] <= max_bytes,
                  'CLEANUP_SOURCE_CHANGED')
        raw = _read(c, handle, identity['size'])
        c.require(_state(c, handle, user) == before, 'CLEANUP_SOURCE_CHANGED')
        return raw


def move(c, source, target, expected, source_parent, target_parent, limits):
    user = _user(c)
    rights = TRAVERSE | READ_ATTRIBUTES | READ_CONTROL
    with _chain(c, source.parent, rights) as old, _chain(c, target.parent, rights) as new:
        c.require(_parent_identity(c, old, source.parent, user) == source_parent and
                  _parent_identity(c, new, target.parent, user) == target_parent, 'CLEANUP_SOURCE_OR_DESTINATION_PARENT_CHANGED')
        c.require(source_parent['volume'] == target_parent['volume'], 'CLEANUP_SAME_VOLUME_REQUIRED')
        with _child(c, old, source.name, DELETE | READ_DATA | rights, SHARE_READ) as opened:
            _canonical(c, opened, source)
            snapshot = _snapshot(c, opened, source.name, {'items': 0, 'bytes': 0}, limits, user)
            c.require(snapshot == expected, 'CLEANUP_SOURCE_CHANGED')
            leaf = _component(c, target.name)
            buffer = ct.create_string_buffer(ct.sizeof(RenameInfo) + len(leaf))
            info = RenameInfo.from_buffer(buffer)
            info.parent, info.length = new, len(leaf)
            ct.memmove(ct.addressof(buffer) + RenameInfo.name.offset, leaf, len(leaf))
            # No replacement flag and no path fallback, even for interrupted moves.
            status = _api()[2].NtSetInformationFile(opened, ct.byref(IoStatus()), buffer, len(buffer), 10)
            if status:
                raise c.SetupError('CLEANUP_WINDOWS_DESTINATION_EXISTS' if status & 0xFFFFFFFF == 0xC0000035
                                   else 'CLEANUP_WINDOWS_RENAME_FAILED')


def known_folder(c, folder):
    ids = {'profile': '5E6C858F-0E22-4760-9AFE-EA3317B67173', 'roaming': '3EB685DB-65F9-4CF6-A03A-E3EF65729F3D'}
    shell = ct.WinDLL('shell32')
    ole = ct.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [ct.c_void_p, w.DWORD]
    ole.CoInitializeEx.restype = w.LONG
    ole.CoUninitialize.argtypes = []
    ole.CoTaskMemFree.argtypes = [ct.c_void_p]
    shell.SHGetKnownFolderPath.argtypes = [ct.c_void_p, w.DWORD, w.HANDLE, ct.POINTER(w.LPWSTR)]
    shell.SHGetKnownFolderPath.restype = w.LONG
    state = ole.CoInitializeEx(None, 0)
    c.require(state in (0, 1) or state & 0xFFFFFFFF == 0x80010106, 'CLEANUP_WINDOWS_SCOPE_UNAVAILABLE')
    value = w.LPWSTR()
    try:
        guid = (w.BYTE * 16).from_buffer_copy(uuid.UUID(ids[folder]).bytes_le)
        c.require(shell.SHGetKnownFolderPath(guid, 0, None, ct.byref(value)) == 0 and value.value,
                  'CLEANUP_WINDOWS_SCOPE_UNAVAILABLE')
        return Path(value.value)
    finally:
        if value:
            ole.CoTaskMemFree(value)
        if state in (0, 1):
            ole.CoUninitialize()


def process_images(c):
    kernel = _api()[0]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    c.require(snapshot not in (None, INVALID_HANDLE), 'CLEANUP_PROCESS_STATE_UNAVAILABLE')
    with _handle(snapshot) as handle:
        entry = ProcessEntry()
        entry.size = ct.sizeof(entry)
        c.require(kernel.Process32FirstW(handle, ct.byref(entry)), 'CLEANUP_PROCESS_STATE_UNAVAILABLE')
        for _ in range(65536):
            yield entry.image
            if not kernel.Process32NextW(handle, ct.byref(entry)):
                c.require(ct.get_last_error() == 18, 'CLEANUP_PROCESS_STATE_UNAVAILABLE')
                return
        raise c.SetupError('CLEANUP_PROCESS_STATE_UNAVAILABLE')
