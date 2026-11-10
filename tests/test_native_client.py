"""Temporary product fixtures; no installed applications, real process list or reload."""
import copy
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import config_recovery as storage
import native_client as native

RAW = b'\xef\xbb\xbf# fixture \xe4\xb8\xad\xe6\x96\x87\r\nprepend: [  ] # keep this comment\r\nappend: []\r\ndelete: []\r\n'


class FixtureHost(native.NativeHost):
    def __init__(self, app, support):
        self.app, self.support = app, support
        self.running = False
        self.guards = 0

    def supported(self, context):
        context.require(os.name == 'posix', 'FIXTURE_POSIX_REQUIRED')

    def paths(self):
        return self.app, self.support

    def guard(self, context):
        self.guards += 1
        context.require(not self.running, 'NATIVE_CLIENT_GUI_RUNNING')

    def apply_text(self, context, folder, pin, output):
        # Test only: use the real POSIX transaction on synthetic files without
        # claiming this Linux CI runner is a native Mac product installation.
        folder, record = storage._artifact(context, folder, 'plan.json', pin, 'plan')
        before, after = storage._snapshots(context, folder, record)
        storage._assert_expected(context, record['target']['path'], record['target'])
        dest = storage._private_dir(context, output, create=True)
        return storage._transaction(context, before, after, record['target'], dest, pin, 'apply')

    def rollback_text(self, context, receipt, pin, output):
        _, _, _, before, after = storage._load_receipt(context, receipt, pin)
        _, intent, final, _, _ = storage._load_receipt(context, receipt, pin)
        state, current = storage._inspection(context, intent, final)
        context.require(state == 'committed_unchanged', 'RECOVERY_ROLLBACK_CONFLICT_OR_INCOMPLETE_RECEIPT')
        dest = storage._private_dir(context, output, create=True)
        return storage._transaction(context, after, before, current, dest, pin, 'rollback')


