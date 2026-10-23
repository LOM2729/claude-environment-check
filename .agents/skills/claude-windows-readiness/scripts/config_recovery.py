"""Pinned, local text-file transactions. Never imports/reloads a proxy or writes its DB.

The writer-stopped confirmation is deliberately required on every write. A file
lock coordinates this tool only; it cannot stop another application. Hashes bind
reviewed artifacts, not authorization. Interrupted commits retain a durable intent
and private backup, but missing final receipts never authorize an automatic undo.
"""
import ctypes
import difflib
import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import tempfile
import uuid

COMMANDS = ('recovery-plan', 'recovery-apply', 'recovery-rollback', 'recovery-check')
EXTENSIONS = {'.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.conf': 'shadowrocket'}
MAX_META = 256 * 1024
PRIVATE_SCHEMA = 'claude-config-recovery/1'


def register_commands(subparsers):
    for command in COMMANDS:
        p = subparsers.add_parser(command, help='Pinned local text-file recovery; no proxy activation or network')
        p.add_argument('--out', required=True)
        if command == 'recovery-plan':
            p.add_argument('--target', required=True)
            p.add_argument('--candidate', required=True)
        elif command == 'recovery-apply':
            p.add_argument('--plan', required=True, help='Private recovery-plan directory')
            p.add_argument('--plan-sha256', required=True, help='Reviewed plan.json SHA256')
        else:
            p.add_argument('--receipt', required=True, help='Private transaction directory (intent plus final receipt)')
            p.add_argument('--receipt-sha256', required=True, help='Pinned final receipt SHA256 (intent SHA256 checks interrupted runs only)')
        if command in ('recovery-apply', 'recovery-rollback'):
            p.add_argument('--allow-write', action='store_true')
            p.add_argument('--writer-stopped', action='store_true', help='Confirm the client/sync writer was stopped safely by its operator')


def _binding():
    # Local host/user binding is an accident barrier, not a hardware attestation.
    parts = [platform.system(), platform.node(), str(Path.home()), str(getattr(os, 'getuid', lambda: '')())]
    return {'platform': platform.system(), 'machine_user_sha256': hashlib.sha256('\0'.join(parts).encode()).hexdigest()}


def _safe_path(c, value, directory=False, missing=False):
    p = Path(value)
    c.require(not any(part in ('.', '..') for part in p.parts) and '\x00' not in str(p), 'RECOVERY_PATH_INVALID')
    p = p.absolute()
    # Disallow ADS, UNC/network paths and device names on Windows.
    if os.name == 'nt':
        c.require(bool(p.drive) and not p.drive.startswith(('\\\\', '//')), 'RECOVERY_LOCAL_PATH_REQUIRED')
        w, kernel, _ = _windows()
        kernel.GetDriveTypeW.argtypes = [w.LPCWSTR]
        kernel.GetDriveTypeW.restype = w.UINT
        c.require(kernel.GetDriveTypeW(p.anchor) == 3, 'RECOVERY_LOCAL_FIXED_DRIVE_REQUIRED')
        for part in p.parts[1:]:
            c.require(':' not in part and part.rstrip(' .') == part and not re.match(r'(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', part), 'RECOVERY_PATH_INVALID')
    chain = []
    for entry in reversed((p, *p.parents)):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            c.require(missing and entry == p, 'RECOVERY_PATH_UNAVAILABLE')
            return p, chain
        except OSError:
            raise c.SetupError('RECOVERY_PATH_UNAVAILABLE') from None
        c.require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400), 'RECOVERY_LINK_OR_REPARSE_REJECTED')
        if entry != p or directory:
            c.require(stat.S_ISDIR(info.st_mode), 'RECOVERY_PARENT_DIRECTORY_REQUIRED')
            # Shared sticky temp ancestors are accepted; an immediate parent may
            # not be writable by a different account on POSIX.
            if os.name != 'nt' and (entry == p.parent or (entry == p and directory)):
                c.require(info.st_uid == os.getuid() and not info.st_mode & 0o022, 'RECOVERY_PRIVATE_PARENT_REQUIRED')
            chain.append([str(entry), info.st_dev, info.st_ino])
        else:
            c.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'RECOVERY_SINGLE_REGULAR_FILE_REQUIRED')
            if os.name != 'nt':
                c.require(info.st_uid == os.getuid(), 'RECOVERY_FILE_OWNER_MISMATCH')
    return p, chain


def _target_path(c, value):
    p, chain = _safe_path(c, value)
    c.require(p.suffix.lower() in EXTENSIONS, 'RECOVERY_TEXT_CONFIG_REQUIRED')
    # These stores must be changed through their supported application/OS entry,
    # even if a caller renames a database or managed preference to .conf.
    lower = str(p).replace('\\', '/').lower()
    bad_parts = ('/library/containers/', '/library/group containers/', '/library/preferences/',
                 '/library/managed preferences/', '/contents/', '/windows/', '/program files/',
                 '/program files (x86)/', '/programdata/microsoft/')
    c.require(not any(x in lower for x in bad_parts), 'RECOVERY_MANAGED_STORE_UNSUPPORTED')
    if os.name != 'nt':
        c.require(not any(lower == x or lower.startswith(x + '/') for x in ('/system', '/etc', '/private/etc', '/usr', '/bin', '/sbin', '/library')), 'RECOVERY_SYSTEM_STORE_UNSUPPORTED')
    if platform.system() == 'Darwin':
        try:
            # mkstemp mode 0600 cannot override inherited macOS ACL grants.
            # Refuse such parents before writing a candidate into them.
            c.require(_metadata(p.parent).get('acl') is None, 'RECOVERY_TARGET_PARENT_ACL_UNSUPPORTED')
        except OSError:
            raise c.SetupError('RECOVERY_PARENT_METADATA_UNAVAILABLE') from None
    return p, chain


def _fingerprint(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns,
            'mode': stat.S_IMODE(info.st_mode), 'uid': getattr(info, 'st_uid', None),
            'gid': getattr(info, 'st_gid', None), 'links': info.st_nlink,
            'flags': getattr(info, 'st_flags', 0), 'attributes': getattr(info, 'st_file_attributes', 0)}


def _windows():
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.GetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    advapi.GetFileSecurityW.restype = w.BOOL
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(w.LPWSTR), ctypes.POINTER(w.ULONG)]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = w.BOOL
    return w, kernel, advapi


