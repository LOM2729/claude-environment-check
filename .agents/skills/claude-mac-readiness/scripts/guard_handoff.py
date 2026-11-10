"""Visible terminal APPLY/CONFIRM handoff for an exact exported guard plan.

Export is offline. Launch accepts fresh terminal input and dispatches only fixed
system_guard operations; saved JSON never supplies an executable or permission.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import stat
import subprocess
import sys
import time
import uuid

import system_guard as guard

COMMANDS = ('guard-launch',)
SCHEMA = 'clearpath-guard-handoff/1'
MAX_MANIFEST = 1024 * 1024
MAX_RUNTIME = 512 * 1024 * 1024
CODE_FILES = ('claude_setup.py', 'guard_handoff.py', 'system_guard.py', 'system_guard_windows.ps1',
              'network_checks.py', 'ai_routing.py', 'ai_domains.json', 'config_recovery.py')
CHECK_WORKER_SECONDS = 9
MIN_CONFIRM_SECONDS = 30


class HandoffError(guard.GuardError):
    pass


def need(condition, code):
    if not condition:
        raise HandoffError(code)


def _pin(value):
    need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'HANDOFF_DIGEST_REQUIRED')
    return value


def _folder(value):
    p = Path(value).absolute()
    need(not any(ord(ch) < 32 for ch in str(p)), 'HANDOFF_PATH_INVALID')
    need(p.is_dir(), 'HANDOFF_BUNDLE_REQUIRED')
    for item in (p, *p.parents):
        info = item.lstat()
        need(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
             'HANDOFF_LINK_REJECTED')
    if os.name != 'nt':
        need(stat.S_IMODE(p.stat().st_mode) == 0o700, 'HANDOFF_PRIVATE_BUNDLE_REQUIRED')
    return p


def _file_hash(path, maximum=MAX_RUNTIME):
    p = Path(path)
    need(not p.is_symlink() and p.is_file(), 'HANDOFF_RUNTIME_FILE_UNAVAILABLE')
    before = p.stat()
    need(before.st_size <= maximum, 'HANDOFF_RUNTIME_BUDGET_EXCEEDED')
    h, size = hashlib.sha256(), 0
    with p.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        need((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino), 'HANDOFF_RUNTIME_CHANGED')
        while True:
            block = stream.read(65536)
            if not block:
                break
            size += len(block)
            need(size <= maximum, 'HANDOFF_RUNTIME_BUDGET_EXCEEDED')
            h.update(block)
        after = os.fstat(stream.fileno())
    final = p.stat()
    shape = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
    need(shape(before) == shape(after) == shape(final), 'HANDOFF_RUNTIME_CHANGED')
    return h.hexdigest()


def runtime_prefix(c):
    """Derived from the currently running trusted program, never from JSON."""
    if getattr(sys, 'frozen', False):
        return [str(Path(sys.executable).absolute()), '--cli']
    script = Path(getattr(c, '__file__', Path(__file__).with_name('claude_setup.py'))).absolute()
    need(script.name == 'claude_setup.py', 'HANDOFF_SOURCE_ENTRY_UNAVAILABLE')
    return [str(Path(sys.executable).absolute()), str(script)]


def runtime_identity(prefix):
    need(type(prefix) in (list, tuple) and len(prefix) == 2 and
         all(type(x) is str and x and not any(ord(ch) < 32 for ch in x) for x in prefix),
         'HANDOFF_RUNTIME_PREFIX_INVALID')
    executable = Path(prefix[0]).absolute().resolve(strict=True)
    files = {str(executable): _file_hash(executable)}
    if prefix[1] == '--cli':
        mode = 'frozen'
    else:
        script = Path(prefix[1]).absolute().resolve(strict=True)
        need(script.name == 'claude_setup.py', 'HANDOFF_SOURCE_ENTRY_UNAVAILABLE')
        mode = 'source'
        for name in CODE_FILES:
            p = script.with_name(name)
            need(p.is_file(), 'HANDOFF_RUNTIME_FILE_UNAVAILABLE')
            files[str(p)] = _file_hash(p)
    return {'mode': mode, 'prefix_sha256': guard.digest(list(prefix)), 'files': files}


def _ps(value):
    need(type(value) is str and not any(x in value for x in ('\r', '\n', '\x00')), 'HANDOFF_PATH_INVALID')
    return "'" + value.replace("'", "''") + "'"


def _windows_powershell():
    return str(guard.windows_directory() / 'System32/WindowsPowerShell/v1.0/powershell.exe')


def _offline_note(plan, prefix):
    folder = str(guard.NativeHost(plan['spec']).root())
    check = list(prefix) + ['guard-status', '--state-dir', folder]
    restore = list(prefix) + ['guard-off', '--state-dir', folder, '--plan-sha256', guard.digest(plan),
                            '--allow-system-change', '--control-channel-independent', '--recovery-ready']
    windows = plan['spec']['platform'] == 'windows'
    def command(argv):
        return '& ' + ' '.join(_ps(x) for x in argv) if windows else '/usr/bin/sudo -- ' + ' '.join(shlex.quote(x) for x in argv)
    return ('本次计划摘要：' + guard.digest(plan) + '\n状态目录：' + folder + '\n\n'
        '不需要在线Agent；保留当前工具和本目录。先在独立管理员终端检查状态：\n' + command(check) + '\n\n'
        '只有核对仍是本次计划、已准备独立控制和恢复，并明确决定撤销时才手动运行：\n' + command(restore) + '\n\n'
        'guard-off也会撤销已确认保护，不是自动重试命令；不同计划、后续编辑或状态不明时先停下调查。\n'
        '未确认时独立保险丝会尝试恢复；不能用经过时间代替实际状态读回。\n').encode('utf-8')


def _scripts(platform, prefix, folder, plan_pin):
    arguments = list(prefix) + ['guard-launch', '--bundle', str(folder), '--plan-sha256', plan_pin]
    if platform in ('macos', 'linux'):
        command = ' '.join(shlex.quote(x) for x in arguments)
        text = ('#!/bin/bash\nset -u\n'
                'printf "%s\\n" "将在可见管理员终端中核对方案；密码仅由系统终端处理。"\n'
                'if [ "$(id -u)" -eq 0 ]; then\n  ' + command + '\nelse\n  /usr/bin/sudo -- ' + command + '\nfi\n'
                'clearpath_status=$?\nprintf "%s\\n" "本次操作已结束；请查看上方结果和私有记录。"\n'
                'read -r -p "按回车关闭：" clearpath_done\nexit "$clearpath_status"\n')
        return {'启用断线保护.command' if platform == 'macos' else 'launch-guard.sh': text.encode('utf-8')}
    executable = _windows_powershell()
    need('"' not in executable and not any(ch in executable for ch in '\r\n\x00'), 'HANDOFF_POWERSHELL_PATH_INVALID')
    # cmd expands percent literals; delayed expansion is disabled for exclamation marks.
    cmd = '@echo off\r\nsetlocal DisableDelayedExpansion\r\n"' + executable.replace('%', '%%') + '" -NoLogo -NoProfile -File "%~dp0launch-guard.ps1"\r\nexit /b %errorlevel%\r\n'
    # Elevate only the fixed current runtime. Never execute this writable bundle
    # script at elevated privilege before the runtime has verified its manifest.
    elevated_arguments = subprocess.list2cmdline(arguments[1:] + ['--keep-open'])
    ps = ("$ErrorActionPreference='Stop'\n"
          "$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)\n"
          "if(-not $admin){\n  Write-Host '接下来显示UAC，打开可见管理员终端；系统认证后仍需查看方案并输入APPLY。'\n"
          "  try{$p=Start-Process -FilePath " + _ps(prefix[0]) +
          " -ArgumentList " + _ps(elevated_arguments) +
          " -Verb RunAs -WindowStyle Normal -PassThru -Wait;exit $p.ExitCode}\n"
          "  catch{Write-Host '未打开管理员终端或UAC已取消；没有申请网络变更。';Read-Host '按回车关闭';exit 2}\n}\n"
          "$runtime=@(" + ','.join(_ps(x) for x in prefix) + ")\n"
          "try{& $runtime[0] @($runtime[1]) 'guard-launch' '--bundle' " + _ps(str(folder)) +
          " '--plan-sha256' " + _ps(plan_pin) + ";$code=$LASTEXITCODE}\n"
          "catch{Write-Host '入口未完成，请保留私有材料并核对状态。';$code=2}\n"
          "Read-Host '按回车关闭';exit $code\n")
    return {'启用断线保护.cmd': cmd.encode('utf-8'), 'launch-guard.ps1': b'\xef\xbb\xbf' + ps.encode('utf-8')}


def export_launchers(c, plan, folder, network_plan=None, runtime_prefix=None):
    """Called after guard-export created plan.json. No launch, elevation or network."""
    guard.validate_plan(plan)
    target = plan['spec']['platform']
    if target != guard.native_platform():
        return {'launcher_generated': False, 'launcher_status': 'export_on_actual_target', 'target_platform': target,
                'system_changes_performed': False, 'network_requests': 0}
    folder = _folder(folder)
    if os.name == 'nt':
        import config_recovery
        config_recovery._private_dir(c, folder)
    prefix = list(runtime_prefix or globals()['runtime_prefix'](c))
    identity = runtime_identity(prefix)
    plan_raw = c.read_bytes(folder / 'plan.json', guard.MAX_INPUT)
    need(c.load_json(plan_raw) == plan, 'HANDOFF_EXPORTED_PLAN_MISMATCH')
    files = {'plan.json': c.sha(plan_raw)}
    for name in ('system_guard.py', 'system_guard_windows.ps1'):
        p = folder / name
        if p.exists():
            expected = plan['runtime_sha256'] if name.endswith('.py') else plan.get('windows_backend_sha256')
            actual = _file_hash(p, MAX_MANIFEST)
            if expected is not None:
                need(actual == expected, 'HANDOFF_RECOVERY_CODE_CHANGED')
            files[name] = actual
    if network_plan is not None:
        import network_checks
        checks = network_checks.validate_plan(c, network_plan)
        need(checks.get('phase') == 'bootstrap', 'HANDOFF_BOOTSTRAP_CHECK_PLAN_REQUIRED')
        need(CHECK_WORKER_SECONDS * len(checks['checks']) + MIN_CONFIRM_SECONDS <= plan['spec']['fuse_seconds'],
             'HANDOFF_CHECK_PLAN_EXCEEDS_FUSE_WINDOW')
        c.write_new(folder / 'check-plan.private.json', c.encode(checks))
        files['check-plan.private.json'] = _file_hash(folder / 'check-plan.private.json', MAX_MANIFEST)
    scripts = _scripts(target, prefix, folder, guard.digest(plan))
    for name, raw in scripts.items():
        c.write_new(folder / name, raw)
        if target in ('macos', 'linux'):
            os.chmod(folder / name, 0o700)
        files[name] = c.sha(raw)
    offline = _offline_note(plan, prefix)
    c.write_new(folder / '离线恢复.txt', offline)
    files['离线恢复.txt'] = c.sha(offline)
    manifest = {'schema': SCHEMA, 'created_at': c.now(), 'platform': target, 'plan_sha256': guard.digest(plan),
        'files': files, 'runtime': identity, 'network_plan': 'check-plan.private.json' if network_plan is not None else None,
        'authorization_saved': False, 'network_verified': False}
    raw = c.encode(manifest)
    c.write_new(folder / 'launch-manifest.private.json', raw)
    return {'launcher_generated': True, 'launcher_status': 'ready_for_customer_terminal',
            'launcher_files': list(scripts), 'launch_manifest_sha256': c.sha(raw),
            'system_changes_performed': False, 'network_requests': 0}


def _load_bundle(c, folder, plan_pin, manifest_pin, prefix):
    folder = _folder(folder)
    if os.name == 'nt':
        import config_recovery
        config_recovery._private_dir(c, folder)
    _pin(plan_pin)
    raw = c.read_bytes(folder / 'launch-manifest.private.json', MAX_MANIFEST)
    if manifest_pin is not None:
        need(c.sha(raw) == _pin(manifest_pin), 'HANDOFF_MANIFEST_CHANGED')
    manifest = c.load_json(raw)
    fields = {'schema', 'created_at', 'platform', 'plan_sha256', 'files', 'runtime', 'network_plan',
              'authorization_saved', 'network_verified'}
    need(type(manifest) is dict and set(manifest) == fields and manifest['schema'] == SCHEMA and
         manifest['authorization_saved'] is False and manifest['network_verified'] is False,
         'HANDOFF_MANIFEST_INVALID')
    need(manifest['platform'] == guard.native_platform(), 'HANDOFF_ACTUAL_TARGET_REQUIRED')
    need(manifest['runtime'] == runtime_identity(prefix), 'HANDOFF_RUNTIME_CHANGED')
    allowed = {'plan.json', 'check-plan.private.json', '启用断线保护.command', 'launch-guard.sh', '启用断线保护.cmd', 'launch-guard.ps1',
               'system_guard.py', 'system_guard_windows.ps1', '离线恢复.txt'}
    files = manifest['files']
    entries = {'macos': {'启用断线保护.command'}, 'linux': {'launch-guard.sh'}, 'windows': {'启用断线保护.cmd', 'launch-guard.ps1'}}[manifest['platform']]
    all_entries = {'启用断线保护.command', 'launch-guard.sh', '启用断线保护.cmd', 'launch-guard.ps1'}
    need(type(files) is dict and {'plan.json', '离线恢复.txt'} <= set(files) and set(files) <= allowed and 3 <= len(files) <= 7
         and set(files) & all_entries == entries,
         'HANDOFF_MANIFEST_FILE_SCOPE')
    for name, expected in files.items():
        need(_file_hash(folder / name, MAX_MANIFEST) == _pin(expected), 'HANDOFF_BUNDLE_FILE_CHANGED')
    plan = guard.validate_plan(c.load_json(c.read_bytes(folder / 'plan.json', guard.MAX_INPUT)))
    need(guard.digest(plan) == plan_pin == manifest['plan_sha256'] and plan['spec']['platform'] == manifest['platform'],
         'HANDOFF_PLAN_CHANGED')
    network = None
    if manifest['network_plan'] is not None:
        need(manifest['network_plan'] == 'check-plan.private.json' and 'check-plan.private.json' in files,
             'HANDOFF_CHECK_PLAN_SCOPE')
        import network_checks
        network = network_checks.validate_plan(c, c.load_json(c.read_bytes(folder / 'check-plan.private.json', MAX_MANIFEST)))
        need(network.get('phase') == 'bootstrap', 'HANDOFF_BOOTSTRAP_CHECK_PLAN_REQUIRED')
        need(CHECK_WORKER_SECONDS * len(network['checks']) + MIN_CONFIRM_SECONDS <= plan['spec']['fuse_seconds'],
             'HANDOFF_CHECK_PLAN_EXCEEDS_FUSE_WINDOW')
    return folder, plan, network


def _tty(stream):
    try:
        return stream is not None and stream.isatty()
    except (AttributeError, OSError):
        return False


def terminal_read(input_stream, output_stream, prompt, seconds):
    """Flush before displaying each decision; no cached APPLY+CONFIRM or pipes."""
    need(_tty(input_stream) and _tty(output_stream), 'HANDOFF_REAL_TERMINAL_REQUIRED')
    if seconds <= 0:
        return None
    if os.name == 'nt':
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
    else:
        import termios
        termios.tcflush(input_stream.fileno(), termios.TCIFLUSH)
    output_stream.write(prompt);output_stream.flush()
    if os.name != 'nt':
        if not select.select([input_stream.fileno()], [], [], seconds)[0]:
            return None
        line = input_stream.readline(64)
        return line.strip() if line.endswith('\n') else None
    import msvcrt
    end, chars = time.monotonic() + seconds, []
    while time.monotonic() < end:
        if not msvcrt.kbhit():
            time.sleep(.05);continue
        ch = msvcrt.getwch()
        if ch == '\x03':
            raise KeyboardInterrupt()
        if ch in ('\x00', '\xe0'):
            msvcrt.getwch();continue
        if ch in ('\r', '\n'):
            output_stream.write('\n');output_stream.flush();return ''.join(chars)
        if ch == '\b':
            if chars:
                chars.pop();output_stream.write('\b \b');output_stream.flush()
        elif ch.isascii() and ch.isalpha() and len(chars) < 32:
            chars.append(ch);output_stream.write(ch);output_stream.flush()
    return None


def _read_state(plan, folder):
    host = guard.NativeHost(plan['spec'], expected_backend_sha256=plan.get('windows_backend_sha256'))
    host.check(folder)
    with guard.operation_lock(folder):
        return guard._load_state(folder)


def _rollback_pending(plan, folder, transaction_id):
    host = guard.NativeHost(plan['spec'], expected_backend_sha256=plan.get('windows_backend_sha256'))
    host.check(folder)
    with guard.operation_lock(folder):
        state = guard._load_state(folder)
        if (state.get('plan_sha256') != guard.digest(plan) or state.get('recovery_nonce') != transaction_id or
                state.get('phase') != 'pending_confirmation'):
            return {'status': 'not_our_pending_generation', 'rolled_back': False}
        result = guard._deactivate_locked(folder, guard.digest(plan), host)
        return {'status': result['status'], 'rolled_back': result['status'] in ('restored', 'uninstalled')}


def _dispatch(c, args):
    return guard.run(c, args)


def _network(c, plan):
    import network_checks
    return network_checks.run_checks(c, plan, True)


def _error_code(error):
    value = str(error)
    return value if re.fullmatch(r'(?:HANDOFF|GUARD|NETWORK|DNS_READY)_[A-Z0-9_]{1,100}', value) else 'HANDOFF_OPERATION_INCOMPLETE'


def _render(plan, checks):
    lines = ['本次系统防护方案：', json.dumps(plan['spec'], ensure_ascii=True, indent=2),
        '影响：指定接口／规则可能中断网络；已有连接不保证立即终止；不会修改DNS。',
        '恢复：写入前由guard保存当前基线并启动独立限时撤销；未确认会撤销本次待确认改动。',
        '请准备独立控制通道和离线恢复入口；状态不明时先核对，不能重复APPLY。']
    if plan['spec']['platform'] == 'windows':
        lines.append('Windows原生策略写入即持久；待确认时保留SYSTEM限时与开机恢复任务，确认后才撤恢复任务。')
    else:
        lines.append('确认前不新增开机加载，确认后才按方案保留防护。')
    if checks is None:
        lines += ['本包没有自动检查计划；不会声称任何网络项目已通过。', '应用后请自行实际检查正常使用及独立管理通道，再决定CONFIRM。']
    else:
        lines += ['本轮外部检查端点与数据：']
        for check in checks['checks']:
            target = check.get('url') or check['host'] + (':' + str(check['port']) if check['type'] == 'stun' else '')
            lines.append(json.dumps({'id': check['id'], 'type': check['type'], 'target': target,
                'route': check.get('route', 'system_path'), 'proxy': check.get('proxy'),
                'family': check.get('family', 'auto'), 'required': check['required']}, ensure_ascii=True))
        lines += ['端点可看到请求来源及检测请求；DNS解析方可看到查询名；不发送登录凭据。',
                  '所有计划检查成功后仍需你现场确认管理通道；样本不证明整机保护。']
    return '\n'.join(lines) + '\n'


def launch(c, args, runner=None, reader=None, read_state=None, rollback=None, network_runner=None,
           input_stream=None, output_stream=None, prefix=None, state_directory=None, wall=None, admin=None):
    """Injectable protocol tests use synthetic state; the CLI exposes no bypass flags."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    need(_tty(input_stream) and _tty(output_stream), 'HANDOFF_REAL_TERMINAL_REQUIRED')
    prefix = list(prefix or runtime_prefix(c))
    folder, plan, checks = _load_bundle(c, args.bundle, args.plan_sha256, args.manifest_sha256, prefix)
    if admin is None:
        if os.name == 'nt':
            import ctypes
            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        else:
            admin = os.geteuid() == 0
    need(admin, 'HANDOFF_ADMINISTRATOR_TERMINAL_REQUIRED')
    runner, read_state, rollback = runner or _dispatch, read_state or _read_state, rollback or _rollback_pending
    network_runner, wall = network_runner or _network, wall or time.time
    reader = reader or (lambda prompt, seconds: terminal_read(input_stream, output_stream, prompt, seconds))
    state_dir = Path(state_directory) if state_directory is not None else guard.NativeHost(plan['spec']).root()
    output_stream.write(_render(plan, checks));output_stream.flush()
    log = {'schema': 'clearpath-guard-handoff-log/1', 'started_at': c.now(), 'plan_sha256': args.plan_sha256,
           'events': [], 'authorization_saved': False, 'network_verified': False}
    token, created, stage, dispatched = None, False, 'approval', False
    result = None

    def event(name, value):
        log['events'].append({'stage': name, 'result': value})

    def base(command):
        return argparse.Namespace(command=command, state_dir=str(state_dir), plan=str(folder / 'plan.json'),
            plan_sha256=args.plan_sha256, allow_system_change=True, control_channel_independent=True,
            recovery_ready=True, persist=False, verification_file=None, transaction_id=None)

    def cancel(reason):
        data = {'status': reason, 'exit_code': 2, 'network_verified': False, 'rolled_back': False}
        if created and token is not None:
            try:
                undone = rollback(plan, state_dir, token);event('rollback', undone)
                data['rolled_back'] = undone.get('rolled_back') is True
                data['recovery_state'] = undone.get('status', 'inspect_before_retry')
            except Exception as error:
                event('rollback', {'error': _error_code(error)})
                data['recovery_state'] = 'inspect_before_retry'
        return data

    try:
        if reader('已准备独立控制／恢复并同意上方具体方案时，输入 APPLY：', 120) != 'APPLY':
            result = cancel('cancelled_before_apply')
        else:
            stage = 'apply'
            dispatched = True
            applied = runner(c, base('guard-on'));event('apply', applied)
            transaction = applied.get('transaction_id')
            need(applied.get('status') == 'applied_pending_confirmation' and applied.get('exit_code') == 2 and
                 applied.get('plan_sha256') == args.plan_sha256 and type(transaction) is str and
                 re.fullmatch(r'[0-9a-f]{32}', transaction), 'HANDOFF_NEW_PENDING_NOT_ESTABLISHED')
            token, created = transaction, True
            state = read_state(plan, state_dir)
            need(state.get('plan_sha256') == args.plan_sha256 and state.get('recovery_nonce') == token and
                 state.get('phase') == 'pending_confirmation', 'HANDOFF_PENDING_STATE_CHANGED')
            stage = 'checks'
            if checks is not None:
                need(state['expires_at'] - wall() >= CHECK_WORKER_SECONDS * len(checks['checks']) + MIN_CONFIRM_SECONDS,
                     'HANDOFF_CHECK_WINDOW_TOO_SHORT')
                rows, private = network_runner(c, checks)
                event('checks', {'rows': rows, 'private': private})
                need(len(rows) == len(checks['checks']) and {r.get('id') for r in rows} == {r['id'] for r in checks['checks']}
                     and all(r.get('status') == '已完成' for r in rows), 'HANDOFF_CHECKS_INCOMPLETE')
                output_stream.write('本轮计划中的限定检查已完成；仍需现场核实正常使用和独立管理通道。\n')
            remaining = max(0, min(120, state['expires_at'] - wall()))
            need(remaining > 0, 'HANDOFF_CONFIRMATION_EXPIRED')
            stage = 'confirmation'
            answer = reader('实际核实正常使用和独立管理通道均正常后，输入 CONFIRM（本入口最多等待%d秒，确认后保留防护）：' % int(remaining), remaining)
            if answer != 'CONFIRM':
                result = cancel('confirmation_cancelled_or_timed_out')
            else:
                need(wall() < state['expires_at'], 'HANDOFF_CONFIRMATION_EXPIRED')
                fresh = read_state(plan, state_dir)
                need(fresh.get('plan_sha256') == args.plan_sha256 and fresh.get('recovery_nonce') == token and
                     fresh.get('phase') == 'pending_confirmation', 'HANDOFF_PENDING_STATE_CHANGED')
                verification = {'schema': 'clearpath-guard-verification/1', 'plan_sha256': args.plan_sha256,
                    'normal_path': 'observed', 'management_path': 'observed', 'observed_at': c.now(),
                    'source': 'fresh_customer_terminal_confirmation', 'automatic_checks_provided': checks is not None,
                    'network_protection_verified': False}
                receipt = folder / ('verification-' + uuid.uuid4().hex + '.private.json')
                c.write_new(receipt, c.encode(verification))
                command = base('guard-confirm');command.verification_file = str(receipt);command.persist = True
                command.transaction_id = token
                stage = 'commit'
                confirmed = runner(c, command);event('commit', confirmed)
                need(confirmed.get('status') == 'configuration_confirmed' and confirmed.get('exit_code') == 0,
                     'HANDOFF_CONFIRMATION_UNCERTAIN')
                result = {'status': 'configuration_confirmed', 'exit_code': 0, 'network_verified': False,
                          'persistent': True, 'rolled_back': False}
    except (Exception, KeyboardInterrupt) as error:
        code = _error_code(error) if not isinstance(error, KeyboardInterrupt) else 'HANDOFF_INTERRUPTED'
        event(stage, {'error': code})
        result = cancel('incomplete_inspect_before_retry' if not created else 'pending_not_confirmed')
        result['reason_code'] = code
    finally:
        if result is None:
            result = {'status': 'incomplete_inspect_before_retry', 'exit_code': 2, 'network_verified': False, 'rolled_back': False}
        result['system_changes_performed'] = (True if result['status'] == 'configuration_confirmed' or result.get('rolled_back')
                                               else None if dispatched else False)
        result['changes_state'] = ('confirmed' if result['status'] == 'configuration_confirmed' else 'restored' if result.get('rolled_back')
                                   else 'inspect_before_retry' if dispatched else 'not_started')
        log.update(ended_at=c.now(), summary=result)
        try:
            c.write_new(folder / ('handoff-' + uuid.uuid4().hex + '.private.json'), c.encode(log))
            result['private_log_written'] = True
        except Exception:
            result['private_log_written'] = False
        if result['status'] == 'configuration_confirmed':
            output_stream.write('本次配置已确认并保留；整机网络效果仍以实际验收为准。\n')
        elif result.get('rolled_back'):
            output_stream.write('本次未确认；已精确撤回本轮待确认改动，保留私有记录。\n')
        else:
            output_stream.write('本次未完成；请保留私有材料，先核对现场状态和离线恢复，再决定下一步。\n')
        output_stream.flush()
    return result


