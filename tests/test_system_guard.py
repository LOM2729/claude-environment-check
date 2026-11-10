"""Firewall orchestration with synthetic state, fake OS commands and real file locks.

No native firewall, interface enumeration, privileged service or network is used.
"""
import argparse
import base64
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import system_guard as g


def spec(target='linux'):
    result = {'schema': 'clearpath-guard-input/1', 'scope': 'fixture', 'platform': target,
              'mode': 'egress', 'policy': 'explicit-exceptions', 'interfaces': ['eth0'], 'tunnels': ['tun0'],
              'nodes': [{'address': '203.0.113.2', 'ports': [443], 'protocol': 'tcp'}],
              'exceptions': [{'network': '192.0.2.0/24', 'ports': [22], 'protocol': 'tcp', 'direction': 'out', 'purpose': 'management'}],
              'bootstrap_dns': ['1.1.1.1'], 'fuse_seconds': 180}
    if target == 'windows':
        result.update(interfaces=['Ethernet'], tunnels=['Mihomo'], core_path=r'C:\Program Files\Mihomo\mihomo.exe', windows_disable_rules=['fixture-rule'])
    return result


class FakeHost:
    def __init__(self, plan):
        self.plan = plan
        self.current = {'rules': None}
        self.desired = {'rules': g.canonical_nft(g.nft_document(plan['spec']))}
        self.events = []
        self.persistent = False
        self.fail_apply = False
        self.fail_persist = False

    def prepare(self, folder):
        Path(folder).mkdir(mode=0o700)
        self.install_runtime(folder)
    def install_runtime(self, folder):
        g.private_write(Path(folder) / 'runtime.py', b'# synthetic worker\n', True)
    def check(self, folder):
        pass
    def snapshot(self, folder):
        return copy.deepcopy(self.current)
    def validate(self, folder):
        self.events.append('validate')
        return copy.deepcopy(self.desired)
    def arm(self, folder):
        self.events.append('arm')
    def apply(self, folder):
        self.events.append('apply')
        if 'arm' not in self.events:
            raise AssertionError('mutation before independent recovery')
        self.current = copy.deepcopy(self.desired)
        if self.fail_apply:
            raise g.GuardError('SYNTHETIC_LOST_COMMAND_RESPONSE')
    def persist(self, folder):
        self.events.append('persist')
        self.persistent = True
        if self.fail_persist:
            raise g.GuardError('SYNTHETIC_PARTIAL_STARTUP')
    def persistence_status(self, folder):
        self.events.append('startup-readback')
        return self.persistent
    def disarm(self, folder):
        self.events.append('disarm')
    def restore(self, folder, state):
        possible = [state['before'], state.get('desired'), state.get('applied')]
        if self.current not in possible:
            raise g.GuardError('GUARD_RESTORE_CONFLICT')
        self.events.append('restore')
        self.current = copy.deepcopy(state['before'])
        if state.get('persisted') or state.get('startup_pending'):
            self.events.append('unpersist')
            self.persistent = False


class GuardTransactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-guard-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve() / 'state'
        self.identity = patch.object(g, '_machine_identity', return_value=b'synthetic-stable-device')
        self.identity.start()
        self.addCleanup(self.identity.stop)
        self.plan = g.make_plan(spec())
        self.host = FakeHost(self.plan)
        self.expected = g.digest(self.plan)

    def verification(self):
        return {'schema': 'clearpath-guard-verification/1', 'plan_sha256': self.expected,
                'normal_path': 'observed', 'management_path': 'observed'}

    def test_unconfirmed_has_fuse_and_no_persistent_startup(self):
        result = g.activate(self.plan, self.folder, self.host)
        self.assertEqual(result['exit_code'], 2)
        self.assertTrue(result['recovery_armed'])
        self.assertFalse(self.host.persistent)
        self.assertLess(self.host.events.index('arm'), self.host.events.index('apply'))
        self.assertNotIn('persist', self.host.events)
        self.assertEqual(g._load_state(self.folder)['phase'], 'pending_confirmation')

    def test_existing_unbound_directory_is_never_adopted_or_executed(self):
        self.folder.mkdir(mode=0o700)
        (self.folder / 'backend.ps1').write_text('throw "UNTRUSTED_BACKEND"', encoding='utf-8')
        self.host.secure = lambda folder: self.fail('untrusted helper must not self-secure')
        with self.assertRaisesRegex(g.GuardError, 'GUARD_EXISTING_STATE_DIRECTORY_UNBOUND'):
            g.activate(self.plan, self.folder, self.host)
        self.assertEqual(self.host.events, [])
        self.assertEqual((self.folder / 'backend.ps1').read_text(), 'throw "UNTRUSTED_BACKEND"')

    def test_confirm_requires_bound_observations_and_durable_startup_readback(self):
        g.activate(self.plan, self.folder, self.host)
        with self.assertRaisesRegex(g.GuardError, 'GUARD_VERIFICATION_REQUIRED'):
            g.finish(self.folder, self.expected, self.host, {}, True)
        result = g.finish(self.folder, self.expected, self.host, self.verification(), True)
        self.assertEqual(result['status'], 'configuration_confirmed')
        self.assertFalse(result['network_verified'])
        self.assertLess(self.host.events.index('persist'), self.host.events.index('startup-readback'))
        self.assertLess(self.host.events.index('startup-readback'), self.host.events.index('disarm'))
        self.assertEqual(g._load_state(self.folder)['phase'], 'confirmed')

    def test_partial_persist_keeps_recovery_eligible_and_undoes_startup(self):
        g.activate(self.plan, self.folder, self.host)
        self.host.fail_persist = True
        with self.assertRaisesRegex(g.GuardError, 'SYNTHETIC_PARTIAL_STARTUP'):
            g.finish(self.folder, self.expected, self.host, self.verification(), True)
        state = g._load_state(self.folder)
        self.assertEqual(state['phase'], 'confirming')
        self.assertTrue(state['startup_pending'])
        self.assertNotIn('disarm', self.host.events)
        result = g.deactivate(self.folder, self.expected, self.host)
        self.assertTrue(result['startup_restored'])
        self.assertFalse(self.host.persistent)
        self.assertEqual(self.host.current, {'rules': None})

    def test_orphan_state_staging_does_not_block_independent_recovery(self):
        g.activate(self.plan, self.folder, self.host)
        orphan = self.folder / 'state.json.new'
        orphan.write_bytes(b'interrupted-private-material')
        g.finish(self.folder, self.expected, self.host, self.verification(), True)
        g.deactivate(self.folder, self.expected, self.host)
        self.assertEqual(g._load_state(self.folder)['phase'], 'restored')
        self.assertEqual(orphan.read_bytes(), b'interrupted-private-material')

    def test_lost_apply_response_is_reconciled_without_replaying(self):
        self.host.fail_apply = True
        with self.assertRaisesRegex(g.GuardError, 'SYNTHETIC_LOST_COMMAND_RESPONSE'):
            g.activate(self.plan, self.folder, self.host)
        self.assertEqual(g._load_state(self.folder)['phase'], 'apply_uncertain')
        g.deactivate(self.folder, self.expected, self.host)
        self.assertEqual(self.host.events.count('apply'), 1)
        self.assertEqual(self.host.current, {'rules': None})

    def test_off_protects_later_native_edits(self):
        g.activate(self.plan, self.folder, self.host)
        self.host.current = {'rules': [{'foreign-later-edit': True}]}
        with self.assertRaisesRegex(g.GuardError, 'GUARD_RESTORE_CONFLICT'):
            g.deactivate(self.folder, self.expected, self.host)
        self.assertEqual(self.host.current, {'rules': [{'foreign-later-edit': True}]})
        self.assertNotIn('disarm', self.host.events)

    def test_uninstall_after_off_and_idempotent_off_do_not_ignore_new_rules(self):
        g.activate(self.plan, self.folder, self.host)
        g.deactivate(self.folder, self.expected, self.host)
        result = g.deactivate(self.folder, self.expected, self.host, uninstall=True)
        self.assertEqual(result['status'], 'uninstalled')
        self.assertFalse((self.folder / 'runtime.py').exists())
        self.host.current = {'rules': ['later-new-policy']}
        with self.assertRaisesRegex(g.GuardError, 'GUARD_RESTORED_BASELINE_DRIFT'):
            g.deactivate(self.folder, self.expected, self.host)

    def test_interface_drift_prevents_confirmation_but_not_scoped_recovery(self):
        self.host.coverage = lambda folder: {'physical_interfaces': ['fixture-nic']}
        g.activate(self.plan, self.folder, self.host)
        self.host.coverage = lambda folder: {'physical_interfaces': ['fixture-nic', 'new-nic']}
        with self.assertRaisesRegex(g.GuardError, 'GUARD_INTERFACE_DRIFT'):
            g.finish(self.folder, self.expected, self.host, self.verification(), True)
        self.assertNotIn('persist', self.host.events)
        g.deactivate(self.folder, self.expected, self.host)
        self.assertEqual(self.host.current, {'rules': None})

    def test_daily_off_on_retains_old_receipt_and_rearms(self):
        g.activate(self.plan, self.folder, self.host)
        g.deactivate(self.folder, self.expected, self.host)
        g.activate(self.plan, self.folder, self.host)
        self.assertEqual(self.host.events.count('arm'), 2)
        self.assertEqual(self.host.events.count('apply'), 2)
        histories = list(self.folder.glob('history-*'))
        self.assertEqual(len(histories), 1)
        self.assertEqual(g.read_json(histories[0] / 'state.json')['phase'], 'restored')

    def test_hostname_change_does_not_revoke_recovery_but_device_change_does(self):
        with patch.object(g.platform, 'node', return_value='before-name'):
            g.activate(self.plan, self.folder, self.host)
        with patch.object(g.platform, 'node', return_value='changed-by-network'):
            g.deactivate(self.folder, self.expected, self.host)
        g.activate(self.plan, self.folder, self.host)
        with patch.object(g, '_machine_identity', return_value=b'another-stable-device'):
            with self.assertRaisesRegex(g.GuardError, 'GUARD_STATE_BINDING'):
                g.deactivate(self.folder, self.expected, self.host)

    def test_confirm_and_expiry_worker_are_serialized(self):
        g.activate(self.plan, self.folder, self.host)
        entered, release = threading.Event(), threading.Event()
        errors = []
        original = self.host.persist
        def slow_persist(folder):
            entered.set()
            self.assertTrue(release.wait(3))
            original(folder)
        self.host.persist = slow_persist
        def confirm():
            try:
                g.finish(self.folder, self.expected, self.host, self.verification(), True)
            except Exception as e:
                errors.append(e)
        thread = threading.Thread(target=confirm)
        thread.start()
        self.assertTrue(entered.wait(2))
        seen = []
        def observer():
            with g.operation_lock(self.folder):
                seen.append(g._load_state(self.folder)['phase'])
        waiting = threading.Thread(target=observer)
        waiting.start()
        time.sleep(.05)
        self.assertEqual(seen, [])
        release.set()
        thread.join(3);waiting.join(3)
        self.assertFalse(thread.is_alive() or waiting.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(seen, ['confirmed'])

    def test_boot_rejects_retained_rule_edit_and_does_not_wash_readback(self):
        g.activate(self.plan, self.folder, self.host)
        g.finish(self.folder, self.expected, self.host, self.verification(), True)
        self.host.current = {'rules': None}
        g.private_write(self.folder / 'rules.nft.json', {'nftables': []})
        with patch.object(g, 'NativeHost', return_value=self.host):
            with self.assertRaisesRegex(g.GuardError, 'GUARD_RETAINED_RULES_CHANGED'):
                g._worker('_boot', self.folder)
        self.assertEqual(self.host.events.count('apply'), 1)
        # Restore the approved artifact, then simulate an unexpected native effect.
        g.private_write(self.folder / 'rules.nft.json', g.nft_document(self.plan['spec']))
        original_apply = self.host.apply
        def mismatch(folder):
            original_apply(folder)
            self.host.current = {'rules': ['unexpected']}
        self.host.apply = mismatch
        old = g._load_state(self.folder)['applied']
        with patch.object(g, 'NativeHost', return_value=self.host):
            with self.assertRaisesRegex(g.GuardError, 'GUARD_BOOT_READBACK_MISMATCH'):
                g._worker('_boot', self.folder)
        self.assertEqual(g._load_state(self.folder)['applied'], old)
        self.assertTrue(list(self.folder.glob('boot-*.intent.json')))


class GuardInputs(unittest.TestCase):
    def test_policy_and_parameter_injection_are_rejected_offline(self):
        for change, code in [({'policy': 'domestic-v4'}, 'GUARD_DOMESTIC_DYNAMIC_POLICY_UNSUPPORTED'),
                             ({'interfaces': ['eth0;reboot']}, 'GUARD_INVALID_INTERFACE'),
                             ({'scope': '../escape'}, 'GUARD_INVALID_IDENTIFIER')]:
            value = spec();value.update(change)
            with self.assertRaisesRegex(g.GuardError, code):
                g.make_plan(value)
        value = spec();value['nodes'][0]['ports'] = [True]
        with self.assertRaisesRegex(g.GuardError, 'GUARD_INVALID_PORT'):
            g.make_plan(value)

    def test_render_owns_only_its_scope_and_preserves_exact_exceptions(self):
        plan = g.make_plan(spec())
        text = plan['rules']
        self.assertIn('table inet clearpath_fixture', text)
        self.assertIn('192.0.2.0/24 tcp dport { 22 }', text)
        self.assertNotIn('flush ruleset', text)
        mac = g.make_plan(spec('macos'))['rules']
        self.assertIn('block drop out quick on { eth0 }', mac)
        self.assertNotIn('/etc/pf.conf', mac)

    def test_nft_readback_normalizes_handles_and_singletons_but_not_policy(self):
        source = g.nft_document(g.validate_input(spec()))
        listed = {'nftables': [{'metainfo': {'version': 'fixture'}}] +
                  [copy.deepcopy(x['add']) for x in source['nftables']]}
        for row in listed['nftables'][1:]:
            next(iter(row.values()))['handle'] = 100
        self.assertEqual(g.canonical_nft(source), g.canonical_nft(listed))
        listed['nftables'][2]['chain']['policy'] = 'accept'
        self.assertNotEqual(g.canonical_nft(source), g.canonical_nft(listed))

    def test_cli_mutation_requires_both_scope_and_independent_recovery(self):
        class C:
            SetupError = ValueError
        args = argparse.Namespace(command='guard-on', allow_system_change=True,
                                  control_channel_independent=False, recovery_ready=True)
        with patch.object(g, 'NativeHost') as native:
            with self.assertRaisesRegex(ValueError, 'GUARD_EXPLICIT_CHANGE_AND_INDEPENDENT_RECOVERY_REQUIRED'):
                g.run(C, args)
            native.assert_not_called()

    def test_systemd_literal_arguments_do_not_expand_environment_or_specifiers(self):
        value = '/opt/space here/$HOME/%i/"runtime".py'
        self.assertEqual(g._systemd_arg(value), '"/opt/space here/$$HOME/%%i/\\"runtime\\".py"')
        with self.assertRaisesRegex(g.GuardError, 'GUARD_UNIT_ARGUMENT'):
            g._systemd_arg('/root/python\nExecStart=/evil')

    def test_native_linux_recovery_is_ready_before_rule_command(self):
        commands, writes, ready = [], [], []
        def runner(argv, **kwargs):
            commands.append(list(argv))
            if argv[:2] == ['/usr/sbin/nft', '-j']:
                self.assertEqual(ready, [True])
                self.assertTrue(any(x[:3] == ['/usr/bin/systemctl', 'enable', '--now'] for x in commands))
            return subprocess.CompletedProcess(argv, 0, '', '')
        host = g.NativeHost(g.validate_input(spec()), runner=runner)
        with patch.object(g, '_new_system_file', side_effect=lambda p, text: writes.append((str(p), text))), \
                patch.object(host, '_record_artifacts'), \
                patch.object(host, '_await_recovery', side_effect=lambda folder: ready.append(True)):
            host.arm(Path('/synthetic/state'))
            host.apply(Path('/synthetic/state'))
        self.assertTrue(any('OnBootSec=5s' in text for _, text in writes))
        self.assertFalse(any('enable' in command and command[-1] == 'clearpath-guard-fixture.service' for command in commands))
        self.assertEqual(commands[-1], ['/usr/sbin/nft', '-j', '-f', '/synthetic/state/rules.nft.json'])

    def test_native_linux_failed_timer_admission_never_reaches_apply(self):
        commands = []
        def runner(argv, **kwargs):
            commands.append(list(argv))
            return subprocess.CompletedProcess(argv, 1 if 'is-active' in argv else 0, '', '')
        host = g.NativeHost(g.validate_input(spec()), runner=runner)
        with patch.object(g, '_new_system_file'), patch.object(host, '_record_artifacts'):
            with self.assertRaisesRegex(g.GuardError, 'GUARD_NATIVE_COMMAND_FAILED'):
                host.arm(Path('/synthetic/state'))
        self.assertFalse(any('/usr/sbin/nft' in argv for argv in commands))

    def test_native_startup_recovery_refuses_modified_owned_unit(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-guard-startup-') as temporary:
            folder = Path(temporary).resolve()
            units = folder / 'synthetic-systemd';units.mkdir()
            state = folder / 'state';state.mkdir(mode=0o700)
            native_name = '/etc/systemd/system/clearpath-guard-fixture.service'
            fixture = units / 'clearpath-guard-fixture.service'
            original = b'[Service]\nExecStart=/synthetic/approved\n'
            fixture.write_bytes(original)
            g.private_write(state / 'startup.files.json', {'schema': 'clearpath-guard-owned-files/1',
                'files': {native_name: g.digest(original)}}, True)
            commands = []
            def runner(argv, **kwargs):
                commands.append(argv)
                return subprocess.CompletedProcess(argv, 0, '', '')
            def paths(value):
                value = str(value)
                if value == '/etc/systemd/system':
                    return units
                if value.startswith('/etc/systemd/system/'):
                    return units / value.rsplit('/', 1)[-1]
                return Path(value)
            host = g.NativeHost(g.validate_input(spec()), runner=runner)
            fixture.write_bytes(b'[Service]\nExecStart=/synthetic/later-edit\n')
            with patch.object(g, 'Path', side_effect=paths):
                with self.assertRaisesRegex(g.GuardError, 'GUARD_STARTUP_LATER_EDIT_CONFLICT'):
                    host.unpersist(state)
            self.assertEqual(commands, [])
            self.assertIn(b'later-edit', fixture.read_bytes())
            fixture.write_bytes(original)
            with patch.object(g, 'Path', side_effect=paths):
                host.unpersist(state)
            self.assertFalse(fixture.exists())
            self.assertIn(['/usr/bin/systemctl', 'disable', 'clearpath-guard-fixture.service'], commands)

    def test_partial_linux_fuse_without_timer_removes_only_owned_service(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-partial-fuse-') as temporary:
            folder = Path(temporary).resolve()
            units = folder / 'units';units.mkdir()
            state = folder / 'state';state.mkdir(mode=0o700)
            service = units / 'clearpath-guard-fixture-fuse.service'
            raw = b'[Service]\nExecStart=/synthetic/recovery\n'
            service.write_bytes(raw)
            g.private_write(state / 'fuse.files.json', {'schema': 'clearpath-guard-owned-files/1', 'files': {
                '/etc/systemd/system/' + service.name: g.digest(raw),
                '/etc/systemd/system/clearpath-guard-fixture-fuse.timer': g.digest(b'not-created')}}, True)
            commands = []
            def runner(argv, **kwargs):
                commands.append(argv);return subprocess.CompletedProcess(argv, 0, '', '')
            def paths(value):
                value = str(value)
                if value == '/etc/systemd/system':return units
                if value.startswith('/etc/systemd/system/'):return units / value.rsplit('/', 1)[-1]
                return Path(value)
            host = g.NativeHost(g.validate_input(spec()), runner=runner)
            with patch.object(g, 'Path', side_effect=paths):
                host.disarm(state)
            self.assertFalse(service.exists())
            self.assertEqual(commands, [['/usr/bin/systemctl', 'daemon-reload']])

    def test_windows_security_audit_uses_pinned_source_not_state_backend(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-untrusted-win-state-') as temporary:
            folder = Path(temporary).resolve()
            (folder / 'backend.ps1').write_bytes(b'throw "UNTRUSTED_BACKEND"')
            commands = []
            def runner(argv, **kwargs):
                commands.append(argv);return subprocess.CompletedProcess(argv, 0, '', '')
            source = Path(g.__file__).with_name('system_guard_windows.ps1').read_bytes()
            host = g.NativeHost(g.validate_input(spec('windows')), runner=runner,
                                expected_backend_sha256=g.digest(source))
            with patch.object(g, 'windows_directory', return_value=Path('/synthetic/windows')):
                host._windows(folder, 'Audit', source=True)
                with self.assertRaisesRegex(g.GuardError, 'GUARD_WINDOWS_BACKEND_HASH_CHANGED'):
                    host._windows(folder, 'Secure')
            self.assertEqual(len(commands), 1)
            self.assertIn('-EncodedCommand', commands[0])
            body = base64.b64decode(commands[0][-1]).decode('utf-16le')
            self.assertIn(base64.b64encode(source).decode('ascii'), body)
            self.assertNotIn('UNTRUSTED_BACKEND', body)


if __name__ == '__main__':
    unittest.main()
