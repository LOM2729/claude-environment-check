"""Terminal handoff protocol with injected prompts/runners; no sudo, UAC or network."""
import argparse
from contextlib import contextmanager
import copy
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import guard_handoff as handoff
import system_guard as guard


def spec(target='macos'):
    value = {'schema': 'clearpath-guard-input/1', 'scope': 'fixture', 'platform': target,
             'mode': 'egress', 'policy': 'unified-v4', 'interfaces': ['en0'], 'tunnels': ['utun3'],
             'nodes': [{'address': '203.0.113.2', 'ports': [443], 'protocol': 'tcp'}],
             'exceptions': [], 'bootstrap_dns': [], 'fuse_seconds': 180}
    if target == 'windows':
        value.update(interfaces=['Ethernet'], tunnels=['Mihomo'], core_path=r'C:\Program Files\Mihomo\core.exe', windows_disable_rules=[])
    return value


class TTY(io.StringIO):
    def isatty(self):
        return True
    def fileno(self):
        return 99


class GuardHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-guard-handoff-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        runtime = self.root / "runtime ' $HOME % !"
        runtime.mkdir(mode=0o700)
        exe = runtime / "tool ' $ %.exe";exe.write_bytes(b'synthetic, never executed')
        self.prefix = [str(exe), '--cli']
        self.plan = guard.make_plan(spec())
        self.bundle = self.root / "bundle ' $HOME % !"
        self.bundle.mkdir(mode=0o700)
        (self.bundle / 'plan.json').write_bytes(c.encode(self.plan))
        self.pin = guard.digest(self.plan)
        self.clock = [10000.0]
        self.phase = 'pending_confirmation'
        self.token = '1' * 32
        self.calls, self.rollbacks, self.prompts = [], [], []
        self.answers = ['APPLY', 'CONFIRM']
        self.output = TTY()
        self.args = argparse.Namespace(command='guard-launch', bundle=str(self.bundle), plan_sha256=self.pin, manifest_sha256=None)

    def export(self, checks=None):
        with patch.object(guard, 'native_platform', return_value='macos'):
            return handoff.export_launchers(c, self.plan, self.bundle, checks, self.prefix)

    def reader(self, prompt, seconds):
        self.prompts.append((prompt, seconds))
        return self.answers.pop(0) if self.answers else None

    def state(self, plan, folder):
        return {'phase': self.phase, 'plan_sha256': self.pin, 'recovery_nonce': self.token, 'expires_at': 10180.0}

    def runner(self, context, args):
        self.calls.append(args)
        self.assertEqual(args.plan_sha256, self.pin)
        self.assertTrue(args.allow_system_change and args.control_channel_independent and args.recovery_ready)
        if args.command == 'guard-on':
            return {'status': 'applied_pending_confirmation', 'exit_code': 2, 'plan_sha256': self.pin, 'transaction_id': self.token}
        self.assertEqual(args.command, 'guard-confirm')
        if args.transaction_id != self.token:
            raise guard.GuardError('GUARD_TRANSACTION_MISMATCH')
        witness = c.load_json(c.read_bytes(args.verification_file))
        self.assertEqual(witness['source'], 'fresh_customer_terminal_confirmation')
        self.assertEqual(witness['management_path'], 'observed')
        self.phase = 'confirmed'
        return {'status': 'configuration_confirmed', 'exit_code': 0, 'persistent': True}

    def rollback(self, plan, folder, token):
        self.rollbacks.append(token)
        if token == self.token and self.phase == 'pending_confirmation':
            self.phase = 'restored'
            return {'status': 'restored', 'rolled_back': True}
        return {'status': 'not_our_pending_generation', 'rolled_back': False}

    def launch(self, **kwargs):
        options = dict(runner=self.runner, reader=self.reader, read_state=self.state, rollback=self.rollback,
                       input_stream=TTY(), output_stream=self.output, prefix=self.prefix,
                       state_directory=self.root / 'synthetic-state', wall=lambda: self.clock[0], admin=True)
        options.update(kwargs)
        with patch.object(guard, 'native_platform', return_value='macos'):
            return handoff.launch(c, self.args, **options)

    def check_plan(self):
        return {'schema': 'claude-network-plan/1', 'phase': 'bootstrap', 'checks': [
            {'id': 'neutral_https', 'type': 'https', 'required': True, 'url': 'https://example.com/',
             'route': 'direct', 'family': 'ipv4', 'expected_statuses': [200]}]}

    def test_offline_export_shell_quotes_paths_and_manifest_binds_all_entries(self):
        exported = self.export()
        self.assertTrue(exported['launcher_generated'])
        self.assertEqual(exported['network_requests'], 0)
        text = (self.bundle / '启用断线保护.command').read_text(encoding='utf-8')
        static = next(line.strip() for line in text.splitlines() if line.startswith('  ') and '/usr/bin/sudo' not in line)
        self.assertEqual(shlex.split(static), self.prefix + ['guard-launch', '--bundle', str(self.bundle), '--plan-sha256', self.pin])
        self.assertIn('/usr/bin/sudo -- ', text)
        manifest = c.load_json(c.read_bytes(self.bundle / 'launch-manifest.private.json'))
        self.assertEqual(manifest['files']['启用断线保护.command'], c.sha((self.bundle / '启用断线保护.command').read_bytes()))
        self.assertFalse(manifest['authorization_saved'])
        self.assertEqual(exported['launch_manifest_sha256'], c.sha(c.read_bytes(self.bundle / 'launch-manifest.private.json')))

    def test_non_target_export_does_not_create_a_fake_launcher(self):
        with patch.object(guard, 'native_platform', return_value='windows'):
            result = handoff.export_launchers(c, self.plan, self.bundle, runtime_prefix=self.prefix)
        self.assertFalse(result['launcher_generated'])
        self.assertEqual(result['launcher_status'], 'export_on_actual_target')
        self.assertFalse((self.bundle / 'launch-manifest.private.json').exists())

    def test_windows_entry_uses_literal_prefix_percent_safe_cmd_bom_and_visible_uac(self):
        self.plan = guard.make_plan(spec('windows'));self.pin = guard.digest(self.plan)
        (self.bundle / 'plan.json').write_bytes(c.encode(self.plan))
        with patch.object(guard, 'native_platform', return_value='windows'), \
                patch.object(guard, 'windows_directory', return_value=Path('C:/ProgramData')), \
                patch.object(handoff, '_windows_powershell', return_value=r'C:\Windows%literal!\powershell.exe'):
            handoff.export_launchers(c, self.plan, self.bundle, runtime_prefix=self.prefix)
        cmd = (self.bundle / '启用断线保护.cmd').read_text(encoding='utf-8')
        self.assertIn('DisableDelayedExpansion', cmd)
        self.assertIn(r'C:\Windows%%literal!\powershell.exe', cmd)
        self.assertIn('"%~dp0launch-guard.ps1"', cmd)
        raw = (self.bundle / 'launch-guard.ps1').read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        text = raw.decode('utf-8-sig')
        self.assertIn('-Verb RunAs -WindowStyle Normal', text)
        self.assertIn(handoff._ps(self.prefix[0]), text)
        self.assertIn('Start-Process -FilePath ' + handoff._ps(self.prefix[0]), text)
        fixed_arguments = self.prefix[1:] + ['guard-launch', '--bundle', str(self.bundle),
                                           '--plan-sha256', self.pin, '--keep-open']
        self.assertIn('-ArgumentList ' + handoff._ps(subprocess.list2cmdline(fixed_arguments)), text)
        self.assertNotIn('$PSCommandPath', text)
        self.assertNotIn('-WindowStyle Hidden', text)

    def test_source_identity_includes_private_acl_dependency(self):
        source = self.root / 'source-runtime'
        source.mkdir(mode=0o700)
        for name in handoff.CODE_FILES:
            (source / name).write_bytes(b'synthetic runtime source')
        prefix = [self.prefix[0], str(source / 'claude_setup.py')]
        before = handoff.runtime_identity(prefix)
        self.assertIn(str(source / 'config_recovery.py'), before['files'])
        (source / 'config_recovery.py').write_bytes(b'changed private ACL code')
        self.assertNotEqual(before, handoff.runtime_identity(prefix))

    def test_windows_preview_discloses_pending_native_persistence(self):
        text = handoff._render(guard.make_plan(spec('windows')), None)
        self.assertIn('Windows原生策略写入即持久', text)
        self.assertIn('SYSTEM限时与开机恢复任务', text)
        self.assertNotIn('确认前不新增开机加载', text)

    def test_summary_interrupt_after_confirm_does_not_claim_no_dispatch(self):
        self.export()
        original_launch = handoff.launch
        class InterruptedSummary(TTY):
            def write(stream, text):
                if '本次配置已确认' in text:
                    raise KeyboardInterrupt()
                return super().write(text)
        output = InterruptedSummary()
        def execute(context, args):
            with patch.object(guard, 'native_platform', return_value='macos'):
                return original_launch(context, args, runner=self.runner, reader=self.reader,
                    read_state=self.state, rollback=self.rollback, input_stream=TTY(), output_stream=output,
                    prefix=self.prefix, state_directory=self.root / 'synthetic-state',
                    wall=lambda: self.clock[0], admin=True)
        with patch.object(handoff, 'launch', side_effect=execute):
            result = handoff._run(c, self.args)
        self.assertEqual(self.phase, 'confirmed')
        self.assertEqual([x.command for x in self.calls], ['guard-on', 'guard-confirm'])
        self.assertEqual(result['status'], 'interrupted_inspect_before_retry')
        self.assertIsNone(result['system_changes_performed'])
        self.assertNotIn('尚未派发', result['message'])

    @unittest.skipUnless(os.name == 'nt', 'Windows native argument/parser checks only; no UAC execution')
    def test_windows_generated_bootstrap_parses_and_preserves_fixed_runtime_arguments(self):
        import ctypes
        self.plan = guard.make_plan(spec('windows'));self.pin = guard.digest(self.plan)
        (self.bundle / 'plan.json').write_bytes(c.encode(self.plan))
        handoff.export_launchers(c, self.plan, self.bundle, runtime_prefix=self.prefix)
        text = (self.bundle / 'launch-guard.ps1').read_text(encoding='utf-8-sig')
        import re
        literal = re.search(r"-ArgumentList ('(?:''|[^'])*') -Verb RunAs", text).group(1)
        argument_line = literal[1:-1].replace("''", "'")
        shell32 = ctypes.WinDLL('shell32', use_last_error=True)
        shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        count = ctypes.c_int()
        pointer = shell32.CommandLineToArgvW('runtime.exe ' + argument_line, ctypes.byref(count))
        self.assertTrue(pointer)
        try:
            parsed = [pointer[i] for i in range(count.value)][1:]
        finally:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree(pointer)
        self.assertEqual(parsed, self.prefix[1:] + ['guard-launch', '--bundle', str(self.bundle),
                                                   '--plan-sha256', self.pin, '--keep-open'])
        checker = self.root / 'parse-only.ps1'
        checker.write_text("param([string]$Source)\n$tokens=$null;$errors=$null\n"
            "[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)|Out-Null\n"
            "if($errors.Count){Write-Output 'ENTRY_SYNTAX_INVALID';exit 1}\n", encoding='utf-8-sig')
        result = subprocess.run([handoff._windows_powershell(), '-NoLogo', '-NoProfile', '-NonInteractive',
            '-File', str(checker), '-Source', str(self.bundle / 'launch-guard.ps1')],
            capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_tty_and_no_admin_fail_before_any_dispatch(self):
        self.export()
        with self.assertRaisesRegex(handoff.HandoffError, 'REAL_TERMINAL_REQUIRED'):
            self.launch(input_stream=io.StringIO())
        with self.assertRaisesRegex(handoff.HandoffError, 'ADMINISTRATOR_TERMINAL_REQUIRED'):
            self.launch(admin=False)
        self.assertFalse(self.calls or self.rollbacks)

    def test_cancel_apply_does_not_change_any_state_or_start_checks(self):
        self.export(self.check_plan());self.answers = ['CANCEL']
        result = self.launch(network_runner=lambda *args: self.fail('no network before APPLY'))
        self.assertEqual(result['status'], 'cancelled_before_apply')
        self.assertIs(result['system_changes_performed'], False)
        self.assertFalse(self.calls or self.rollbacks)
        self.assertIn('https://example.com/', self.output.getvalue())

    def test_pending_exit_two_is_successful_trial_and_manual_confirmation_is_explicit(self):
        self.export();result = self.launch()
        self.assertEqual(result['status'], 'configuration_confirmed')
        self.assertFalse(result['network_verified'])
        self.assertEqual([x.command for x in self.calls], ['guard-on', 'guard-confirm'])
        self.assertIn('没有自动检查计划', self.output.getvalue())
        self.assertNotIn('三项已通过', self.output.getvalue())
        self.assertEqual(len(self.prompts), 2)
        self.assertFalse(self.rollbacks)

    def test_check_failure_rolls_back_only_this_pending_generation(self):
        self.export(self.check_plan())
        result = self.launch(network_runner=lambda *args: ([{'id': 'neutral_https', 'status': '未完成'}], []))
        self.assertTrue(result['rolled_back'])
        self.assertEqual(self.phase, 'restored')
        self.assertEqual([x.command for x in self.calls], ['guard-on'])
        self.assertEqual(self.rollbacks, [self.token])
        self.assertEqual(len(self.prompts), 1)

    def test_successful_checks_do_not_replace_customer_management_confirmation(self):
        self.export(self.check_plan())
        result = self.launch(network_runner=lambda *args: ([{'id': 'neutral_https', 'status': '已完成'}], []))
        self.assertEqual(result['status'], 'configuration_confirmed')
        self.assertEqual(len(self.prompts), 2)
        self.assertIn('独立管理通道', self.prompts[1][0])

    def test_unknown_apply_and_old_confirmed_never_trigger_rollback(self):
        self.export()
        def unknown(*args):
            raise OSError('private-secret-not-for-summary')
        result = self.launch(runner=unknown)
        self.assertEqual(result['status'], 'incomplete_inspect_before_retry')
        self.assertIsNone(result['system_changes_performed'])
        self.assertFalse(result['rolled_back'])
        self.assertFalse(self.rollbacks)
        self.assertNotIn('private-secret', json.dumps(result))
        self.assertTrue(all('private-secret' not in p.read_text(encoding='utf-8') for p in self.bundle.glob('handoff-*.private.json')))
        self.answers = ['APPLY']
        result = self.launch(runner=lambda *args: {'status': 'confirmed', 'exit_code': 0, 'plan_sha256': self.pin})
        self.assertFalse(result['rolled_back'])
        self.assertFalse(self.rollbacks)

    def test_confirmation_timeout_expiry_and_cancel_never_commit(self):
        self.export();self.answers = ['APPLY', None]
        result = self.launch()
        self.assertTrue(result['rolled_back'])
        self.assertFalse(any(x.command == 'guard-confirm' for x in self.calls))
        self.phase = 'pending_confirmation';self.calls.clear();self.answers = ['APPLY', 'CONFIRM']
        original = self.reader
        def late(prompt, seconds):
            answer = original(prompt, seconds)
            if 'CONFIRM' in prompt:
                self.clock[0] = 10181
            return answer
        result = self.launch(reader=late)
        self.assertEqual(result['reason_code'], 'HANDOFF_CONFIRMATION_EXPIRED')
        self.assertFalse(any(x.command == 'guard-confirm' for x in self.calls))

    def test_changed_generation_or_confirmed_state_is_not_rolled_back(self):
        self.export(self.check_plan())
        def became_confirmed(*args):
            self.phase = 'confirmed'
            return [{'id': 'neutral_https', 'status': '未完成'}], []
        result = self.launch(network_runner=became_confirmed)
        self.assertFalse(result['rolled_back'])
        self.assertEqual(self.phase, 'confirmed')

    def test_confirm_binds_generation_atomically_even_if_reactivation_follows_fresh_read(self):
        self.export()
        original = self.state
        reads = [0]
        def changed_after_read(plan, folder):
            value = original(plan, folder)
            reads[0] += 1
            if reads[0] == 2:
                self.token = '2' * 32  # Another terminal replaced the pending generation after the read.
            return value
        result = self.launch(read_state=changed_after_read)
        self.assertEqual(result['reason_code'], 'GUARD_TRANSACTION_MISMATCH')
        self.assertEqual(self.phase, 'pending_confirmation')
        self.assertFalse(result['rolled_back'])
        self.assertEqual(self.calls[-1].transaction_id, '1' * 32)
        self.assertEqual(self.rollbacks, ['1' * 32])

    def test_atomic_rollback_rechecks_nonce_and_phase_under_existing_guard_lock(self):
        host = type('Host', (), {'check': lambda self, folder: None})()
        state_dir = self.root / 'state';state_dir.mkdir(mode=0o700)
        with patch.object(guard, 'NativeHost', return_value=host), \
                patch.object(guard, '_load_state', return_value={'plan_sha256': self.pin, 'recovery_nonce': self.token, 'phase': 'confirmed'}), \
                patch.object(guard, '_deactivate_locked') as mutate:
            result = handoff._rollback_pending(self.plan, state_dir, self.token)
            self.assertFalse(result['rolled_back']);mutate.assert_not_called()
        with patch.object(guard, 'NativeHost', return_value=host), \
                patch.object(guard, '_load_state', return_value={'plan_sha256': self.pin, 'recovery_nonce': '2' * 32, 'phase': 'pending_confirmation'}), \
                patch.object(guard, '_deactivate_locked') as mutate:
            result = handoff._rollback_pending(self.plan, state_dir, self.token)
            self.assertFalse(result['rolled_back']);mutate.assert_not_called()

    def test_manifest_and_runtime_tamper_fail_before_prompts_or_execution(self):
        self.export()
        (self.bundle / '启用断线保护.command').write_text('# changed launcher')
        with self.assertRaisesRegex(handoff.HandoffError, 'BUNDLE_FILE_CHANGED'):
            self.launch()
        self.assertFalse(self.calls or self.prompts)

    def test_manifest_cannot_supply_a_program_or_replace_the_current_runtime(self):
        self.export()
        path = self.bundle / 'launch-manifest.private.json'
        manifest = c.load_json(c.read_bytes(path))
        manifest['program'] = ['/bin/sh', '-c', 'do-not-execute']
        path.write_bytes(c.encode(manifest))
        with self.assertRaisesRegex(handoff.HandoffError, 'MANIFEST_INVALID'):
            self.launch()
        del manifest['program']
        manifest['runtime']['files'] = {'/untrusted/program': '0' * 64}
        path.write_bytes(c.encode(manifest))
        with self.assertRaisesRegex(handoff.HandoffError, 'RUNTIME_CHANGED'):
            self.launch()
        self.assertFalse(self.calls or self.prompts)

    def test_service_check_plan_and_ai_bootstrap_targets_are_not_accepted(self):
        bad = self.check_plan();bad['phase'] = 'service'
        with self.assertRaisesRegex(handoff.HandoffError, 'BOOTSTRAP_CHECK_PLAN_REQUIRED'):
            self.export(bad)
        bad = self.check_plan();bad['checks'][0]['url'] = 'https://claude.ai/'
        with self.assertRaisesRegex(c.SetupError, 'BOOTSTRAP_AI_TARGET_FORBIDDEN'):
            self.export(bad)

    def test_checks_must_leave_confirmation_budget_both_at_export_and_after_apply(self):
        value = spec();value['fuse_seconds'] = 60
        self.plan = guard.make_plan(value);self.pin = guard.digest(self.plan);self.args.plan_sha256 = self.pin
        (self.bundle / 'plan.json').write_bytes(c.encode(self.plan))
        checks = self.check_plan()
        checks['checks'] = [dict(checks['checks'][0], id='probe_' + str(n)) for n in range(4)]
        with self.assertRaisesRegex(handoff.HandoffError, 'CHECK_PLAN_EXCEEDS_FUSE_WINDOW'):
            self.export(checks)
        self.assertFalse((self.bundle / 'check-plan.private.json').exists())
        self.export(self.check_plan())
        def short_window(plan, folder):
            value = self.state(plan, folder);value['expires_at'] = self.clock[0] + 20;return value
        result = self.launch(read_state=short_window, network_runner=lambda *args: self.fail('insufficient window must not start probes'))
        self.assertEqual(result['reason_code'], 'HANDOFF_CHECK_WINDOW_TOO_SHORT')
        self.assertTrue(result['rolled_back'])

    @unittest.skipIf(sys.platform == 'win32', 'POSIX select/termios branch only')
    def test_real_terminal_reader_flushes_before_prompt_and_times_out_without_reading(self):
        stream, output, events = TTY(), TTY(), []
        write = output.write
        def show(value):
            events.append('prompt');return write(value)
        output.write = show
        with patch('termios.tcflush', side_effect=lambda *args: events.append('flush')), \
                patch.object(handoff.select, 'select', return_value=([], [], [])):
            self.assertIsNone(handoff.terminal_read(stream, output, 'CONFIRM: ', .001))
        self.assertEqual(events, ['flush', 'prompt'])


if __name__ == '__main__':
    unittest.main()