def _win_sid():
    w, kernel, advapi = _windows()
    kernel.GetCurrentProcess.restype = w.HANDLE
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    token = w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise OSError('private-acl')
    try:
        count = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(count))
        data = ctypes.create_string_buffer(count.value)
        if not advapi.GetTokenInformation(token, 1, data, count, ctypes.byref(count)):
            raise OSError('private-acl')
        sid = ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p))[0]
        value = w.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(value)):
            raise OSError('private-acl')
        try:
            return value.value
        finally:
            kernel.LocalFree(value)
    finally:
        kernel.CloseHandle(token)


def _win_security_buffer(path):
    w, kernel, advapi = _windows()
    size = w.DWORD()
    advapi.GetFileSecurityW(str(path), 7, None, 0, ctypes.byref(size))
    if not size.value or size.value > MAX_META:
        raise OSError('security-unavailable')
    raw = ctypes.create_string_buffer(size.value)
    if not advapi.GetFileSecurityW(str(path), 7, raw, size, ctypes.byref(size)):
        raise OSError('security-unavailable')
    return raw


def _win_security(path):
    w, kernel, advapi = _windows()
    raw = _win_security_buffer(path)
    value = w.LPWSTR()
    if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(raw, 1, 7, ctypes.byref(value), None):
        raise OSError('security-unavailable')
    try:
        return value.value
    finally:
        kernel.LocalFree(value)


def _win_acl_summary(path=None, descriptor=None):
    """Semantic ACL check; diagnostics contain no names, SIDs, paths or SDDL.

    SDDL abbreviates well-known SIDs (and sometimes the current account) on
    serialization. Compare native SID values instead of matching that spelling.
    The optional descriptor supports native synthetic regression tests only.
    """
    w, kernel, advapi = _windows()
    raw = _win_security_buffer(path) if descriptor is None else descriptor
    class AclSize(ctypes.Structure):
        _fields_ = [('ace_count', w.DWORD), ('bytes_in_use', w.DWORD), ('bytes_free', w.DWORD)]
    class AceHeader(ctypes.Structure):
        _fields_ = [('kind', w.BYTE), ('flags', w.BYTE), ('size', w.WORD)]
    advapi.IsValidSecurityDescriptor.argtypes = [ctypes.c_void_p]
    advapi.IsValidSecurityDescriptor.restype = w.BOOL
    advapi.GetSecurityDescriptorOwner.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL)]
    advapi.GetSecurityDescriptorOwner.restype = w.BOOL
    advapi.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD)]
    advapi.GetSecurityDescriptorControl.restype = w.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL)]
    advapi.GetSecurityDescriptorDacl.restype = w.BOOL
    advapi.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_int]
    advapi.GetAclInformation.restype = w.BOOL
    advapi.GetAce.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi.GetAce.restype = w.BOOL
    advapi.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    advapi.ConvertStringSidToSidW.restype = w.BOOL
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi.EqualSid.restype = w.BOOL
    advapi.IsValidSid.argtypes = [ctypes.c_void_p]
    advapi.IsValidSid.restype = w.BOOL
    advapi.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi.GetLengthSid.restype = w.DWORD
    if not advapi.IsValidSecurityDescriptor(raw):
        raise OSError('security-descriptor-invalid')
    owner, dacl, user, system = (ctypes.c_void_p() for _ in range(4))
    owner_defaulted, present, dacl_defaulted = (w.BOOL() for _ in range(3))
    control, revision = w.WORD(), w.DWORD()
    if not advapi.GetSecurityDescriptorOwner(raw, ctypes.byref(owner), ctypes.byref(owner_defaulted)) or not advapi.GetSecurityDescriptorControl(raw, ctypes.byref(control), ctypes.byref(revision)) or not advapi.GetSecurityDescriptorDacl(raw, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(dacl_defaulted)):
        raise OSError('security-descriptor-unavailable')
    result = {'owner_is_current': False, 'dacl_present': bool(present.value),
              'dacl_nonnull': bool(dacl.value), 'dacl_protected': bool(control.value & 0x1000),
              'ace_count': 0, 'ace_types': [], 'only_allowed_principals': False,
              'current_user_full_access': False, 'current_user_children_full_access': False, 'private': False}
    try:
        if not advapi.ConvertStringSidToSidW(_win_sid(), ctypes.byref(user)) or not advapi.ConvertStringSidToSidW('S-1-5-18', ctypes.byref(system)):
            raise OSError('security-sid-unavailable')
        result['owner_is_current'] = bool(owner.value and advapi.EqualSid(owner, user))
        if not present.value or not dacl.value:
            return result
        size = AclSize()
        if not advapi.GetAclInformation(dacl, ctypes.byref(size), ctypes.sizeof(size), 2) or size.ace_count > 1024:
            raise OSError('security-acl-unavailable')
        result['ace_count'] = size.ace_count
        all_allowed = bool(size.ace_count)
        for index in range(size.ace_count):
            pointer = ctypes.c_void_p()
            if not advapi.GetAce(dacl, index, ctypes.byref(pointer)) or not pointer.value:
                raise OSError('security-ace-unavailable')
            header = ctypes.cast(pointer, ctypes.POINTER(AceHeader)).contents
            result['ace_types'].append(header.kind)
            # Only ordinary ACCESS_ALLOWED_ACE has this layout. Reject deny,
            # callback/object or conditional ACEs conservatively.
            if header.kind != 0 or header.size < 16:
                all_allowed = False
                continue
            sid = ctypes.c_void_p(pointer.value + 8)
            if not advapi.IsValidSid(sid) or advapi.GetLengthSid(sid) > header.size - 8:
                raise OSError('security-ace-invalid')
            is_user = bool(advapi.EqualSid(sid, user))
            is_system = bool(advapi.EqualSid(sid, system))
            all_allowed = all_allowed and (is_user or is_system)
            mask = ctypes.cast(ctypes.c_void_p(pointer.value + 4), ctypes.POINTER(w.DWORD)).contents.value
            if is_user and not header.flags & 0x08 and mask & 0x001F01FF == 0x001F01FF:
                result['current_user_full_access'] = True
                if header.flags & 0x03 == 0x03:
                    result['current_user_children_full_access'] = True
        result['only_allowed_principals'] = bool(all_allowed)
        result['private'] = all(result[k] for k in ('owner_is_current', 'dacl_present', 'dacl_nonnull',
                         'dacl_protected', 'only_allowed_principals', 'current_user_full_access',
                         'current_user_children_full_access'))
        return result
    finally:
        if user.value:
            kernel.LocalFree(user)
        if system.value:
            kernel.LocalFree(system)