@unittest.skipUnless(os.name == 'posix', 'Synthetic fixed Mac adapter; no pretend-platform CLI')
class NativeClient(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='clearpath-native-fixture-')
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.app = self.root / 'Clash Verge.app/Contents/Info.plist'
        self.app.parent.mkdir(mode=0o700, parents=True)
        self.app.write_bytes(plistlib.dumps({'CFBundleShortVersionString': '2.5.8', 'CFBundleName': 'fixture',
                                           'CFBundleIdentifier': 'io.github.clash-verge-rev.clash-verge-rev'}))
        self.support = self.root / 'support'
        self.support.mkdir(mode=0o700)
        (self.support / 'profiles').mkdir(mode=0o700)
        self.index = self.support / 'profiles.yaml'
        self.index_data = {'current': 'R1', 'items': [
            {'uid': 'R1', 'type': 'remote', 'file': 'base.yaml',
             'option': {'rules': 'r1', 'merge': 'm1', 'script': 's1'}},
            {'uid': 'r1', 'type': 'rules', 'file': 'rules.yaml'}]}
        self.write_index()
        self.base = self.support / 'profiles/base.yaml'
        self.base.write_bytes(b'proxies: [{name: fixture-node, type: socks5, server: example.invalid, port: 1080}]\nproxy-groups: [{name: fixture-group, type: select, proxies: [fixture-node]}]\nrules: [MATCH,REJECT]\n')
        self.target = self.support / 'profiles/rules.yaml'
        self.target.write_bytes(RAW)
        self.host = FixtureHost(self.app, self.support)
        self.request = {'schema': 'clearpath-native-rules/1', 'target_alias': 'fixture',
                        'rules': ['DOMAIN,example.com,fixture-group']}

    def tearDown(self):
        self.temp.cleanup()

    def write_index(self):
        self.index.write_text(json.dumps(self.index_data))  # JSON is a YAML subset.

    def plan(self):
        folder = self.root / 'plan'
        result = native.prepare(c, self.request, folder, self.host)
        self.assertEqual(self.host.guards, 0, 'planning must not collect live process state')
        return folder, result['plan_sha256'], result

    def applied(self):
        folder, pin, _ = self.plan()
        output = self.root / 'apply'
        result = native.apply(c, folder, pin, output, True, True, self.host)
        self.assertEqual(result['status'], 'written_but_not_verified', result)
        return folder, pin, output, result

    def test_plan_preserves_comments_bom_crlf_and_binds_private_target(self):
        folder, pin, result = self.plan()
        candidate = (folder / 'candidate.private.yaml').read_bytes()
        self.assertEqual(candidate, RAW.replace(b'[  ]', b'[  "DOMAIN,example.com,fixture-group"]', 1))
        self.assertEqual(self.target.read_bytes(), RAW)
        self.assertEqual(c.sha((folder / 'native-plan.private.json').read_bytes()), pin)
        self.assertTrue(result['later_chain_review_required'])
        self.assertFalse(result['config_file_changed'])
        self.assertNotIn('example.com', c.encode(result).decode())
        self.assertNotIn(str(self.target), c.encode(result).decode())

    def test_apply_and_protected_rollback_reuse_actual_text_transaction(self):
        folder, pin, receipt, applied = self.applied()
        self.assertEqual(applied['byte_readback'] if 'byte_readback' in applied else applied['readback_checks']['content_matches'], True)
        self.assertEqual(applied['application_reload'], 'not_run')
        self.assertEqual(applied['effective_routing'], 'not_run')
        self.assertNotEqual(self.target.read_bytes(), RAW)
        checked = native.check(c, folder, pin, receipt, applied['receipt_sha256'], self.root / 'check', self.host)
        self.assertTrue(checked['native_source_binding_matches'])
        restored = native.rollback(c, folder, pin, receipt, applied['receipt_sha256'], self.root / 'rollback', True, True, self.host)
        self.assertEqual(restored['recovery_state'], 'committed', restored)
        self.assertEqual(self.target.read_bytes(), RAW)
        self.assertEqual(restored['application_reload'], 'not_run')

    def test_wrong_version_has_no_candidate_or_output(self):
        self.app.write_bytes(plistlib.dumps({'CFBundleShortVersionString': '2.5.9'}))
        with self.assertRaisesRegex(c.SetupError, 'VERSION_UNSUPPORTED'):
            native.prepare(c, self.request, self.root / 'plan', self.host)
        self.assertFalse((self.root / 'plan').exists())

    def test_shared_extension_duplicate_uid_and_file_alias_are_rejected(self):
        original = copy.deepcopy(self.index_data)
        self.index_data['items'].append({'uid': 'R2', 'type': 'local', 'file': 'other.yaml', 'option': {'rules': 'r1'}})
        self.write_index()
        with self.assertRaisesRegex(c.SetupError, 'SHARED_EXTENSION'):
            native.capture(c, self.host)
        self.index_data = copy.deepcopy(original)
        self.index_data['items'].append({'uid': 'r1', 'type': 'rules', 'file': 'other.yaml'})
        self.write_index()
        with self.assertRaisesRegex(c.SetupError, 'ALIAS_CONFLICT'):
            native.capture(c, self.host)
        self.index_data = copy.deepcopy(original)
        self.index_data['items'].append({'uid': 'r2', 'type': 'rules', 'file': 'rules.yaml'})
        self.write_index()
        with self.assertRaisesRegex(c.SetupError, 'FILE_ALIAS_CONFLICT'):
            native.capture(c, self.host)

    def test_only_existing_policy_and_supported_domain_rule_are_allowed(self):
        for rule in ['MATCH,fixture-group', 'DOMAIN,example.com,DIRECT',
                     'DOMAIN,example.com,missing-group', 'DOMAIN,example.com,fixture-group\n']:
            request = dict(self.request, rules=[rule])
            with self.assertRaises(c.SetupError):
                native.prepare(c, request, self.root / 'plan', self.host)
        self.assertFalse((self.root / 'plan').exists())

    def test_nonempty_or_destructive_rules_extensions_are_not_reformatted(self):
        for raw in [b'prepend: [DOMAIN,old.invalid,REJECT]\nappend: []\ndelete: []\n',
                    b'prepend: []\nappend: []\ndelete: [old]\n',
                    b'prepend: []\nappend: []\ndelete: []\ncustom: keep\n']:
            self.target.write_bytes(raw)
            with self.assertRaises(c.SetupError):
                native.prepare(c, self.request, self.root / 'plan', self.host)
            self.assertEqual(self.target.read_bytes(), raw)

    def test_exact_repeat_is_no_change_without_another_backup_or_plan(self):
        self.target.write_bytes(b'prepend: ["DOMAIN,example.com,fixture-group"]\nappend: []\ndelete: []\n')
        result = native.prepare(c, self.request, self.root / 'plan', self.host)
        self.assertEqual(result['status'], 'no_change')
        self.assertFalse((self.root / 'plan').exists())

    def test_missing_current_profile_or_cross_directory_filename_stops(self):
        self.index_data['current'] = 'missing'
        self.write_index()
        with self.assertRaisesRegex(c.SetupError, 'CURRENT_PROFILE'):
            native.capture(c, self.host)
        self.index_data['current'] = 'R1'
        self.index_data['items'][1]['file'] = '../other.yaml'
        self.write_index()
        with self.assertRaisesRegex(c.SetupError, 'FILENAME'):
            native.capture(c, self.host)

    def test_explicit_write_and_stopped_gui_are_required(self):
        folder, pin, _ = self.plan()
        with self.assertRaisesRegex(c.SetupError, 'CURRENT_WRITE'):
            native.apply(c, folder, pin, self.root / 'apply', False, True, self.host)
        self.host.running = True
        with self.assertRaisesRegex(c.SetupError, 'GUI_RUNNING'):
            native.apply(c, folder, pin, self.root / 'apply', True, True, self.host)
        self.assertEqual(self.target.read_bytes(), RAW)
        self.assertFalse((self.root / 'apply').exists())

    def test_base_or_profile_drift_invalidates_review_before_write(self):
        folder, pin, _ = self.plan()
        self.base.write_bytes(self.base.read_bytes() + b'# later customer change\n')
        with self.assertRaisesRegex(c.SetupError, 'SOURCE_CHANGED'):
            native.apply(c, folder, pin, self.root / 'apply', True, True, self.host)
        self.assertEqual(self.target.read_bytes(), RAW)

    def test_wrong_plan_digest_and_target_edit_are_not_overwritten(self):
        folder, pin, _ = self.plan()
        with self.assertRaisesRegex(c.SetupError, 'PLAN_CHANGED'):
            native.apply(c, folder, '0' * 64, self.root / 'apply', True, True, self.host)
        edited = RAW + b'# later customer comment\r\n'
        self.target.write_bytes(edited)
        with self.assertRaisesRegex(c.SetupError, 'TARGET_CONFLICT'):
            native.apply(c, folder, pin, self.root / 'apply', True, True, self.host)
        self.assertEqual(self.target.read_bytes(), edited)

    def test_gui_starting_after_commit_keeps_recovery_and_unknown_status(self):
        folder, pin, _ = self.plan()
        original = storage._replace
        def starts_after_replace(*args, **kwargs):
            original(*args, **kwargs)
            self.host.running = True
        with patch.object(storage, '_replace', side_effect=starts_after_replace):
            result = native.apply(c, folder, pin, self.root / 'apply', True, True, self.host)
        self.assertEqual(result['exit_code'], 2)
        self.assertEqual(result['status'], 'partial_or_unconfirmed')
        self.assertTrue(result['intent_sha256'])
        self.assertTrue((self.root / 'apply/original.private.bin').is_file())
        self.assertNotEqual(self.target.read_bytes(), RAW)

    def test_later_user_edit_blocks_rollback(self):
        folder, pin, receipt, applied = self.applied()
        self.target.write_bytes(self.target.read_bytes() + b'# do not overwrite\n')
        with self.assertRaisesRegex(c.SetupError, 'ROLLBACK_CONFLICT'):
            native.rollback(c, folder, pin, receipt, applied['receipt_sha256'], self.root / 'rollback', True, True, self.host)
        self.assertIn(b'do not overwrite', self.target.read_bytes())

    def test_receipt_for_another_text_target_cannot_be_used(self):
        folder, pin, receipt, applied = self.applied()
        value = c.load_json((receipt / 'intent.private.json').read_bytes())
        value['target']['path'] = str(self.root / 'unrelated.yaml')
        # Use a complete independent transaction rather than forging the first receipt.
        unrelated = self.root / 'unrelated.yaml'
        other_candidate = self.root / 'other-candidate.yaml'
        unrelated.write_bytes(b'value: before\n')
        other_candidate.write_bytes(b'value: after\n')
        p = storage.prepare(c, unrelated, other_candidate, self.root / 'other-plan')
        other = self.host.apply_text(c, self.root / 'other-plan', p['plan_sha256'], self.root / 'other-receipt')
        with self.assertRaisesRegex(c.SetupError, 'RECEIPT_SCOPE_CHANGED'):
            native.rollback(c, folder, pin, self.root / 'other-receipt', other['receipt_sha256'], self.root / 'rollback', True, True, self.host)

    def test_symlinked_app_or_target_metadata_is_rejected(self):
        actual = self.root / 'real-info.plist'
        self.app.rename(actual)
        self.app.symlink_to(actual)
        with self.assertRaisesRegex(c.SetupError, 'LINK_REJECTED'):
            native.capture(c, self.host)

    def test_same_target_receipt_from_another_plan_is_not_native_authority(self):
        folder, pin, _, _ = self.applied()
        other_candidate = self.root / 'later-candidate.yaml'
        other_candidate.write_bytes(self.target.read_bytes().replace(b'example.com', b'other.invalid'))
        prepared = storage.prepare(c, self.target, other_candidate, self.root / 'later-plan')
        applied = self.host.apply_text(c, self.root / 'later-plan', prepared['plan_sha256'], self.root / 'later-receipt')
        with self.assertRaisesRegex(c.SetupError, 'RECEIPT_SCOPE_CHANGED'):
            native.rollback(c, folder, pin, self.root / 'later-receipt', applied['receipt_sha256'],
                            self.root / 'rollback', True, True, self.host)

    def test_rebound_text_plan_cannot_expand_the_native_requested_change(self):
        folder, _, _ = self.plan()
        text = folder / 'text-plan'
        changed = (text / 'candidate.private.bin').read_bytes() + b'custom: unreviewed\n'
        (text / 'candidate.private.bin').write_bytes(changed)
        text_plan = c.load_json((text / 'plan.json').read_bytes())
        text_plan['candidate_sha256'] = c.sha(changed)
        (text / 'plan.json').write_bytes(c.encode(text_plan))
        plan = c.load_json((folder / 'native-plan.private.json').read_bytes())
        plan['text_plan_sha256'] = c.sha(c.encode(text_plan))
        (folder / 'native-plan.private.json').write_bytes(c.encode(plan))
        with self.assertRaisesRegex(c.SetupError, 'CANDIDATE_SCOPE_CHANGED'):
            native.apply(c, folder, c.sha(c.encode(plan)), self.root / 'apply', True, True, self.host)
        self.assertEqual(self.target.read_bytes(), RAW)