def register_commands(subparsers):
    p = subparsers.add_parser('guard-launch', help='Visible real-terminal APPLY/CONFIRM handoff for a pinned exported guard plan')
    p.add_argument('--bundle', required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--manifest-sha256')
    p.add_argument('--keep-open', action='store_true', help='Keep the generated Windows console visible after its result')


def _run(c, args):
    try:
        return launch(c, args)
    except KeyboardInterrupt:
        return {'status': 'interrupted_inspect_before_retry', 'exit_code': 2, 'network_verified': False,
                'system_changes_performed': None, 'rolled_back': False, 'reason_code': 'HANDOFF_INTERRUPTED',
                'message': '入口已中断，配置可能已写入；请先核对本轮状态，不要重复APPLY。'}
    except (HandoffError, guard.GuardError) as error:
        return {'status': 'entry_not_ready', 'exit_code': 2, 'network_verified': False, 'rolled_back': False,
                'reason_code': _error_code(error), 'message': '入口未就绪；请核对目标平台、真实管理员终端和导出材料。'}
    except (OSError, ValueError, TypeError, KeyError):
        return {'status': 'entry_not_ready', 'exit_code': 2, 'network_verified': False, 'rolled_back': False,
                'reason_code': 'HANDOFF_ENTRY_INCOMPLETE', 'message': '入口未完成；请保留私有材料并先核对状态。'}


def run(c, args):
    result = _run(c, args)
    if result.get('message') and _tty(sys.stdin) and _tty(sys.stdout):
        sys.stdout.write(result['message'] + '\n')
        if result.get('reason_code'):
            sys.stdout.write('原因：' + result['reason_code'] + '\n')
        sys.stdout.flush()
    if getattr(args, 'keep_open', False) and _tty(sys.stdin) and _tty(sys.stdout):
        try:
            terminal_read(sys.stdin, sys.stdout, '本次入口已结束，按回车关闭：', 120)
        except (KeyboardInterrupt, OSError, ValueError):
            pass
    return result