def _win_security_comparison(expected, actual):
    """Explain native descriptor differences without emitting SIDs or SDDL."""
    w, kernel, advapi = _windows()
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.ULONG)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    for name in ('GetSecurityDescriptorOwner', 'GetSecurityDescriptorGroup'):
        fn = getattr(advapi, name)
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL)]
        fn.restype = w.BOOL
    advapi.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD)]
    advapi.GetSecurityDescriptorControl.restype = w.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL)]
    advapi.GetSecurityDescriptorDacl.restype = w.BOOL
    advapi.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_int]
    advapi.GetAclInformation.restype = w.BOOL
    advapi.GetAce.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi.GetAce.restype = w.BOOL
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi.EqualSid.restype = w.BOOL
    class AclSize(ctypes.Structure):
        _fields_ = [('ace_count', w.DWORD), ('bytes_in_use', w.DWORD), ('bytes_free', w.DWORD)]
    allocations = []
    def components(text):
        descriptor = ctypes.c_void_p()
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(text, 1, ctypes.byref(descriptor), None):
            raise OSError('descriptor-comparison-unavailable')
        allocations.append(descriptor)
        owner, group, dacl = (ctypes.c_void_p() for _ in range(3))
        defaulted, present, dacl_defaulted = (w.BOOL() for _ in range(3))
        control, revision = w.WORD(), w.DWORD()
        if not advapi.GetSecurityDescriptorOwner(descriptor, ctypes.byref(owner), ctypes.byref(defaulted)) or not advapi.GetSecurityDescriptorGroup(descriptor, ctypes.byref(group), ctypes.byref(defaulted)) or not advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)) or not advapi.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(dacl_defaulted)):
            raise OSError('descriptor-comparison-unavailable')
        aces = []
        if dacl.value:
            size = AclSize()
            if not advapi.GetAclInformation(dacl, ctypes.byref(size), ctypes.sizeof(size), 2) or size.ace_count > 1024:
                raise OSError('descriptor-comparison-unavailable')
            for index in range(size.ace_count):
                ace = ctypes.c_void_p()
                if not advapi.GetAce(dacl, index, ctypes.byref(ace)) or not ace.value:
                    raise OSError('descriptor-comparison-unavailable')
                header = ctypes.string_at(ace, 4)
                length = int.from_bytes(header[2:4], 'little')
                if length < 4:
                    raise OSError('descriptor-comparison-unavailable')
                aces.append(ctypes.string_at(ace, length))
        return {'owner': owner, 'group': group, 'control': control.value,
                'dacl_present': bool(present.value), 'dacl_nonnull': bool(dacl.value),
                'dacl_defaulted': bool(dacl_defaulted.value), 'aces': aces}
    try:
        left, right = components(expected), components(actual)
        sid_equal = lambda a, b: bool(advapi.EqualSid(a, b)) if a.value and b.value else not a.value and not b.value
        flags = {'protected': 0x1000, 'auto_inherited': 0x0400, 'auto_inherit_required': 0x0100, 'defaulted': 0x0008}
        return {'available': True, 'owner_sid_matches': sid_equal(left['owner'], right['owner']),
                'group_sid_matches': sid_equal(left['group'], right['group']),
                'control_matches': left['control'] == right['control'],
                'expected_dacl_control': {key: bool(left['control'] & mask) for key, mask in flags.items()},
                'actual_dacl_control': {key: bool(right['control'] & mask) for key, mask in flags.items()},
                'dacl_present_matches': left['dacl_present'] == right['dacl_present'],
                'dacl_nonnull_matches': left['dacl_nonnull'] == right['dacl_nonnull'],
                'dacl_ace_bytes_match': left['aces'] == right['aces'],
                'dacl_ace_count_matches': len(left['aces']) == len(right['aces']),
                'expected_ace_types': [ace[0] for ace in left['aces']], 'actual_ace_types': [ace[0] for ace in right['aces']],
                'expected_ace_flags': [ace[1] for ace in left['aces']], 'actual_ace_flags': [ace[1] for ace in right['aces']],
                'dacl_ace_masks_match': [ace[4:8] for ace in left['aces']] == [ace[4:8] for ace in right['aces']]}
    finally:
        for descriptor in allocations:
            kernel.LocalFree(descriptor)


def _win_no_named_streams(path):
    """This text-only backup does not claim to snapshot alternate data streams."""
    w, kernel, _ = _windows()
    class Stream(ctypes.Structure):
        _fields_ = [('size', ctypes.c_longlong), ('name', w.WCHAR * 296)]
    kernel.FindFirstStreamW.argtypes = [w.LPCWSTR, ctypes.c_int, ctypes.POINTER(Stream), w.DWORD]
    kernel.FindFirstStreamW.restype = w.HANDLE
    kernel.FindNextStreamW.argtypes = [w.HANDLE, ctypes.POINTER(Stream)]
    kernel.FindNextStreamW.restype = w.BOOL
    kernel.FindClose.argtypes = [w.HANDLE]
    data = Stream()
    handle = kernel.FindFirstStreamW(str(path), 0, ctypes.byref(data), 0)
    if handle == w.HANDLE(-1).value:
        if ctypes.get_last_error() == 38:  # ERROR_HANDLE_EOF
            return
        raise OSError('stream-enumeration-unavailable')
    try:
        while True:
            if data.name != '::$DATA':
                raise OSError('named-streams-unsupported')
            if not kernel.FindNextStreamW(handle, ctypes.byref(data)):
                if ctypes.get_last_error() != 38:
                    raise OSError('stream-enumeration-unavailable')
                break
    finally:
        kernel.FindClose(handle)


def _win_stage_owner_group(path, security):
    """Keep the private staging DACL, but preserve the original owner/group."""
    w, kernel, advapi = _windows()
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.ULONG)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    advapi.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p]
    advapi.SetFileSecurityW.restype = w.BOOL
    descriptor = ctypes.c_void_p()
    identity = security.split('D:', 1)[0]
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(identity, 1, ctypes.byref(descriptor), None):
        raise OSError('owner-group-unavailable')
    try:
        if not advapi.SetFileSecurityW(str(path), 1 | 2, descriptor):
            raise OSError('owner-group-preserve')
    finally:
        kernel.LocalFree(descriptor)


