"""Isolated fake Linux host, files and downloader; never execute native commands."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import remote_setup as remote


class FakeHost(remote.NativeHost):
    def __init__(self, spec, sandbox):
        super().__init__(spec)
        self.sandbox = sandbox
        self.owner = os.getuid()
        self.commands = []
        self.services = {'ssh.service': {'active': 'active', 'enabled': 'enabled'}}
        self.nft = None
        self.tun = {'ifindex': None, 'routes': []}
        self.fail = None
        self.boot = 'fixture-boot'
        self.stable_machine = 'fixture-machine'
        self.fetcher = lambda unused: (_ for _ in ()).throw(AssertionError('network not mocked'))
        for name in ('/etc/systemd/system', '/etc/ssh/sshd_config.d', '/source'):
            self.path(name).mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path('/etc/ssh/sshd_config').write_text('Include /etc/ssh/sshd_config.d/*.conf\n')
        fragment = self.path('/usr/lib/systemd/system/ssh.service')
        fragment.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fragment.write_bytes(b'# fixture distro ssh.service\n')

    def path(self, value):
        p = Path(value)
        return p if p.is_relative_to(self.sandbox) else self.sandbox / 'filesystem' / str(p).lstrip('/')

    def root(self):
        return self.sandbox / 'state'

    def check(self, folder=None):
        remote.need(folder is None or Path(folder) == self.root(), 'REMOTE_FIXED_STATE_DIRECTORY_REQUIRED')

    def _trusted(self, path, missing=False, allowed_owner=None):
        p = Path(path)
        remote.need(p.is_relative_to(self.sandbox), 'FIXTURE_PATH_ESCAPED')
        while p != self.sandbox.parent:
            remote.need(not p.is_symlink(), 'REMOTE_NATIVE_PATH_UNTRUSTED')
            p = p.parent

    def boot_id(self):
        return self.boot

    def machine_id(self):
        return remote.digest(self.stable_machine.encode())

    def account_uid(self, name):
        return self.owner

    def customer_terminal_ready(self):
        return True  # API-only fixture, never exposed as a pretend-console CLI.

    def _service_state(self, name):
        if name in self.services:
            return copy.deepcopy(self.services[name])
        exists = self.path('/etc/systemd/system/' + name).is_file()
        return {'active': 'inactive', 'enabled': 'disabled' if exists else 'not-found'}

    def _inbound(self):
        return copy.deepcopy(self.nft)

    def _tun(self):
        return copy.deepcopy(self.tun) if 'core' in self.spec['modules'] else None

    def command(self, argv, data=None, allowed=(0,)):
        self.commands.append(list(argv))
        if self.fail and self.fail(argv):
            raise remote.RemoteError('SYNTHETIC_NATIVE_FAILURE')
        if '_handshake' in argv:
            state = remote.loads((self.root() / 'state.json').read_bytes())
            return json.dumps({'status': 'recovery_worker_ready', 'challenge': argv[-1],
                               'plan_sha256': state['plan_sha256'], 'worker_sha256': state['worker_sha256'], 'binding': state['binding']})
        if argv[0] == '/usr/bin/systemctl':
            action = argv[1]
            name = argv[-1]
            if action == 'show':
                key = next(x.split('=', 1)[1] for x in argv if x.startswith('--property='))
                return {'ExecStart': '{ path=/usr/sbin/sshd ; argv[]=/usr/sbin/sshd -D $SSHD_OPTS ; ignore_errors=no ; }',
                        'FragmentPath': '/usr/lib/systemd/system/ssh.service', 'EnvironmentFiles': '/etc/default/ssh (ignore_errors=yes)',
                        'Environment': 'SSHD_OPTS='}.get(key, '')
            if action == 'daemon-reload':
                for unit, state in self.services.items():
                    if unit != 'ssh.service' and not self.path('/etc/systemd/system/' + unit).exists():
                        state['enabled'] = 'not-found'
                return ''
            if action in ('is-active', 'is-enabled'):
                key = 'active' if action == 'is-active' else 'enabled'
                actual = self._service_state(name)[key]
                if '--quiet' in argv:
                    remote.need(actual == ('active' if key == 'active' else 'enabled'), 'SYNTHETIC_NATIVE_FAILURE')
                    return ''
                return actual
            state = self.services.setdefault(name, self._service_state(name))
            if action in ('start', 'restart'):
                state['active'] = 'active'
                if name == remote._service(self.spec, 'core'):
                    self.tun = {'ifindex': 81, 'routes': [{'dst': 'default', 'table': self.spec['core']['route_table']}]}
            elif action == 'stop':
                state['active'] = 'inactive'
                if name == remote._service(self.spec, 'core'):
                    self.tun = {'ifindex': None, 'routes': []}
            elif action == 'enable':
                state['enabled'] = 'enabled'
                if '--now' in argv:
                    state['active'] = 'active'
            elif action == 'disable':
                state['enabled'] = 'disabled' if self.path('/etc/systemd/system/' + name).exists() else 'not-found'
                if '--now' in argv:
                    state['active'] = 'inactive'
            return ''
        if argv[0] == '/usr/sbin/sshd':
            if '-T' in argv:
                item = self.spec['ssh']
                return 'port %d\npasswordauthentication %s\npermitrootlogin %s\nallowusers %s' % (
                    item['port'], 'yes' if item['password_authentication'] else 'no', item['permit_root_login'], ' '.join(item['allow_users']))
            return ''
        if argv[0] == '/usr/sbin/nft':
            if '-c' not in argv:
                document = remote.loads(data.encode())
                additions = []
                for row in document['nftables']:
                    if 'delete' in row:
                        remote.need(self.nft is not None, 'SYNTHETIC_DELETE_MISSING_TABLE')
                        self.nft = None
                    elif 'add' in row:
                        additions.append(row['add'])
                if additions:
                    self.nft = remote._canonical_nft({'nftables': additions})
            return ''
        if argv[0] == '/usr/sbin/ip':
            if 'flush' in argv:
                self.tun['routes'] = []
            elif 'delete' in argv:
                self.tun['ifindex'] = None
            return ''
        if argv[0] == remote._paths(self.spec)['binary'] and '-t' in argv:
            return ''
        raise AssertionError('unexpected fake command: ' + str(argv))


@unittest.skipUnless(os.name == 'posix', 'Self-contained Linux engine tested with POSIX temporary files')
class RemoteSetup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='clearpath-remote-fixture-')
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.input = {'schema': 'clearpath-remote-input/1', 'scope': 'fixture', 'platform': 'linux',
                      'distribution': 'debian', 'modules': ['ssh'], 'fuse_seconds': 180,
                      'ssh': {'port': 2222, 'password_authentication': False, 'permit_root_login': 'prohibit-password',
                              'allow_users': ['operator'], 'activation': 'restart'}}

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, value=None):
        plan = remote.make_plan(value or self.input)
        pin = remote.digest(remote.encoded(plan))
        folder = self.root / 'bundle'
        result = remote.export_bundle(plan, pin, folder)
        return folder, result['bundle_sha256'], plan, pin

    def activate(self, value=None):
        folder, pin, plan, plan_pin = self.bundle(value)
        host = FakeHost(plan['spec'], self.root / 'target')
        result = remote.activate(folder, pin, False, True, host)
        return host, result, plan_pin

    def verification(self, pin):
        return {'schema': 'clearpath-remote-verification/1', 'plan_sha256': pin,
                'normal_path': 'observed', 'management_path': 'observed', 'second_session': 'observed'}

    def core_input(self, https=False):
        binary = b'\x7fELFsynthetic fixture binary only'
        config = remote.encoded({'tun': {'enable': True, 'auto-route': True, 'device': 'cpfixture', 'iproute2-table-index': 30001}, 'ipv6': False})
        value = copy.deepcopy(self.input)
        value['modules'] = ['core', 'watchdog', 'inbound_guard']
        value.pop('ssh')
        source = {'kind': 'existing', 'path': '/source/mihomo', 'sha256': remote.digest(binary)}
        if https:
            raw = gzip.compress(binary)
            source = {'kind': 'https', 'url': 'https://example.invalid/mihomo.gz', 'sha256': remote.digest(raw),
                      'binary_sha256': remote.digest(binary), 'compression': 'gzip'}
        value['core'] = {'source': source, 'configuration_file': '/source/mihomo.json', 'configuration_sha256': remote.digest(config),
                         'tun_interface': 'cpfixture', 'route_table': 30001}
        value['watchdog'] = {'interval_seconds': 30}
        value['inbound_guard'] = {'management_networks': ['198.51.100.0/24'], 'tcp_ports': [22]}
        return value, binary, config

    def prepare_core_host(self, value, binary, config):
        folder, pin, plan, plan_pin = self.bundle(value)
        host = FakeHost(plan['spec'], self.root / 'target')
        host.path('/source/mihomo').write_bytes(binary)
        host.path('/source/mihomo.json').write_bytes(config)
        return folder, pin, host, plan_pin

    def test_export_is_offline_pinned_and_self_contained(self):
        with patch.object(remote.subprocess, 'run', side_effect=AssertionError('no process')):
            folder, pin, plan, plan_pin = self.bundle()
        self.assertEqual(set(x.name for x in folder.iterdir()), {'plan.private.json', 'remote_setup.py', 'bundle.json'})
        _, _, loaded, runtime = remote.read_bundle(folder, pin)
        self.assertEqual(loaded, plan)
        self.assertEqual(runtime, Path(remote.__file__).read_bytes())
        self.assertNotIn('import system_guard', runtime.decode())
        self.assertEqual(remote.digest((folder / 'plan.private.json').read_bytes()), plan_pin)

    def test_ssh_apply_arms_recovery_before_config_change_and_never_enables_runtime(self):
        host, result, pin = self.activate()
        self.assertEqual(result['status'], 'applied_pending_confirmation', result)
        self.assertEqual(result['exit_code'], 2)
        self.assertTrue(result['recovery_armed'])
        self.assertFalse(result['persistent'])
        commands = host.commands
        armed_at = next(i for i, x in enumerate(commands) if x[:3] == ['/usr/bin/systemctl', 'is-active', '--quiet'])
        reload_at = next(i for i, x in enumerate(commands) if x == ['/usr/bin/systemctl', 'restart', 'ssh.service'])
        self.assertLess(armed_at, reload_at)
        for x in commands:
            if len(x) > 1 and x[1] == 'enable':
                self.assertIn('recovery', x[-1])
        self.assertEqual(host.path(remote._paths(host.spec)['ssh']).read_text().splitlines()[0], 'Port 2222')
        self.assertTrue(any('Before=ssh.service' in p.read_text() for p in host.path('/etc/systemd/system').glob('*-boot.service')))

    def test_missing_second_session_fails_before_state_or_live_changes(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        with self.assertRaisesRegex(remote.RemoteError, 'SECOND_SESSION'):
            remote.activate(folder, pin, False, False, host)
        self.assertFalse(host.root().exists())
        self.assertEqual(host.commands, [])

    def test_bundle_or_plan_tampering_is_rejected(self):
        folder, pin, _, _ = self.bundle()
        with self.assertRaisesRegex(remote.RemoteError, 'BUNDLE_DIGEST'):
            remote.read_bundle(folder, '0' * 64)
        (folder / 'remote_setup.py').write_text('print("unreviewed")')
        with self.assertRaisesRegex(remote.RemoteError, 'BUNDLE_FILE_CHANGED'):
            remote.read_bundle(folder, pin)

    def test_unsupported_scope_path_module_or_hidden_parameter_rejected(self):
        for changed in [dict(self.input, scope='../escape'), dict(self.input, modules=['unknown']),
                        dict(self.input, trusted_python='/tmp/../python'), dict(self.input, reverse_tunnel={})]:
            with self.assertRaises(remote.RemoteError):
                remote.make_plan(changed)

    def test_unreviewed_existing_owned_file_is_not_replaced(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        target = host.path(remote._paths(host.spec)['ssh'])
        target.write_text('# existing owner configuration\n')
        with self.assertRaisesRegex(remote.RemoteError, 'EXACT_BASELINE'):
            remote.activate(folder, pin, False, True, host)
        self.assertEqual(target.read_text(), '# existing owner configuration\n')
        self.assertFalse(host.root().exists())

    def test_arm_failure_prevents_any_live_file_write(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        host.fail = lambda argv: argv[:3] == ['/usr/bin/systemctl', 'is-active', '--quiet']
        result = remote.activate(folder, pin, False, True, host)
        self.assertEqual(result['status'], 'partial_or_unconfirmed')
        self.assertFalse(result['recovery_armed'])
        self.assertFalse(host.path(remote._paths(host.spec)['ssh']).exists())
        self.assertTrue((host.root() / 'state.json').is_file())

    def test_error_after_config_write_keeps_private_recovery_and_can_restore(self):
        folder, pin, plan, plan_pin = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        host.fail = lambda argv: argv == ['/usr/bin/systemctl', 'restart', 'ssh.service']
        result = remote.activate(folder, pin, False, True, host)
        self.assertEqual(result['exit_code'], 2)
        self.assertTrue(host.path(remote._paths(host.spec)['ssh']).is_file())
        self.assertEqual(remote.loads((host.root() / 'state.json').read_bytes())['phase'], 'apply_uncertain')
        host.fail = None
        restored = remote.restore(host.root(), plan_pin, host)
        self.assertTrue(restored['startup_restored'])
        self.assertFalse(host.path(remote._paths(host.spec)['ssh']).exists())

    def test_confirmation_requires_observed_paths_and_unchanged_files(self):
        host, _, pin = self.activate()
        with self.assertRaisesRegex(remote.RemoteError, 'VERIFICATION'):
            remote.confirm(host.root(), pin, {}, True, host)
        target = host.path(remote._paths(host.spec)['ssh'])
        target.write_text(target.read_text() + '# later owner edit\n')
        with self.assertRaisesRegex(remote.RemoteError, 'CONFIGURATION_DRIFT'):
            remote.confirm(host.root(), pin, self.verification(pin), True, host)
        with self.assertRaisesRegex(remote.RemoteError, 'RESTORE_FILE_CONFLICT'):
            remote.restore(host.root(), pin, host)
        self.assertIn('later owner edit', target.read_text())

    def test_successful_confirm_disarms_both_timer_and_boot_recovery(self):
        host, _, pin = self.activate()
        result = remote.confirm(host.root(), pin, self.verification(pin), True, host)
        self.assertEqual(result['status'], 'configuration_confirmed')
        self.assertFalse(result['network_verified'])
        self.assertFalse(list(host.path('/etc/systemd/system').glob('*-recovery*')))
        self.assertEqual(remote.status(host.root(), host)['exit_code'], 0)

    def test_existing_file_backup_and_rollback_preserve_content_and_mode(self):
        value = copy.deepcopy(self.input)
        logical = '/etc/ssh/sshd_config.d/90-clearpath-fixture.conf'
        original = b'# owned baseline\n'
        value['expected_files'] = {logical: remote.digest(original)}
        folder, pin, plan, plan_pin = self.bundle(value)
        host = FakeHost(plan['spec'], self.root / 'target')
        target = host.path(logical)
        target.write_bytes(original)
        target.chmod(0o640)
        result = remote.activate(folder, pin, False, True, host)
        self.assertEqual(result['status'], 'applied_pending_confirmation')
        restored = remote.restore(host.root(), plan_pin, host)
        self.assertEqual(restored['status'], 'restored')
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(remote.status(host.root(), host)['exit_code'], 0)

    def test_preconfirm_boot_rollback_does_not_reload_or_start_queued_services(self):
        host, _, pin = self.activate()
        host.boot = 'different-boot'
        host.commands.clear()
        restored = remote.restore(host.root(), pin, host)
        self.assertTrue(restored['post_boot_runtime_recheck'])
        self.assertFalse(restored['runtime_restored'])
        self.assertFalse(any(x[1] in ('start', 'restart', 'reload', 'kill') for x in host.commands))
        self.assertFalse(host.path(remote._paths(host.spec)['ssh']).exists())

    def test_core_hash_and_config_validation_happen_before_recovery_arm(self):
        value, binary, config = self.core_input()
        folder, pin, host, _ = self.prepare_core_host(value, binary + b'changed', config)
        with self.assertRaisesRegex(remote.RemoteError, 'CORE_HASH'):
            remote.activate(folder, pin, True, True, host)
        self.assertFalse(host.root().exists())
        self.assertFalse(host.commands)

    def test_core_and_watchdog_trial_does_not_enable_new_persistence(self):
        value, binary, config = self.core_input()
        folder, pin, host, plan_pin = self.prepare_core_host(value, binary, config)
        result = remote.activate(folder, pin, True, True, host)
        self.assertEqual(result['status'], 'applied_pending_confirmation', result)
        self.assertTrue(host.path(remote._paths(host.spec)['binary']).is_file())
        self.assertEqual(host.path(remote._paths(host.spec)['config']).stat().st_mode & 0o777, 0o600)
        self.assertTrue(all('recovery' in x[-1] for x in host.commands if len(x) > 1 and x[1] == 'enable'))
        confirmed = remote.confirm(host.root(), plan_pin, self.verification(plan_pin), True, host)
        self.assertTrue(confirmed['persistent'])
        self.assertTrue(any(x[1] == 'enable' and x[-1] == remote._service(host.spec, 'core') for x in host.commands))

    def test_pinned_download_and_gzip_binary_are_verified_without_real_network(self):
        value, binary, config = self.core_input(https=True)
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        host.fetcher = lambda unused: gzip.compress(binary)
        result = remote.activate(folder, pin, True, True, host)
        self.assertEqual(result['status'], 'applied_pending_confirmation', result)
        self.assertEqual(host.path(remote._paths(host.spec)['binary']).read_bytes(), binary)

    def test_failed_core_watchdog_only_touches_its_planned_table_and_interface(self):
        value, binary, config = self.core_input()
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        remote.activate(folder, pin, True, True, host)
        core = remote._service(host.spec, 'core')
        host.services[core]['active'] = 'failed'
        command = host.command
        def leaves_old_tun(argv, *args, **kwargs):
            before = copy.deepcopy(host.tun)
            result = command(argv, *args, **kwargs)
            if argv[:2] == ['/usr/bin/systemctl', 'stop'] and argv[-1] == core:
                host.tun = before
            return result
        host.command = leaves_old_tun
        host.commands.clear()
        result = remote.watchdog(host.root(), host)
        self.assertEqual(result['status'], 'owned_core_restarted')
        self.assertIn(['/usr/sbin/ip', 'route', 'flush', 'table', '30001'], host.commands)
        self.assertIn(['/usr/sbin/ip', 'link', 'delete', 'dev', 'cpfixture'], host.commands)
        self.assertFalse(any('pkill' in x or 'main' in x for argv in host.commands for x in argv))

    def test_watchdog_does_not_undo_changed_route_ownership(self):
        value, binary, config = self.core_input()
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        remote.activate(folder, pin, True, True, host)
        host.services[remote._service(host.spec, 'core')]['active'] = 'failed'
        host.tun['ifindex'] = 999
        host.commands.clear()
        with self.assertRaisesRegex(remote.RemoteError, 'OWNERSHIP_CHANGED'):
            remote.watchdog(host.root(), host)
        self.assertFalse(host.commands)

    def test_inbound_is_not_an_outbound_kill_switch(self):
        value, _, _ = self.core_input()
        plan = remote.make_plan(value)
        raw = remote.encoded(remote.inbound_document(plan['spec'])).decode()
        self.assertIn('"hook": "input"', raw)
        self.assertNotIn('"hook": "output"', raw)

    def test_reverse_tunnel_has_no_implicit_proxy_agent_or_non_loopback_bind(self):
        value = copy.deepcopy(self.input)
        value['modules'] = ['reverse_tunnel']
        value.pop('ssh')
        value['reverse_tunnel'] = {'user': 'operator', 'remote_user': 'relay', 'host': 'relay.example.invalid', 'port': 22,
                                   'remote_bind_port': 22022, 'local_port': 22, 'identity_file': '/home/operator/.ssh/key',
                                   'known_hosts': '/home/operator/.ssh/known_hosts'}
        plan = remote.make_plan(value)
        raw = next(x['text'] for x in plan['files'].values())
        for required in ('"-F" "/dev/null"', 'IdentitiesOnly=yes', 'IdentityAgent=none', 'ProxyCommand=none',
                         'StrictHostKeyChecking=yes', 'GlobalKnownHostsFile=/dev/null', 'ControlMaster=no',
                         '127.0.0.1:22022:127.0.0.1:22', 'UnsetEnvironment=SSH_AUTH_SOCK SSH_AGENT_PID'):
            self.assertIn(required, raw)
        self.assertNotIn('0.0.0.0:', raw)

    def test_portable_bundle_runs_its_own_offline_planner_under_isolated_python(self):
        folder, _, _, _ = self.bundle()
        request = self.root / 'request.json'
        output = self.root / 'independent-plan.json'
        request.write_bytes(remote.encoded(self.input))
        result = subprocess.run([sys.executable, '-I', str(folder / 'remote_setup.py'), 'remote-plan', '--input', str(request), '--output', str(output)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['network_requests'], 0)
        self.assertTrue(output.is_file())

    def test_match_requires_context_before_writing_and_supplied_context_is_used(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        main = host.path('/etc/ssh/sshd_config')
        main.write_text(main.read_text() + 'Match User operator\n PasswordAuthentication yes\n')
        with self.assertRaisesRegex(remote.RemoteError, 'MATCH_CONTEXTS_REQUIRED'):
            remote.activate(folder, pin, False, True, host)
        self.assertFalse(host.root().exists())
        value = copy.deepcopy(self.input)
        value['ssh']['validation_contexts'] = [{'user': 'operator', 'host': 'client.example.invalid',
            'address': '198.51.100.2', 'local_address': '203.0.113.2', 'local_port': 2222}]
        contextual = remote.make_plan(value)
        other_bundle = self.root / 'context-bundle'
        exported = remote.export_bundle(contextual, remote.digest(remote.encoded(contextual)), other_bundle)
        host.spec = contextual['spec']
        result = remote.activate(other_bundle, exported['bundle_sha256'], False, True, host)
        self.assertEqual(result['status'], 'applied_pending_confirmation', result)
        self.assertTrue(any('-C' in argv and 'user=operator' in argv[-1] for argv in host.commands))

    def test_both_old_and_new_ports_are_not_misreported_as_single_replacement(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        original = host.command
        def multiple_ports(argv, *args, **kwargs):
            answer = original(argv, *args, **kwargs)
            return 'port 22\n' + answer if argv[:2] == ['/usr/sbin/sshd', '-T'] else answer
        host.command = multiple_ports
        result = remote.activate(folder, pin, False, True, host)
        self.assertEqual(result['reason_code'], 'REMOTE_SSH_EFFECTIVE_CONFIGURATION_MISMATCH')
        state = remote.loads((host.root() / 'state.json').read_bytes())
        self.assertEqual(state['ssh_readback'][0]['ports'], ['22', '2222'])
        self.assertFalse(any(argv[:2] == ['/usr/bin/systemctl', 'kill'] for argv in host.commands))

    def test_socket_activation_is_explicitly_unsupported_without_port_adoption_proof(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        host.services['ssh.socket'] = {'active': 'active', 'enabled': 'enabled'}
        with self.assertRaisesRegex(remote.RemoteError, 'SOCKET_ACTIVATION_UNSUPPORTED'):
            remote.activate(folder, pin, False, True, host)
        self.assertFalse(host.root().exists())

    def test_shared_persistent_ssh_change_requires_explicit_persistence_confirmation(self):
        host, _, pin = self.activate()
        with self.assertRaisesRegex(remote.RemoteError, 'REQUIRES_PERSIST_CONFIRMATION'):
            remote.confirm(host.root(), pin, self.verification(pin), False, host)
        self.assertTrue(remote.loads((host.root() / 'state.json').read_bytes())['recovery_armed'])

    def test_corrupt_old_backup_blocks_restoration_before_any_live_change(self):
        value = copy.deepcopy(self.input)
        logical = '/etc/ssh/sshd_config.d/90-clearpath-fixture.conf'
        value['expected_files'] = {logical: remote.digest(b'# old\n')}
        folder, pin, plan, plan_pin = self.bundle(value)
        host = FakeHost(plan['spec'], self.root / 'target')
        host.path(logical).write_bytes(b'# old\n')
        remote.activate(folder, pin, False, True, host)
        (host.root() / 'before/0').write_bytes(b'corrupt')
        host.commands.clear()
        with self.assertRaisesRegex(remote.RemoteError, 'BACKUP_CORRUPT'):
            remote.restore(host.root(), plan_pin, host)
        self.assertFalse(any(argv[1] in ('start', 'restart', 'stop', 'enable', 'disable', 'kill') for argv in host.commands))
        self.assertIn('Port 2222', host.path(logical).read_text())

    def test_restore_replacement_then_lost_response_can_resume_without_overwrite(self):
        value = copy.deepcopy(self.input)
        logical = '/etc/ssh/sshd_config.d/90-clearpath-fixture.conf'
        original_bytes = b'# old baseline\n'
        value['expected_files'] = {logical: remote.digest(original_bytes)}
        folder, pin, plan, plan_pin = self.bundle(value)
        host = FakeHost(plan['spec'], self.root / 'target')
        host.path(logical).write_bytes(original_bytes)
        remote.activate(folder, pin, False, True, host)
        replace = os.replace
        def lost_response(a, b):
            replace(a, b)
            if '.restore-' in Path(a).name:
                raise OSError('synthetic response lost after restore')
        with patch.object(remote.os, 'replace', side_effect=lost_response):
            with self.assertRaises(OSError):
                remote.restore(host.root(), plan_pin, host)
        self.assertEqual(host.path(logical).read_bytes(), original_bytes)
        result = remote.restore(host.root(), plan_pin, host)
        self.assertEqual(result['status'], 'restored')

    def test_nft_wrote_then_response_failed_is_bound_to_pending_exact_rules(self):
        value, binary, config = self.core_input()
        folder, pin, host, plan_pin = self.prepare_core_host(value, binary, config)
        command = host.command
        failed = [False]
        def lost_response(argv, *args, **kwargs):
            result = command(argv, *args, **kwargs)
            if argv[:2] == ['/usr/sbin/nft', '-j'] and '-c' not in argv and not failed[0]:
                failed[0] = True
                raise remote.RemoteError('SYNTHETIC_NFT_RESPONSE_LOST')
            return result
        host.command = lost_response
        result = remote.activate(folder, pin, True, True, host)
        self.assertEqual(result['status'], 'partial_or_unconfirmed')
        self.assertIsNotNone(host.nft)
        host.command = command
        restored = remote.restore(host.root(), plan_pin, host)
        self.assertEqual(restored['status'], 'restored', restored)
        self.assertIsNone(host.nft)

    def test_failed_persistence_keeps_fuse_and_restores_enabled_and_runtime_separately(self):
        value, binary, config = self.core_input()
        folder, pin, host, plan_pin = self.prepare_core_host(value, binary, config)
        remote.activate(folder, pin, True, True, host)
        host.fail = lambda argv: len(argv) > 2 and argv[1] == 'enable' and argv[-1] == remote._service(host.spec, 'inbound_guard')
        with self.assertRaises(remote.RemoteError):
            remote.confirm(host.root(), plan_pin, self.verification(plan_pin), True, host)
        state = remote.loads((host.root() / 'state.json').read_bytes())
        self.assertTrue(state['startup_pending'])
        self.assertTrue(state['recovery_armed'])
        host.fail = None
        result = remote.restore(host.root(), plan_pin, host)
        self.assertTrue(result['runtime_restored'])
        self.assertTrue(result['startup_restored'])

    def test_changed_startup_or_shared_main_ssh_configuration_is_preserved(self):
        host, _, pin = self.activate()
        main = host.path('/etc/ssh/sshd_config')
        main.write_text(main.read_text() + '# later administrator change\n')
        host.commands.clear()
        with self.assertRaisesRegex(remote.RemoteError, 'SHARED_SSH_CONFIG_CHANGED'):
            remote.restore(host.root(), pin, host)
        self.assertFalse(host.commands)
        self.assertIn('later administrator', main.read_text())

    def test_systemd_arguments_escape_percent_dollar_quotes_and_no_shell(self):
        rendered = remote._unit_arg('/home/operator/key$X%Y"Z')
        self.assertEqual(rendered, '"/home/operator/key$$X%%Y\\"Z"')

    def test_network_denial_precedes_download_and_real_target_mutations(self):
        value, binary, config = self.core_input(https=True)
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        host.fetcher = lambda unused: (_ for _ in ()).throw(AssertionError('must not download'))
        with self.assertRaisesRegex(remote.RemoteError, 'NETWORK_PERMISSION'):
            remote.activate(folder, pin, False, True, host)
        self.assertFalse(host.root().exists())

    def test_old_inbound_table_missing_after_boot_is_added_without_delete_missing(self):
        value, _, _ = self.core_input()
        value['modules'] = ['inbound_guard']
        value.pop('core')
        value.pop('watchdog')
        old = {'nftables': [{'table': {'family': 'inet', 'name': 'clearpath_remote_fixture'}},
                           {'chain': {'family': 'inet', 'table': 'clearpath_remote_fixture', 'name': 'input',
                                      'type': 'filter', 'hook': 'input', 'prio': 10, 'policy': 'accept'}}]}
        value['expected_inbound_sha256'] = remote.digest(old)
        folder, pin, plan, plan_pin = self.bundle(value)
        host = FakeHost(plan['spec'], self.root / 'target')
        host.nft = copy.deepcopy(old)
        result = remote.activate(folder, pin, False, True, host)
        self.assertEqual(result['status'], 'applied_pending_confirmation')
        host.boot = 'new-boot'
        host.nft = None
        result = remote.restore(host.root(), plan_pin, host)
        self.assertEqual(result['status'], 'restored')
        self.assertEqual(host.nft, old)

    def test_boot_recovery_checks_enabled_state_even_when_runtime_is_deferred(self):
        value, binary, config = self.core_input()
        unit = '/etc/systemd/system/clearpath-remote-fixture-core.service'
        old_unit = b'# original owned unit\n'
        value['expected_files'] = {unit: remote.digest(old_unit)}
        value['expected_services'] = {'clearpath-remote-fixture-core.service': {'active': 'inactive', 'enabled': 'disabled'}}
        folder, pin, host, plan_pin = self.prepare_core_host(value, binary, config)
        host.path(unit).write_bytes(old_unit)
        remote.activate(folder, pin, True, True, host)
        host.fail = lambda argv: len(argv) > 2 and argv[1] == 'enable' and argv[-1] == remote._service(host.spec, 'inbound_guard')
        with self.assertRaises(remote.RemoteError):
            remote.confirm(host.root(), plan_pin, self.verification(plan_pin), True, host)
        host.fail = None
        host.boot = 'new-boot'
        host.tun = {'ifindex': None, 'routes': []}
        host.services[remote._service(host.spec, 'core')]['active'] = 'inactive'
        command = host.command
        def ignored_disable(argv, *args, **kwargs):
            if len(argv) > 2 and argv[1] == 'disable' and argv[-1] == remote._service(host.spec, 'core'):
                host.commands.append(list(argv))
                return ''
            return command(argv, *args, **kwargs)
        host.command = ignored_disable
        with self.assertRaisesRegex(remote.RemoteError, 'STARTUP_READBACK_FAILED'):
            remote.restore(host.root(), plan_pin, host)
        self.assertNotEqual(remote.loads((host.root() / 'state.json').read_bytes())['phase'], 'restored')

    def test_hostname_change_does_not_invalidate_exact_recovery(self):
        host, _, pin = self.activate()
        with patch.object(remote.platform, 'node', return_value='a-new-hostname'):
            result = remote.restore(host.root(), pin, host)
        self.assertEqual(result['status'], 'restored')

    def test_different_stable_machine_id_refuses_recovery_before_any_change(self):
        host, _, pin = self.activate()
        host.stable_machine = 'different-machine'
        host.commands.clear()
        with self.assertRaisesRegex(remote.RemoteError, 'STATE_BINDING_CHANGED'):
            remote.restore(host.root(), pin, host)
        self.assertFalse(host.commands)

    def test_failed_independent_worker_handshake_never_reaches_live_mutation(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        command = host.command
        def bad_handshake(argv, *args, **kwargs):
            return '{}' if '_handshake' in argv else command(argv, *args, **kwargs)
        host.command = bad_handshake
        result = remote.activate(folder, pin, False, True, host)
        self.assertEqual(result['reason_code'], 'REMOTE_INDEPENDENT_WORKER_HANDSHAKE_FAILED')
        self.assertFalse(host.path(remote._paths(host.spec)['ssh']).exists())
        self.assertFalse(list(host.path('/etc/systemd/system').glob('*-recovery*')))

    def test_abandoned_fixed_and_unique_state_stages_do_not_block_recovery(self):
        host, _, pin = self.activate()
        old = host.root() / 'state.json.next'
        orphan = host.root() / 'state.json.next-orphan'
        old.write_bytes(b'old interrupted staging artifact')
        orphan.write_bytes(b'another interrupted staging artifact')
        result = remote.restore(host.root(), pin, host)
        self.assertEqual(result['status'], 'restored')
        self.assertEqual(old.read_bytes(), b'old interrupted staging artifact')
        self.assertEqual(orphan.read_bytes(), b'another interrupted staging artifact')

    def test_persistence_callback_cannot_launder_a_later_file_edit_into_applied(self):
        host, _, pin = self.activate()
        before = remote.loads((host.root() / 'state.json').read_bytes())['applied']
        original = host.persist
        target = host.path(remote._paths(host.spec)['ssh'])
        def changed_during_persist(state):
            original(state)
            target.write_text(target.read_text() + '# post-approval edit\n')
        host.persist = changed_during_persist
        with self.assertRaisesRegex(remote.RemoteError, 'CHANGED_DURING_PERSISTENCE'):
            remote.confirm(host.root(), pin, self.verification(pin), True, host)
        saved = remote.loads((host.root() / 'state.json').read_bytes())
        self.assertEqual(saved['applied'], before)
        self.assertEqual(saved['phase'], 'confirming')
        self.assertTrue(saved['recovery_armed'])
        with self.assertRaisesRegex(remote.RemoteError, 'RESTORE_FILE_CONFLICT'):
            remote.restore(host.root(), pin, host)
        self.assertIn('post-approval edit', target.read_text())

    def test_multiple_existing_backups_keep_stable_file_order_after_json_roundtrip(self):
        value, binary, config = self.core_input()
        original = {'/etc/systemd/system/clearpath-remote-fixture-core.service': b'# old core unit\n',
                    '/usr/local/lib/clearpath/fixture/mihomo': b'\x7fELFold binary fixture',
                    '/etc/clearpath/fixture/mihomo.json': b'{"old":"config"}\n'}
        value['expected_files'] = {path: remote.digest(raw) for path, raw in original.items()}
        value['expected_services'] = {'clearpath-remote-fixture-core.service': {'active': 'inactive', 'enabled': 'disabled'}}
        folder, pin, host, plan_pin = self.prepare_core_host(value, binary, config)
        for path, raw in original.items():
            target = host.path(path)
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            target.write_bytes(raw)
        result = remote.activate(folder, pin, True, True, host)
        self.assertEqual(result['status'], 'applied_pending_confirmation', result)
        result = remote.restore(host.root(), plan_pin, host)
        self.assertEqual(result['status'], 'restored')
        for path, raw in original.items():
            self.assertEqual(host.path(path).read_bytes(), raw)

    def test_clean_core_crash_restarts_without_deleting_any_route_or_interface(self):
        value, binary, config = self.core_input()
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        remote.activate(folder, pin, True, True, host)
        core = remote._service(host.spec, 'core')
        host.services[core]['active'] = 'failed'
        host.tun = {'ifindex': None, 'routes': []}
        host.commands.clear()
        result = remote.watchdog(host.root(), host)
        self.assertEqual(result['status'], 'owned_core_restarted')
        self.assertIn(['/usr/bin/systemctl', 'stop', core], host.commands)
        self.assertIn(['/usr/bin/systemctl', 'restart', core], host.commands)
        self.assertFalse(any(argv[0] == '/usr/sbin/ip' for argv in host.commands))

    def test_watchdog_never_launders_a_restart_callback_file_change(self):
        value, binary, config = self.core_input()
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        remote.activate(folder, pin, True, True, host)
        state_before = remote.loads((host.root() / 'state.json').read_bytes())['applied']
        core = remote._service(host.spec, 'core')
        host.services[core]['active'] = 'failed'
        command = host.command
        config_file = host.path(remote._paths(host.spec)['config'])
        def changed_after_restart(argv, *args, **kwargs):
            result = command(argv, *args, **kwargs)
            if argv[:2] == ['/usr/bin/systemctl', 'restart'] and argv[-1] == core:
                config_file.write_bytes(config_file.read_bytes() + b'\n')
            return result
        host.command = changed_after_restart
        with self.assertRaisesRegex(remote.RemoteError, 'POST_RESTART_CONFIGURATION_DRIFT'):
            remote.watchdog(host.root(), host)
        after = remote.loads((host.root() / 'state.json').read_bytes())
        self.assertEqual(after['applied'], state_before)
        self.assertTrue((host.root() / 'watchdog-intent.json').exists())
        self.assertTrue(config_file.read_bytes().endswith(b'\n\n'))

    def test_watchdog_stops_auto_restart_then_refuses_a_new_interface_generation(self):
        value, binary, config = self.core_input()
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        remote.activate(folder, pin, True, True, host)
        core = remote._service(host.spec, 'core')
        host.services[core]['active'] = 'failed'
        command = host.command
        def new_generation_after_stop(argv, *args, **kwargs):
            result = command(argv, *args, **kwargs)
            if argv[:2] == ['/usr/bin/systemctl', 'stop'] and argv[-1] == core:
                host.tun = {'ifindex': 999, 'routes': [{'owner': 'new generation'}]}
            return result
        host.command = new_generation_after_stop
        host.commands.clear()
        with self.assertRaisesRegex(remote.RemoteError, 'FRESH_ROUTE_OWNERSHIP_CHANGED'):
            remote.watchdog(host.root(), host)
        self.assertIn(['/usr/bin/systemctl', 'stop', core], host.commands)
        self.assertFalse(any(argv[0] == '/usr/sbin/ip' or argv[1] == 'restart' for argv in host.commands))

    def test_watchdog_does_not_capture_its_oneshot_activation_as_new_baseline(self):
        value, binary, config = self.core_input()
        folder, pin, host, _ = self.prepare_core_host(value, binary, config)
        remote.activate(folder, pin, True, True, host)
        core, worker = remote._service(host.spec, 'core'), remote._service(host.spec, 'watchdog')
        host.services[core]['active'] = 'failed'
        host.services[worker] = {'active': 'activating', 'enabled': 'disabled'}
        result = remote.watchdog(host.root(), host)
        self.assertEqual(result['status'], 'owned_core_restarted')
        saved = remote.loads((host.root() / 'state.json').read_bytes())
        self.assertEqual(saved['applied']['services'][worker]['active'], 'inactive')

    def test_queued_expiry_worker_rechecks_confirmation_under_restore_lock(self):
        host, _, pin = self.activate()
        original_restore = remote.restore
        def confirmation_wins(folder, expected, current_host, pending_only=False):
            remote.confirm(folder, expected, self.verification(expected), True, current_host)
            return original_restore(folder, expected, current_host, pending_only=pending_only)
        with patch.object(remote, '_host_from_state', return_value=host), \
                patch.object(remote, 'restore', side_effect=confirmation_wins):
            result = remote._worker('_expire', str(host.root()))
        self.assertEqual(result['status'], 'not_due')
        self.assertIn('Port 2222', host.path(remote._paths(host.spec)['ssh']).read_text())

    def test_dhcp_reply_is_exact_ipv4_udp_server_to_client_ports(self):
        value, _, _ = self.core_input()
        rules = remote.inbound_document(remote.make_plan(value)['spec'])['nftables']
        dhcp = [x['add']['rule']['expr'] for x in rules if 'rule' in x.get('add', {}) and
                any(row.get('match', {}).get('right') == 67 for row in x['add']['rule']['expr'])]
        self.assertEqual(len(dhcp), 1)
        self.assertIn({'match': {'op': '==', 'left': {'payload': {'protocol': 'udp', 'field': 'dport'}}, 'right': 68}}, dhcp[0])
        self.assertIn({'match': {'op': '==', 'left': {'meta': {'key': 'nfproto'}}, 'right': 'ipv4'}}, dhcp[0])

    def test_enabled_but_inactive_ssh_socket_is_also_rejected(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        host.services['ssh.socket'] = {'active': 'inactive', 'enabled': 'enabled'}
        with self.assertRaisesRegex(remote.RemoteError, 'SOCKET_ACTIVATION_UNSUPPORTED'):
            remote.activate(folder, pin, False, True, host)
        self.assertFalse(host.root().exists())

    def test_nonstandard_service_execstart_or_nonempty_options_are_not_default_config_proof(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        command = host.command
        def custom_config(argv, *args, **kwargs):
            if '--property=ExecStart' in argv:
                return '{ path=/usr/sbin/sshd ; argv[]=/usr/sbin/sshd -D -f /private/custom.conf ; ignore_errors=no ; }'
            return command(argv, *args, **kwargs)
        host.command = custom_config
        with self.assertRaisesRegex(remote.RemoteError, 'NONSTANDARD_SSH_EXECSTART'):
            remote.activate(folder, pin, False, True, host)
        self.assertFalse(host.root().exists())
        host.command = command
        defaults = host.path('/etc/default/ssh')
        defaults.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        defaults.write_text('SSHD_OPTS="-f /private/custom.conf"\n')
        with self.assertRaisesRegex(remote.RemoteError, 'NONEMPTY_OPTIONS'):
            remote.activate(folder, pin, False, True, host)
        self.assertFalse(host.root().exists())

    def test_partial_arm_missing_units_can_be_removed_without_disabling_uncreated_names(self):
        folder, pin, plan, plan_pin = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        original = remote._write_new
        wrote = [0]
        def interrupted_arm(path, data, mode=0o600):
            if 'recovery' in str(path) and str(path).endswith(('.timer', '-boot.service')):
                raise OSError('synthetic partial arm interruption')
            original(path, data, mode)
            if 'recovery' in str(path):
                wrote[0] += 1
        with patch.object(remote, '_write_new', side_effect=interrupted_arm):
            result = remote.activate(folder, pin, False, True, host)
        self.assertEqual(result['status'], 'partial_or_unconfirmed')
        self.assertEqual(wrote[0], 1)
        saved = remote.loads((host.root() / 'state.json').read_bytes())
        self.assertEqual(len(saved['fuse_files']), 3)
        host.commands.clear()
        restored = remote.restore(host.root(), plan_pin, host)
        self.assertEqual(restored['status'], 'restored')
        self.assertFalse(any(argv[1] == 'disable' and 'recovery' in argv[-1] for argv in host.commands))
        self.assertFalse(list(host.path('/etc/systemd/system').glob('*-recovery*')))

    def test_ssh_restart_is_explicit_and_resets_to_reviewed_unit_not_old_daemon_argv(self):
        missing_activation = copy.deepcopy(self.input)
        missing_activation['ssh'].pop('activation')
        with self.assertRaisesRegex(remote.RemoteError, 'EXPLICIT_SSH_RESTART'):
            remote.make_plan(missing_activation)
        folder, pin, plan, plan_pin = self.bundle()
        self.assertTrue(plan['requires_customer_terminal'])
        self.assertEqual(plan['ssh_adoption'], 'restart_current_reviewed_unit_and_defaults')
        host = FakeHost(plan['spec'], self.root / 'target')
        host.old_daemon_arguments = ['-D', '-f', '/private/previous-not-in-current-unit.conf']
        command = host.command
        def unit_restart(argv, *args, **kwargs):
            result = command(argv, *args, **kwargs)
            if argv == ['/usr/bin/systemctl', 'restart', 'ssh.service']:
                host.old_daemon_arguments = ['-D']
            return result
        host.command = unit_restart
        applied = remote.activate(folder, pin, False, True, host)
        self.assertEqual(applied['status'], 'applied_pending_confirmation')
        self.assertFalse(applied['old_unpersisted_sshd_arguments_retained'])
        self.assertEqual(host.old_daemon_arguments, ['-D'])
        self.assertFalse(any(argv[:2] == ['/usr/bin/systemctl', 'kill'] for argv in host.commands))
        result = remote.restore(host.root(), plan_pin, host)
        self.assertFalse(result['runtime_restored'])
        self.assertFalse(result['old_unpersisted_sshd_arguments_restored'])
        self.assertTrue(result['saved_files_restored'])
        self.assertTrue(result['service_states_restored'])

    def test_ssh_initial_deployment_requires_customer_terminal_before_live_changes(self):
        folder, pin, plan, _ = self.bundle()
        host = FakeHost(plan['spec'], self.root / 'target')
        host.customer_terminal_ready = lambda: False
        with self.assertRaisesRegex(remote.RemoteError, 'CUSTOMER_TERMINAL_REQUIRED'):
            remote.activate(folder, pin, False, True, host)
        self.assertFalse(host.root().exists())
        self.assertFalse(host.path(remote._paths(host.spec)['ssh']).exists())


if __name__ == '__main__':
    unittest.main()
