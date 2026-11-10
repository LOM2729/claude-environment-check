"""Desktop adapter tests on disposable fixtures only. No processes or network."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'desktop')]

import claude_setup as c
import config_recovery as storage
import guard_handoff
import native_client
import operation_tools
import remote_setup
import scoped_cleanup
import system_guard
import test_guard_handoff as guard_fixture
import test_native_client as native_fixture
import test_scoped_cleanup as cleanup_fixture


@unittest.skipUnless(os.name == 'posix', 'Isolated POSIX fixture, no native desktop acceptance')
class DesktopOperationTools(unittest.TestCase):
    def setUp(self):
        self.fixture = cleanup_fixture.ScopedCleanup()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = storage._private_dir(c, self.fixture.root / 'tools', create=True)
        self.enterContext(patch.object(scoped_cleanup, 'NativeHost', return_value=self.fixture.host))
        self.enterContext(patch.object(subprocess, 'run', side_effect=AssertionError('native process forbidden')))
        self.enterContext(patch.object(subprocess, 'Popen', side_effect=AssertionError('subprocess forbidden')))
        self.prefix = None

    def run_tool(self, action, **payload):
        return operation_tools.dispatch(c, self.root, action, payload, self.prefix)

    def cleanup_plan(self):
        return self.run_tool('cleanup_plan', kind='cli', path=str(self.fixture.config))

    def test_cache_only_review_apply_restore_and_no_replay(self):
        history = self.fixture.config / 'history.jsonl'
        history.write_bytes(b'synthetic history')
        plan = self.cleanup_plan()
        token = plan['token']
        self.assertRegex(token, r'^[a-f0-9]{32}$')
        self.assertEqual(plan['next'], ['cleanup_apply'])
        self.assertIn(str(self.fixture.cache), plan['details'])
        self.assertNotIn(str(history), plan['details'])
        self.assertEqual(self.run_tool('cleanup_latest')['token'], token)
        applied = self.run_tool('cleanup_apply', token=token, stopped=True)
        self.assertEqual(applied['next'], ['cleanup_reconcile'])
        self.assertFalse(self.fixture.cache.exists())
        self.assertEqual(history.read_bytes(), b'synthetic history')
        with self.assertRaisesRegex(c.SetupError, 'TOOLS_CLEANUP_PLAN_USED'):
            self.run_tool('cleanup_apply', token=token, stopped=True)
        observed = self.run_tool('cleanup_reconcile', token=token)
        self.assertIn('cleanup_restore', observed['next'])
        self.assertIn(str(self.fixture.cache), observed['details'])
        self.assertIn('cleanup_restore', self.run_tool('cleanup_latest')['next'])
        restored = self.run_tool('cleanup_restore', token=token, stopped=True)
        self.assertEqual(restored['next'], [])
        self.assertTrue((Path(restored['folder']) / 'operation/backup/0/data.bin').exists())
        self.assertEqual((self.fixture.cache / 'data.bin').read_bytes(), b'synthetic cache')
        with self.assertRaisesRegex(c.SetupError, 'TOOLS_CLEANUP_OBSERVATION_REQUIRED'):
            self.run_tool('cleanup_restore', token=token, stopped=True)

    def test_no_cache_does_not_create_review_or_inspect_non_cache_items(self):
        (self.fixture.cache / 'data.bin').unlink()
        self.fixture.cache.rmdir()
        (self.fixture.config / 'history.jsonl').symlink_to(self.fixture.root / 'unopened-file')
        result = self.cleanup_plan()
        self.assertNotIn('token', result)
        self.assertEqual(result['next'], [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_partial_quarantine_keeps_journal_and_recovers_move(self):
        quarantine = scoped_cleanup.quarantine

        def interrupted_move(source, dest):
            os.rename(source, dest)
            raise OSError('synthetic interruption after rename')

        def interrupted(*args, **kwargs):
            result = quarantine(*args, mover=interrupted_move, **kwargs)
            self.assertEqual(result['status'], 'partial_or_unconfirmed')
            # Simulate an interruption after the durable operation was written
            # but before the desktop adapter can copy its digest into its state.
            raise c.SetupError('SYNTHETIC_AFTER_MOVE')

        stale = self.cleanup_plan()['token']
        token = self.cleanup_plan()['token']
        with patch.object(scoped_cleanup, 'quarantine', side_effect=interrupted):
            applied = self.run_tool('cleanup_apply', token=token, stopped=True)
        self.assertEqual(applied['next'], ['cleanup_reconcile'])
        self.assertTrue((Path(applied['folder']) / 'operation/operation.private.json').is_file())
        self.assertEqual(self.run_tool('cleanup_latest')['token'], token)
        blocked = self.cleanup_plan()
        self.assertEqual(blocked['token'], token)
        self.assertEqual(blocked['next'], ['cleanup_reconcile'])
        self.assertEqual(self.run_tool('cleanup_apply', token=stale, stopped=True)['token'], token)
        self.assertIn('cleanup_restore', self.run_tool('cleanup_reconcile', token=token)['next'])
        self.run_tool('cleanup_restore', token=token, stopped=True)
        self.assertTrue(self.fixture.cache.is_dir())

    def test_new_plan_preserves_older_verified_operation_and_recovery_guide(self):
        token = self.cleanup_plan()['token']
        old = Path(self.run_tool('cleanup_apply', token=token, stopped=True)['folder'])
        (self.fixture.config / '.cache').mkdir()
        newer = self.cleanup_plan()
        self.assertNotEqual(newer['token'], token)
        self.assertEqual(self.run_tool('cleanup_latest')['token'], newer['token'])
        self.assertTrue((old / 'operation/backup/0/data.bin').is_file())
        self.assertIn('cleanup-reconcile', (old / '缓存恢复说明.txt').read_text(encoding='utf-8'))
        self.assertIn('cleanup_restore', self.run_tool('cleanup_reconcile', token=token)['next'])

    def test_changed_observation_is_consumed_and_new_cache_is_preserved(self):
        token = self.cleanup_plan()['token']
        self.run_tool('cleanup_apply', token=token, stopped=True)
        self.assertIn('cleanup_restore', self.run_tool('cleanup_reconcile', token=token)['next'])
        self.fixture.cache.mkdir()
        (self.fixture.cache / 'new').write_bytes(b'keep')
        pending = self.run_tool('cleanup_restore', token=token, stopped=True)
        self.assertEqual(pending['next'], ['cleanup_reconcile'])
        self.assertEqual((self.fixture.cache / 'new').read_bytes(), b'keep')
        observed = self.run_tool('cleanup_reconcile', token=token)
        self.assertNotIn('cleanup_restore', observed['next'])

    def test_invalid_fields_approval_and_token_cannot_request_writes(self):
        token = self.cleanup_plan()['token']
        for payload in ({'token': token, 'stopped': 1}, {'token': token, 'stopped': False},
                        {'token': token, 'stopped': True, 'allow': True}, {'token': '../tools', 'stopped': True}):
            with self.subTest(payload=payload), self.assertRaises(c.SetupError):
                self.run_tool('cleanup_apply', **payload)
        self.assertTrue(self.fixture.cache.is_dir())
        self.assertEqual(self.run_tool('cleanup_latest')['next'], ['cleanup_apply'])

    def native_data(self):
        fixture = native_fixture.NativeClient()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.enterContext(patch.object(native_client, 'NativeHost', return_value=fixture.host))
        return fixture

    def test_native_known_policy_review_and_receipt_bound_rollback(self):
        fixture = self.native_data()
        options = self.run_tool('native_inspect')
        self.assertIn('fixture-group', options['policies'])
        self.assertEqual(options['policies'], sorted(options['policies']))
        plan = self.run_tool('native_plan', kind='DOMAIN', domain='example.com', policy='fixture-group')
        token = plan['token']
        self.assertEqual(plan['next'], ['native_apply'])
        self.assertIn(str(fixture.target), plan['details'])
        self.assertEqual(fixture.target.read_bytes(), native_fixture.RAW)
        with self.assertRaisesRegex(c.SetupError, 'TOOLS_NATIVE_RECEIPT_REQUIRED'):
            self.run_tool('native_rollback', token=token, stopped=True)
        applied = self.run_tool('native_apply', token=token, stopped=True)
        self.assertEqual(applied['next'], ['native_rollback'])
        self.assertIn(b'DOMAIN,example.com,fixture-group', fixture.target.read_bytes())
        self.assertTrue((Path(applied['folder']) / 'receipt.private.json').is_file())
        self.assertEqual(self.run_tool('native_latest')['token'], token)
        rolled_back = self.run_tool('native_rollback', token=token, stopped=True)
        self.assertEqual(rolled_back['next'], [])
        self.assertEqual(fixture.target.read_bytes(), native_fixture.RAW)

    def test_native_ambiguous_write_keeps_intent_without_automatic_rollback(self):
        fixture = self.native_data()
        token = self.run_tool('native_plan', kind='DOMAIN', domain='example.com', policy='fixture-group')['token']
        apply = fixture.host.apply_text

        def running_after_write(*args):
            result = apply(*args)
            fixture.host.running = True
            return result

        with patch.object(fixture.host, 'apply_text', side_effect=running_after_write):
            pending = self.run_tool('native_apply', token=token, stopped=True)
        self.assertIn('尚未确认', pending['message'])
        self.assertNotIn('native_rollback', pending['next'])
        self.assertTrue((Path(pending['folder']) / 'apply/intent.private.json').is_file())
        self.assertEqual(self.run_tool('native_latest')['token'], token)
        with self.assertRaisesRegex(c.SetupError, 'TOOLS_NATIVE_PLAN_USED'):
            self.run_tool('native_apply', token=token, stopped=True)

    def test_native_no_change_does_not_replace_recoverable_token(self):
        self.native_data()
        request = {'kind': 'DOMAIN', 'domain': 'example.com', 'policy': 'fixture-group'}
        token = self.run_tool('native_plan', **request)['token']
        self.run_tool('native_apply', token=token, stopped=True)
        no_change = self.run_tool('native_plan', **request)
        self.assertNotIn('token', no_change)
        self.assertEqual(no_change['next'], [])
        self.assertEqual(self.run_tool('native_latest')['token'], token)

    def test_native_inspection_bounds_visible_policies(self):
        names = {'x' * 129, 'bad,rule', 'bad\nline', '\u202einvalid', *{f'p{i:03d}' for i in range(150)}}
        with patch.object(native_client, 'capture', return_value={'policy_names': names, 'target_bytes': b'private'}):
            result = self.run_tool('native_inspect')
        self.assertEqual(result['policies'], [f'p{i:03d}' for i in range(128)])
        self.assertNotIn('private', repr(result))

    def test_guard_export_writes_existing_launch_bundle_and_binds_trusted_runtime(self):
        plan = system_guard.make_plan(guard_fixture.spec())
        source = self.fixture.root / 'guard-plan.json'
        source.write_bytes(c.encode(plan))
        executable = self.fixture.root / 'synthetic-runtime'
        executable.write_bytes(b'never run')
        trusted = [str(executable), '--cli']
        with patch.object(guard_handoff, 'runtime_prefix', return_value=trusted), \
                patch.object(system_guard, 'native_platform', return_value='macos'):
            self.prefix = [str(executable), '--unexpected']
            with self.assertRaisesRegex(c.SetupError, 'TOOLS_GUARD_RUNTIME_INVALID'):
                self.run_tool('guard_export', path=str(source))
            self.prefix = trusted
            output = self.run_tool('guard_export', path=str(source))
        folder = Path(output['folder'])
        manifest = c.load_json((folder / 'launch-manifest.private.json').read_bytes())
        self.assertEqual(manifest['plan_sha256'], system_guard.digest(plan))
        self.assertFalse(manifest['authorization_saved'])
        self.assertTrue((folder / '启用断线保护.command').is_file())
        self.assertEqual(output['next'], [])

    def test_remote_export_writes_portable_pinned_bundle_and_rejects_modified_plan(self):
        plan = remote_setup.make_plan({
            'schema': 'clearpath-remote-input/1', 'scope': 'fixture', 'platform': 'linux',
            'distribution': 'debian', 'modules': ['ssh'], 'fuse_seconds': 180,
            'ssh': {'port': 2222, 'password_authentication': False, 'permit_root_login': 'prohibit-password',
                    'allow_users': ['operator'], 'activation': 'restart'},
        })
        source = self.fixture.root / 'remote-plan.json'
        source.write_bytes(c.encode(plan))
        output = self.run_tool('remote_export', path=str(source))
        folder = Path(output['folder'])
        _, manifest, bundled, _ = remote_setup.read_bundle(folder, c.sha((folder / 'bundle.json').read_bytes()))
        self.assertEqual(manifest['plan_sha256'], remote_setup.digest(plan))
        self.assertEqual(bundled, plan)
        self.assertFalse(bundled['authorization_saved'])
        plan['authorization_saved'] = True
        source.write_bytes(c.encode(plan))
        with self.assertRaisesRegex(c.SetupError, 'REMOTE_PLAN_RECOMPILE_MISMATCH'):
            self.run_tool('remote_export', path=str(source))
        self.assertEqual(len(list(self.root.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