def _win_stage_security(c, path, security):
    """Restore the exact original descriptor while the staging file is empty.

    SetFileSecurityW is intentionally used for its legacy DACL model. Modern
    SetSecurityInfo/ReplaceFileW may append inherited parent ACEs. An unexpected
    control/ACE result is a hard pre-commit failure, never normalized away.
    """
    _win_stage_owner_group(path, security)
    w, kernel, advapi = _windows()
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.ULONG)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    advapi.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p]
    advapi.SetFileSecurityW.restype = w.BOOL
    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(security, 1, ctypes.byref(descriptor), None):
        raise c.SetupError('RECOVERY_WINDOWS_STAGE_SECURITY_UNAVAILABLE')
    try:
        if not advapi.SetFileSecurityW(str(path), 4, descriptor):
            raise c.SetupError('RECOVERY_WINDOWS_STAGE_SECURITY_COPY_FAILED')
    finally:
        kernel.LocalFree(descriptor)
    observed = _win_security(path)
    if observed != security:
        error = c.SetupError('RECOVERY_WINDOWS_STAGE_SECURITY_MISMATCH')
        error.recovery_diagnostics = {'windows_stage_security': _win_security_comparison(security, observed)}
        raise error


def _win_creation_time(path):
    w, kernel, _ = _windows()
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.GetFileTime.argtypes = [w.HANDLE, ctypes.POINTER(w.FILETIME), ctypes.c_void_p, ctypes.c_void_p]
    kernel.GetFileTime.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80, 7, None, 3, 0x00200000, None)
    if handle == w.HANDLE(-1).value:
        raise OSError('creation-time-unavailable')
    try:
        value = w.FILETIME()
        if not kernel.GetFileTime(handle, ctypes.byref(value), None, None):
            raise OSError('creation-time-unavailable')
        return (value.dwHighDateTime << 32) | value.dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def _win_stage_attributes(path, fd, expected):
    import msvcrt
    w, kernel, _ = _windows()
    kernel.SetFileTime.argtypes = [w.HANDLE, ctypes.POINTER(w.FILETIME), ctypes.c_void_p, ctypes.c_void_p]
    kernel.SetFileTime.restype = w.BOOL
    kernel.SetFileAttributesW.argtypes = [w.LPCWSTR, w.DWORD]
    kernel.SetFileAttributesW.restype = w.BOOL
    stamp = expected['metadata']['creation_time_100ns']
    creation = w.FILETIME(stamp & 0xffffffff, stamp >> 32)
    if not kernel.SetFileTime(msvcrt.get_osfhandle(fd), ctypes.byref(creation), None, None):
        raise OSError('creation-time-preserve')
    if not kernel.SetFileAttributesW(str(path), expected['fingerprint']['attributes']):
        raise OSError('file-attributes-preserve')


def _win_make_private(path):
    w, kernel, advapi = _windows()
    class Attributes(ctypes.Structure):
        _fields_ = [('length', w.DWORD), ('descriptor', ctypes.c_void_p), ('inherit', w.BOOL)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.ULONG)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    kernel.CreateDirectoryW.argtypes = [w.LPCWSTR, ctypes.POINTER(Attributes)]
    kernel.CreateDirectoryW.restype = w.BOOL
    sid = _win_sid()
    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW('O:' + sid + 'D:P(A;OICI;FA;;;' + sid + ')(A;OICI;FA;;;SY)', 1, ctypes.byref(descriptor), None):
        raise OSError('private-acl')
    try:
        attrs = Attributes(ctypes.sizeof(Attributes), descriptor, False)
        if not kernel.CreateDirectoryW(str(path), ctypes.byref(attrs)):
            raise OSError('private-directory')
    finally:
        kernel.LocalFree(descriptor)


def _win_private_stage(parent, protected=True):
    """Create an empty stage; the exact final DACL is checked before any data.

    Match the source protection model at creation. An unprotected empty file
    may initially inherit parent ACEs; _win_stage_security removes unintended
    grants and validates the whole descriptor before writing candidate bytes.
    """
    import msvcrt
    w, kernel, advapi = _windows()
    class Attributes(ctypes.Structure):
        _fields_ = [('length', w.DWORD), ('descriptor', ctypes.c_void_p), ('inherit', w.BOOL)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.ULONG)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.POINTER(Attributes), w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    sid = _win_sid()
    descriptor = ctypes.c_void_p()
    protection = 'P' if protected else ''
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW('O:' + sid + 'D:' + protection + '(A;;FA;;;' + sid + ')(A;;FA;;;SY)', 1, ctypes.byref(descriptor), None):
        raise OSError('private-stage-acl')
    handle = None
    path = parent / ('.claude-recovery-' + uuid.uuid4().hex + '.tmp')
    try:
        attrs = Attributes(ctypes.sizeof(Attributes), descriptor, False)
        handle = kernel.CreateFileW(str(path), 0x80000000 | 0x40000000, 7, ctypes.byref(attrs), 1, 0x80, None)
        if handle == w.HANDLE(-1).value:
            handle = None
            raise OSError('private-stage-create')
        fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        handle = None  # descriptor now owns the native handle
        return fd, str(path)
    finally:
        if handle is not None:
            kernel.CloseHandle(handle)
        kernel.LocalFree(descriptor)


def _private_dir(c, value, create=False):
    p, _ = _safe_path(c, value, directory=True, missing=create)
    try:
        if create:
            if os.name == 'nt':
                _win_make_private(p)
            else:
                p.mkdir(mode=0o700)
        info = p.lstat()
        if os.name == 'nt':
            c.require(_win_acl_summary(p)['private'], 'RECOVERY_PRIVATE_ACL_REQUIRED')
        else:
            c.require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'RECOVERY_PRIVATE_DIRECTORY_REQUIRED')
            if platform.system() == 'Darwin':
                # macOS ACLs can grant access independently of mode bits. An
                # inherited extended ACL must not silently expose credentials.
                c.require(_metadata(p).get('acl') is None, 'RECOVERY_PRIVATE_ACL_REQUIRED')
    except c.SetupError:
        raise
    except OSError:
        raise c.SetupError('RECOVERY_PRIVATE_DIRECTORY_UNAVAILABLE') from None
    return p