class FixedNativeGuard(unittest.TestCase):
    def test_only_gui_blocks_and_fixed_process_command_never_stops_core(self):
        done = subprocess.CompletedProcess([], 0, b'/Library/PrivilegedHelperTools/clash-verge-service\n/usr/local/bin/verge-mihomo\n', b'')
        with patch.object(native.platform, 'system', return_value='Darwin'), \
                patch.object(native.subprocess, 'run', return_value=done) as run:
            native.NativeHost().guard(c)
            self.assertEqual(run.call_args.args[0], ['/bin/ps', '-axo', 'comm='])
            self.assertFalse(run.call_args.kwargs['shell'])
        done.stdout = b'/Applications/Clash Verge.app/Contents/MacOS/clash-verge\n'
        with patch.object(native.platform, 'system', return_value='Darwin'), \
                patch.object(native.subprocess, 'run', return_value=done):
            with self.assertRaisesRegex(c.SetupError, 'GUI_RUNNING'):
                native.NativeHost().guard(c)

    def test_unsupported_platform_and_failed_process_query_are_fixed_errors(self):
        with patch.object(native.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(c.SetupError, 'PLATFORM_UNSUPPORTED'):
                native.NativeHost().supported(c)
        with patch.object(native.platform, 'system', return_value='Darwin'), \
                patch.object(native.subprocess, 'run', side_effect=OSError('private failure')):
            with self.assertRaisesRegex(c.SetupError, 'PROCESS_STATE_UNAVAILABLE'):
                native.NativeHost().guard(c)


if __name__ == '__main__':
    unittest.main()
