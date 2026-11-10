"""Public CLI integration using only synthetic files and forbidden live transports."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c


class CapabilityCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='clearpath-capability-cli-')
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)

    def run_cli(self, args, code=0):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(c, 'collect', side_effect=AssertionError('no native collection')), \
                patch.object(c, 'run_fixed', side_effect=AssertionError('no native commands')), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            actual = c.main(list(map(str, args)))
        self.assertEqual(actual, code, stdout.getvalue() + stderr.getvalue())
        return json.loads(stdout.getvalue() if code in (0, 2) else stderr.getvalue())

    def test_every_new_module_is_discoverable_without_native_inspection(self):
        result = self.run_cli(['capabilities'])
        self.assertEqual(len(result['features']), 7)
        commands = {name for feature in result['features'] for name in feature['commands']}
        self.assertTrue({'intake-assess', 'webrtc-serve', 'skill-update-check',
                         'cleanup-restore', 'native-client-rollback', 'guard-confirm',
                         'remote-rollback'} <= commands)
        self.assertFalse(result['system_changes_performed'])
        self.assertTrue(all(x['native_acceptance'] == 'not_run' for x in result['features']))
        support = {x['module']: x['support'] for x in result['features']}
        self.assertEqual(support['scoped_cleanup']['native_write_platforms'], ['macos'])
        self.assertFalse(support['system_guard']['domestic_v4_native_compilation'])
        self.assertFalse(support['remote_setup']['implicit_ssh_execution'])

    def test_offline_intake_cli_roundtrip_never_grants_actions(self):
        answers = self.root / 'answers.json'
        answers.write_bytes(c.encode([{'field': 'platform', 'state': 'known', 'value': 'macos'},
                                     {'field': 'priority', 'state': 'known', 'value': 'isolation'}]))
        state = self.root / 'state.json'
        result = self.run_cli(['intake-start', '--task', 'compare', '--answers', answers, '--output', state])
        self.assertEqual(result['status'], 'explanation_only')
        result = self.run_cli(['intake-assess', '--state', state])
        self.assertFalse(result['action_authorized'])
        self.assertEqual(result['network_requests'], 0)

    def test_webrtc_plan_does_not_open_browser_or_send_stun(self):
        config = self.root / 'config.json';config.write_text('{}')
        plan = self.root / 'webrtc.json'
        result = self.run_cli(['webrtc-plan', '--config', config, '--target-alias', 'fixture',
                               '--profile-alias', 'profile-a', '--platform', 'macos',
                               '--stun-url', 'stun:stun.example.invalid:3478', '--output', plan])
        self.assertEqual(result['network_requests'], 0)
        self.assertFalse(result['browser_launched'])
        self.assertEqual(json.loads(plan.read_text())['config_sha256'], c.sha(b'{}'))

    def test_update_comparison_uses_supplied_snapshot_without_network(self):
        import skill_updates as updates
        skill = self.root / 'claude-mac-readiness';skill.mkdir()
        raw = b'---\nname: claude-mac-readiness\ndescription: fixture\n---\n'
        (skill / 'SKILL.md').write_bytes(raw)
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        snapshot = self.root / 'snapshot.json'
        snapshot.write_bytes(c.encode({'schema': updates.SNAPSHOT_SCHEMA, 'repository': updates.REPOSITORY,
            'commit': 'a' * 40, 'tree_sha': 'b' * 40, 'tree': {'sha': 'b' * 40, 'truncated': False,
            'tree': [{'path': '.agents/skills/claude-mac-readiness/SKILL.md',
                      'mode': '100644', 'type': 'blob', 'sha': blob}]}}))
        with patch.object(updates, 'fetch_bytes', side_effect=AssertionError('no GitHub request')):
            result = self.run_cli(['skill-update-check', '--skill-root', skill, '--platform', 'mac',
                                   '--snapshot', snapshot, '--output', self.root / 'comparison.json'])
        self.assertEqual(result['status'], 'upstream_matches')
        self.assertFalse(result['latest_version_checked'])
        self.assertFalse(result['installed_files_modified'])

    def test_guard_plan_renders_all_supported_platforms_offline(self):
        import system_guard as guard
        for target in ('macos', 'windows', 'linux'):
            request = self.root / (target + '.json')
            value = {'schema': 'clearpath-guard-input/1', 'scope': 'fixture', 'platform': target,
                     'policy': 'unified-v4', 'interfaces': ['Ethernet' if target == 'windows' else 'eth0'],
                     'nodes': [{'address': '192.0.2.10', 'ports': [443], 'protocol': 'tcp'}]}
            if target == 'windows':
                value['core_path'] = r'C:\Example\mihomo.exe'
            request.write_bytes(c.encode(value))
            with patch.object(guard.NativeHost, 'command', side_effect=AssertionError('no native commands')):
                result = self.run_cli(['guard-plan', '--input', request, '--output', self.root / (target + '-plan.json')])
            self.assertEqual(result['platform'], target)
            self.assertFalse(result['system_changes'])

    def test_missing_system_write_permission_stops_before_read_or_host_access(self):
        import system_guard as guard
        with patch.object(guard.NativeHost, 'check', side_effect=AssertionError('no live host check')):
            result = self.run_cli(['guard-on', '--state-dir', self.root / 'not-live-state',
                                   '--plan', self.root / 'absent.json', '--plan-sha256', 'a' * 64], code=1)
        self.assertIn('REQUIRED', result['error'])

    def test_interrupted_mutation_never_claims_no_change(self):
        import system_guard as guard
        with patch.object(guard, 'run', side_effect=KeyboardInterrupt):
            result = self.run_cli(['guard-on', '--state-dir', self.root / 'state',
                                   '--plan', self.root / 'absent.json', '--plan-sha256', 'a' * 64], code=130)
        self.assertIsNone(result['system_changes_performed'])
        self.assertEqual(result['error'], 'OPERATION_CANCELLED')
        self.assertIn('check_private_receipt', result['recovery_state'])

    def test_incomplete_module_result_keeps_nonzero_exit(self):
        import browser_webrtc as browser
        with patch.object(browser, 'run', return_value={'status': 'incomplete', 'required_checks_completed': False}):
            self.run_cli(['webrtc-report', '--plan', 'unused', '--config', 'unused',
                          '--input', 'unused', '--output', 'unused'], code=2)


if __name__ == '__main__':
    unittest.main()