def _metadata(path):
    info = path.lstat()
    if os.name == 'nt':
        # Staging and native rename must preserve this descriptor. Read-only/system,
        # EFS, sparse, compressed and reparse targets require a native adapter.
        if getattr(info, 'st_file_attributes', 0) & (1 | 4 | 0x200 | 0x400 | 0x800 | 0x4000):
            raise OSError('attributes-unsupported')
        _win_no_named_streams(path)
        return {'security': _win_security(path), 'attributes': getattr(info, 'st_file_attributes', 0) & ~0x20,
                'creation_time_100ns': _win_creation_time(path)}
    if getattr(info, 'st_flags', 0):
        raise OSError('flags-unsupported')
    attrs = {}
    if platform.system() == 'Darwin' and not hasattr(os, 'listxattr'):
        # Some bundled Python builds omit xattr wrappers; libc still provides
        # the native API. Never silently downgrade metadata verification.
        libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        libc.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        libc.listxattr.restype = ctypes.c_ssize_t
        libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        libc.getxattr.restype = ctypes.c_ssize_t
        size = libc.listxattr(os.fsencode(path), None, 0, 1)
        if size < 0 or size > MAX_META:
            raise OSError('xattrs-unavailable')
        names = ctypes.create_string_buffer(size)
        if libc.listxattr(os.fsencode(path), names, size, 1) != size:
            raise OSError('xattrs-changed')
        total = size
        for name in sorted(x for x in names.raw.split(b'\0') if x):
            length = libc.getxattr(os.fsencode(path), name, None, 0, 0, 1)
            if length < 0 or total + length > MAX_META:
                raise OSError('xattrs-unavailable')
            buffer = ctypes.create_string_buffer(length)
            if libc.getxattr(os.fsencode(path), name, buffer, length, 0, 1) != length:
                raise OSError('xattrs-changed')
            attrs[os.fsdecode(name)] = buffer.raw.hex()
            total += length
    elif hasattr(os, 'listxattr'):
        for key in sorted(os.listxattr(path, follow_symlinks=False)):
            value = os.getxattr(path, key, follow_symlinks=False)
            if sum(len(k) + len(bytes.fromhex(v)) for k, v in attrs.items()) + len(key) + len(value) > MAX_META:
                raise OSError('metadata-too-large')
            attrs[key] = value.hex()
    result = {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid, 'xattrs': attrs}
    if platform.system() == 'Darwin':
        libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        libc.acl_get_file.argtypes = [ctypes.c_char_p, ctypes.c_int]
        libc.acl_get_file.restype = ctypes.c_void_p
        libc.acl_to_text.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ssize_t)]
        libc.acl_to_text.restype = ctypes.c_void_p
        libc.acl_free.argtypes = [ctypes.c_void_p]
        acl = libc.acl_get_file(os.fsencode(path), 0x100)
        if not acl:
            # Darwin returns ENOENT for an existing file with no extended ACL.
            # The surrounding snapshot independently rechecks file existence
            # and identity, so an actual disappearance still rejects the read.
            if ctypes.get_errno() == 2:
                result['acl'] = None
                return result
            raise OSError('acl-unavailable')
        value = None
        try:
            length = ctypes.c_ssize_t()
            value = libc.acl_to_text(acl, ctypes.byref(length))
            if not value or length.value > MAX_META:
                raise OSError('acl-unavailable')
            result['acl'] = ctypes.string_at(value, length.value).decode('utf-8')
        finally:
            if value:
                libc.acl_free(value)
            libc.acl_free(acl)
    return result


def _snapshot(c, value):
    p, chain = _target_path(c, value)
    before = _fingerprint(p.lstat())
    try:
        data = c.read_bytes(p)
        metadata = _metadata(p)
    except OSError:
        raise c.SetupError('RECOVERY_METADATA_UNAVAILABLE_OR_UNSUPPORTED') from None
    final, final_chain = _target_path(c, value)
    c.require(before == _fingerprint(final.lstat()) and chain == final_chain, 'RECOVERY_TARGET_CHANGED_DURING_READ')
    c.parse_config(data, EXTENSIONS[p.suffix.lower()])
    return data, {'path': str(p), 'parents': chain, 'fingerprint': before,
                  'sha256': c.sha(data), 'metadata': metadata}


def _sync_dir(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write(c, path, data):
    # Windows CRT _commit (os.fsync) requires a writable descriptor. Persist on
    # the same exclusive-create handle; reopening after write would introduce
    # an unnecessary identity race and a read-only handle cannot be committed.
    fd = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        flags |= getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOINHERIT', 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            fd = None  # fdopen now owns the descriptor
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_dir(path.parent)
    except OSError:
        raise c.SetupError('RECOVERY_DURABLE_WRITE_FAILED') from None
    finally:
        if fd is not None:
            os.close(fd)


def _pin(c, data, supplied, code):
    c.require(isinstance(supplied, str) and re.fullmatch('[0-9a-f]{64}', supplied) is not None and c.sha(data) == supplied, code)


def _artifact(c, folder, filename, supplied, kind):
    directory = _private_dir(c, folder)
    path, _ = _safe_path(c, directory / filename)
    raw = c.read_bytes(path)
    _pin(c, raw, supplied, 'RECOVERY_ARTIFACT_PIN_MISMATCH')
    data = c.load_json(raw)
    c.require(isinstance(data, dict) and data.get('schema') == PRIVATE_SCHEMA and data.get('kind') == kind and data.get('binding') == _binding(), 'RECOVERY_ARTIFACT_BINDING_MISMATCH')
    return directory, data


def _row(key, title, passed, reason, next_step):
    return {'id': key, 'title': title, 'status': '已完成' if passed else '未完成', 'required': True,
            'reason': reason, 'next_step': next_step}


def _report(c, folder, command, rows, extra, private=None):
    extra = dict(extra, config_file_changed=extra.get('config_file_changed', False),
                 system_settings_changed=extra.get('config_file_changed', False),
                 system_changes_performed=extra.get('config_file_changed', False),
                 proxy_reloaded=False, runtime_adoption_verified=False, network_requests=0)
    try:
        import readiness_lifecycle as lifecycle
        result = lifecycle.save_report(c, folder, command, rows, extra=extra, private=private, create=False)
        result.update(extra)
        result.update(status='已完成' if all(x['status'] == '已完成' for x in rows) else '未完成', report_written=True)
        return result
    except Exception:
        # A report-write failure after a commit must not fall through the main
        # CLI's generic "nothing changed" error branch.
        return dict(extra, status='未完成', required_checks_completed=False, report_written=False,
                    reason_code='RECOVERY_REPORT_WRITE_FAILED',
                    next_step='保留私有操作目录；用 recovery-check 核对 intent 和备份，再审阅恢复方案。')


def prepare(c, target, candidate, output):
    before, bound = _snapshot(c, target)
    other, _ = _target_path(c, candidate)
    after, candidate_bound = _snapshot(c, other)
    c.require(bound['path'] != candidate_bound['path'] and
              (bound['fingerprint']['device'], bound['fingerprint']['inode']) !=
              (candidate_bound['fingerprint']['device'], candidate_bound['fingerprint']['inode']), 'RECOVERY_DISTINCT_CANDIDATE_REQUIRED')
    fmt = EXTENSIONS[Path(bound['path']).suffix.lower()]
    c.require(EXTENSIONS[other.suffix.lower()] == fmt, 'RECOVERY_CANDIDATE_FORMAT_MISMATCH')
    c.parse_config(after, fmt)
    c.require(before != after, 'RECOVERY_NO_CHANGE')
    folder = _private_dir(c, output, create=True)
    plan = {'schema': PRIVATE_SCHEMA, 'kind': 'plan', 'created_at': c.now(), 'binding': _binding(),
            'id': uuid.uuid4().hex, 'target': bound, 'format': fmt,
            'original_sha256': c.sha(before), 'candidate_sha256': c.sha(after),
            'scope': 'explicit_local_text_file_only', 'authorization_saved': False}
    raw = c.encode(plan)
    _write(c, folder / 'original.private.bin', before)
    _write(c, folder / 'candidate.private.bin', after)
    diff = ''.join(difflib.unified_diff(c.decode(before).splitlines(True), c.decode(after).splitlines(True), fromfile='original', tofile='candidate'))
    _write(c, folder / 'diff.private.txt', diff.encode())
    _write(c, folder / 'plan.json', raw)
    _write(c, folder / 'plan.sha256', (c.sha(raw) + '\n').encode())
    return _report(c, folder, 'recovery-plan', [_row('plan', '恢复方案与私有差异', True,
        '目标身份、原文快照、候选差异和哈希已绑定；尚未写入目标。',
        '先确认具体差异；安全停止目标写入者后，本轮明确允许才执行 apply。')],
        {'plan_sha256': c.sha(raw), 'config_file_changed': False, 'recovery_state': 'prepared'})


def _snapshots(c, folder, record):
    before = c.read_bytes(_safe_path(c, folder / 'original.private.bin')[0])
    after = c.read_bytes(_safe_path(c, folder / 'candidate.private.bin')[0])
    c.require(c.sha(before) == record.get('original_sha256') and c.sha(after) == record.get('candidate_sha256'), 'RECOVERY_BACKUP_INTEGRITY_MISMATCH')
    c.require(record.get('format') in ('yaml', 'json', 'shadowrocket'), 'RECOVERY_FORMAT_INVALID')
    c.parse_config(before, record['format'])
    c.parse_config(after, record['format'])
    target = record.get('target')
    c.require(isinstance(target, dict) and isinstance(target.get('path'), str) and
              isinstance(target.get('fingerprint'), dict) and isinstance(target.get('parents'), list) and
              isinstance(target.get('metadata'), dict) and isinstance(target.get('sha256'), str), 'RECOVERY_TARGET_RECORD_INVALID')
    c.require(EXTENSIONS.get(Path(target['path']).suffix.lower()) == record['format'] and
              target['sha256'] == c.sha(before), 'RECOVERY_TARGET_RECORD_INVALID')
    return before, after


def _assert_expected(c, path, expected):
    data, observed = _snapshot(c, path)
    c.require(observed == expected, 'RECOVERY_TARGET_CONFLICT')
    return data


def _stage(c, target, data, expected):
    if os.name == 'nt':
        security = expected['metadata']['security']
        protected = _win_security_comparison(security, security)['expected_dacl_control']['protected']
        fd, name = _win_private_stage(target.parent, protected)
    else:
        fd, name = tempfile.mkstemp(prefix='.claude-recovery-', suffix='.tmp', dir=target.parent)
    stage = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if os.name == 'nt':
                # Validate the final ACL on an empty file, before any candidate
                # credentials could be exposed to an unexpected inherited ACE.
                _win_stage_security(c, stage, expected['metadata']['security'])
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            if os.name == 'nt':
                _win_stage_attributes(stage, stream.fileno(), expected)
                c.require(_metadata(stage) == expected['metadata'], 'RECOVERY_STAGE_METADATA_MISMATCH')
            if os.name != 'nt':
                if platform.system() == 'Darwin':
                    source = os.open(target, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                    try:
                        libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
                        libc.fcopyfile.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
                        libc.fcopyfile.restype = ctypes.c_int
                        if libc.fcopyfile(source, stream.fileno(), None, 1 | 2 | 4):
                            raise OSError('metadata-copy')
                    finally:
                        os.close(source)
                else:
                    os.fchown(stream.fileno(), expected['metadata']['uid'], expected['metadata']['gid'])
                    os.fchmod(stream.fileno(), expected['metadata']['mode'])
                    for key, value in expected['metadata']['xattrs'].items():
                        os.setxattr(stage, key, bytes.fromhex(value), follow_symlinks=False)
                os.utime(stream.fileno(), None)
                c.require(_metadata(stage) == expected['metadata'], 'RECOVERY_STAGE_METADATA_MISMATCH')
            os.fsync(stream.fileno())
        c.require(c.read_bytes(stage) == data, 'RECOVERY_STAGE_READBACK_MISMATCH')
        return stage
    except BaseException:
        stage.unlink(missing_ok=True)
        raise


def _replace(c, stage, target, expected, stage_identity):
    if os.name == 'nt':
        # Windows rename-replace has no compare-and-swap contract. Recheck as
        # close as possible, require stopped writers, and verify afterwards.
        _assert_expected(c, target, expected)
        c.require(_fingerprint(stage.lstat()) == stage_identity, 'RECOVERY_STAGE_CHANGED')
        c.require(stage.parent == target.parent and stage_identity['device'] == expected['fingerprint']['device'], 'RECOVERY_SAME_DIRECTORY_VOLUME_REQUIRED')
        c.require(_metadata(stage) == expected['metadata'], 'RECOVERY_STAGE_METADATA_MISMATCH')
        w, kernel, _ = _windows()
        kernel.MoveFileExW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.DWORD]
        kernel.MoveFileExW.restype = w.BOOL
        # Never enable COPY_ALLOWED: only the already prepared file identity
        # may be renamed over this local, same-directory target. Unlike
        # ReplaceFileW, this does not merge a broader parent DACL into the file.
        if not kernel.MoveFileExW(str(stage), str(target), 0x1 | 0x8):
            raise OSError('replace-failed')
    else:
        fd = os.open(target.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        try:
            actual = target.parent.lstat()
            c.require((actual.st_dev, actual.st_ino) == (os.fstat(fd).st_dev, os.fstat(fd).st_ino), 'RECOVERY_PARENT_CHANGED')
            planned_parent = expected['parents'][-1]
            c.require(planned_parent[0] == str(target.parent) and
                      (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == tuple(planned_parent[1:]), 'RECOVERY_PARENT_CHANGED')
            actual_target = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
            actual_stage = os.stat(stage.name, dir_fd=fd, follow_symlinks=False)
            c.require(stat.S_ISREG(actual_target.st_mode) and _fingerprint(actual_target) == expected['fingerprint'], 'RECOVERY_TARGET_CONFLICT')
            c.require(stat.S_ISREG(actual_stage.st_mode) and _fingerprint(actual_stage) == stage_identity, 'RECOVERY_STAGE_CHANGED')
            os.replace(stage.name, target.name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(fd)


def _load_receipt(c, folder, pin):
    folder = _private_dir(c, folder)
    intent_raw = c.read_bytes(_safe_path(c, folder / 'intent.private.json')[0])
    final_path = folder / 'receipt.private.json'
    final = None
    if final_path.exists():
        final_path, _ = _safe_path(c, final_path)
        raw = c.read_bytes(final_path)
        if c.sha(raw) == pin:
            final = c.load_json(raw)
            c.require(isinstance(final, dict) and final.get('schema') == PRIVATE_SCHEMA and final.get('kind') == 'receipt'
                      and final.get('intent_sha256') == c.sha(intent_raw) and final.get('binding') == _binding(), 'RECOVERY_RECEIPT_INVALID')
        else:
            # An intent pin can inspect an incomplete run, but never trusts an
            # unpinned final receipt or enables its automatic rollback.
            _pin(c, intent_raw, pin, 'RECOVERY_RECEIPT_INTEGRITY_MISMATCH')
    else:
        _pin(c, intent_raw, pin, 'RECOVERY_ARTIFACT_PIN_MISMATCH')
    _, intent = _artifact(c, folder, 'intent.private.json', c.sha(intent_raw), 'intent')
    before, after = _snapshots(c, folder, intent)
    return folder, intent, final, before, after


def _inspection(c, intent, final):
    try:
        data, observed = _snapshot(c, intent['target']['path'])
    except (c.SetupError, OSError, KeyError, TypeError):
        return 'target_unavailable', None
    if final and final.get('state') == 'committed' and final.get('target_after') == observed:
        return 'committed_unchanged', observed
    if observed == intent['target']:
        return 'original_unchanged', observed
    if c.sha(data) == intent['candidate_sha256']:
        return 'candidate_observed_receipt_incomplete' if final is None or final.get('state') != 'committed' else 'subsequent_change_conflict', observed
    return 'subsequent_change_conflict', observed


def _transaction(c, original, candidate, expected, folder, origin, action):
    target = Path(expected['path'])
    lock = target.parent / ('.claude-recovery-' + hashlib.sha256(str(target).encode()).hexdigest()[:24] + '.lock')
    lock_fd = None
    lock_identity = None
    stage = None
    intent = None
    intent_pin = None
    changed = False
    attempted = False
    state = 'not_committed'
    current = None
    error = None
    lock_cleanup_completed = True
    readback_checks = None
    try:
        # The lock remains after a hard interruption. Never delete another run's
        # lock automatically; an operator must first inspect its private intent.
        try:
            lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except OSError:
            raise c.SetupError('RECOVERY_LOCK_EXISTS_OR_UNAVAILABLE') from None
        lock_identity = os.fstat(lock_fd)
        _assert_expected(c, target, expected)
        _write(c, folder / 'original.private.bin', original)
        _write(c, folder / 'candidate.private.bin', candidate)
        stage = _stage(c, target, candidate, expected)
        intent = {'schema': PRIVATE_SCHEMA, 'kind': 'intent', 'binding': _binding(), 'created_at': c.now(),
                  'id': uuid.uuid4().hex, 'action': action, 'origin_sha256': origin, 'target': expected,
                  'format': EXTENSIONS[target.suffix.lower()], 'original_sha256': c.sha(original),
                  'candidate_sha256': c.sha(candidate), 'stage_identity': _fingerprint(stage.lstat()),
                  'stage_basename': stage.name, 'authorization_saved': False}
        raw = c.encode(intent)
        intent_pin = c.sha(raw)
        _write(c, folder / 'intent.private.json', raw)
        _write(c, folder / 'intent.sha256', (intent_pin + '\n').encode())
        # Keep raw private paths out of a lock placed alongside the target.
        os.write(lock_fd, c.encode({'intent_sha256': intent_pin}))
        os.fsync(lock_fd)
        _sync_dir(target.parent)
        _assert_expected(c, target, expected)
        c.require(c.read_bytes(stage) == candidate and _fingerprint(stage.lstat()) == intent['stage_identity'], 'RECOVERY_STAGE_CHANGED')
        attempted = True
        _replace(c, stage, target, expected, intent['stage_identity'])
        changed = True
        state = 'committed_readback_pending'
        actual, current = _snapshot(c, target)
        readback_checks = {'content_matches': actual == candidate,
                           'metadata_matches': current['metadata'] == expected['metadata'],
                           'metadata_keys_match': {key: current['metadata'].get(key) == expected['metadata'].get(key)
                              for key in ('mode', 'uid', 'gid', 'xattrs', 'acl', 'security', 'attributes', 'creation_time_100ns')
                              if key in current['metadata'] or key in expected['metadata']},
                           'stage_device_matches': current['fingerprint']['device'] == intent['stage_identity']['device'],
                           'stage_inode_matches': current['fingerprint']['inode'] == intent['stage_identity']['inode']}
        if os.name == 'nt' and not readback_checks['metadata_keys_match'].get('security', True):
            try:
                readback_checks['windows_security'] = _win_security_comparison(expected['metadata']['security'], current['metadata']['security'])
            except Exception:
                readback_checks['windows_security'] = {'available': False}
        if os.name == 'nt':
            readback_checks['windows_attribute_flags'] = {'expected': expected['metadata'].get('attributes'),
                                                        'actual': current['metadata'].get('attributes')}
        c.require(all(readback_checks[key] for key in ('content_matches', 'metadata_matches', 'stage_device_matches', 'stage_inode_matches')), 'RECOVERY_READBACK_MISMATCH')
        state = 'committed'
    except (Exception, KeyboardInterrupt) as exc:
        error = str(exc) if isinstance(exc, c.SetupError) else 'RECOVERY_TRANSACTION_IO_OR_INTERRUPTED'
        if isinstance(exc, c.SetupError) and hasattr(exc, 'recovery_diagnostics'):
            readback_checks = exc.recovery_diagnostics
        if attempted:
            try:
                actual, current = _snapshot(c, target)
                changed = current != expected
                state = 'not_committed' if current == expected else 'commit_unverified'
            except (c.SetupError, OSError, KeyError, TypeError):
                changed, state = True, 'commit_state_unknown'
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
                observed = lock.lstat()
                if (observed.st_dev, observed.st_ino) == (lock_identity.st_dev, lock_identity.st_ino):
                    lock.unlink()
                    _sync_dir(lock.parent)
                else:
                    lock_cleanup_completed = False
            except OSError:
                lock_cleanup_completed = False
        if stage is not None and stage.exists() and not attempted:
            try:
                stage.unlink()
            except OSError:
                pass
    receipt_written = False
    receipt_pin = None
    if intent is not None:
        receipt = {'schema': PRIVATE_SCHEMA, 'kind': 'receipt', 'binding': _binding(), 'created_at': c.now(),
                   'intent_sha256': intent_pin, 'state': state, 'target_after': current,
                   'write_attempted': attempted, 'config_file_changed': changed, 'error_code': error,
                   'readback_checks': readback_checks}
        try:
            raw = c.encode(receipt)
            _write(c, folder / 'receipt.private.json', raw)
            receipt_pin = c.sha(raw)
            _write(c, folder / 'receipt.sha256', (receipt_pin + '\n').encode())
            receipt_written = True
        except Exception:
            pass
    rows = [_row('file_transaction', '配置文本' + ('恢复' if action == 'rollback' else '写入') + '与读回', state == 'committed',
        '候选已原子替换并读回；文件权限及可支持的元数据已核对。' if state == 'committed' else
        ('已尝试写入，当前状态未完全确认；不能当作未改动。' if attempted else '提交前校验或暂存未完成，目标没有由本工具提交。'),
        '客户端没有重载；安全交接给客户后，重新验证实际采用。' if state == 'committed' else '保留操作目录，先用 recovery-check 核对；有冲突则先审阅客户后续修改。'),
        _row('receipt', '私有恢复记录', receipt_written, '不可变 intent、备份和最终回执已保存。' if receipt_written else '最终回执或 intent 未完整保存，不能自动认定可回滚。',
             '保留本机私有目录及 intent.sha256；回滚仍需本轮确认。' if receipt_written else '保留已有 intent、备份及临时文件；检查存储空间和权限，人工审阅恢复。')]
    if not lock_cleanup_completed:
        rows.append(_row('lock_cleanup', '操作锁清理', False,
            '目标处理结束，但本次操作锁未能可靠清理或同步；可能阻止后续恢复。',
            '先检查私有 intent 和当前目标；确认没有运行中的写入者，再人工处理本次遗留锁。'))
    return _report(c, folder, 'recovery-' + ('rollback' if action == 'rollback' else 'apply'), rows,
                   {'config_file_changed': changed, 'write_attempted': attempted, 'recovery_state': state,
                    'receipt_complete': receipt_written, 'receipt_sha256': receipt_pin, 'intent_sha256': intent_pin,
                    'reason_code': error, 'lock_cleanup_completed': lock_cleanup_completed,
                    'readback_checks': readback_checks, 'target_runtime_verified': False})


def apply(c, folder, pin, allow, stopped, output):
    c.require(allow and stopped, 'RECOVERY_CURRENT_WRITE_AND_STOPPED_CONFIRMATION_REQUIRED')
    c.require(platform.system() in ('Darwin', 'Windows'), 'RECOVERY_NATIVE_MAC_OR_WINDOWS_REQUIRED')
    folder, plan = _artifact(c, folder, 'plan.json', pin, 'plan')
    before, after = _snapshots(c, folder, plan)
    c.require(isinstance(plan.get('target'), dict) and plan['target'].get('sha256') == c.sha(before), 'RECOVERY_PLAN_INVALID')
    _assert_expected(c, plan['target']['path'], plan['target'])
    dest = _private_dir(c, output, create=True)
    return _transaction(c, before, after, plan['target'], dest, pin, 'apply')


def check(c, folder, pin, output):
    folder, intent, final, _, _ = _load_receipt(c, folder, pin)
    state, current = _inspection(c, intent, final)
    dest = _private_dir(c, output, create=True)
    intact = state == 'committed_unchanged'
    reason = {'committed_unchanged': '目标仍与本次提交后身份、内容和元数据完全一致，可准备受保护的恢复。',
              'original_unchanged': '目标仍是提交前状态；没有需要自动撤销的本次提交。',
              'candidate_observed_receipt_incomplete': '观察到候选字节，但缺少完整成功回执；不能证明期间没有其他修改。',
              'subsequent_change_conflict': '目标身份、内容或元数据后来发生变化；已阻止自动覆盖。',
              'target_unavailable': '目标无法可靠读取，不能确认提交状态。'}[state]
    rows = [_row('backup', '私有备份完整性', True, '原始快照和候选快照已按 intent 校验。', '保留本机私有备份；记录不提供新授权。'),
            _row('recovery_target', '当前目标与安全恢复条件', intact, reason,
                 '确认恢复差异并安全停止写入者；本轮允许后再执行 rollback。' if intact else
                 '先审阅现场文件与备份；目标已变或回执缺失时人工合并，不能强制覆盖。')]
    return _report(c, dest, 'recovery-check', rows,
                   {'config_file_changed': False, 'recovery_state': state, 'safe_automatic_rollback_available': intact,
                    'receipt_sha256': pin, 'receipt_complete': final is not None}, private={'observed': current})


def rollback(c, folder, pin, allow, stopped, output):
    c.require(allow and stopped, 'RECOVERY_CURRENT_WRITE_AND_STOPPED_CONFIRMATION_REQUIRED')
    c.require(platform.system() in ('Darwin', 'Windows'), 'RECOVERY_NATIVE_MAC_OR_WINDOWS_REQUIRED')
    folder, intent, final, before, after = _load_receipt(c, folder, pin)
    state, current = _inspection(c, intent, final)
    c.require(state == 'committed_unchanged', 'RECOVERY_ROLLBACK_CONFLICT_OR_INCOMPLETE_RECEIPT')
    dest = _private_dir(c, output, create=True)
    return _transaction(c, after, before, current, dest, pin, 'rollback')


def run(c, args):
    if args.command == 'recovery-plan':
        return prepare(c, args.target, args.candidate, args.out)
    if args.command == 'recovery-apply':
        return apply(c, args.plan, args.plan_sha256, args.allow_write, args.writer_stopped, args.out)
    if args.command == 'recovery-rollback':
        return rollback(c, args.receipt, args.receipt_sha256, args.allow_write, args.writer_stopped, args.out)
    if args.command == 'recovery-check':
        return check(c, args.receipt, args.receipt_sha256, args.out)
    raise c.SetupError('RECOVERY_COMMAND_UNKNOWN')
