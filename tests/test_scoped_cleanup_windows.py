"""Native Windows NTFS fixtures only. No installed clients or process queries."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import config_recovery as storage
import scoped_cleanup as cleanup
import windows_cleanup as windows


@unittest.skipUnless(os.name == 'nt', 'Windows NTFS fixture and native handles required')
class WindowsScopedCleanup(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='clearpath-windows-cleanup-'))
        self.root = Path(temporary).resolve()
        self.profile = storage._private_dir(c, self.root / 'profile', create=True)
        self.config = storage._private_dir(c, self.profile / '.claude', create=True)
        self.cache = storage._private_dir(c, self.config / 'cache', create=True)
        self.data = self.cache / '测试-data.bin'
        self.write(self.data, b'synthetic cache')
        self.roaming = storage._private_dir(c, self.profile / 'Roaming', create=True)
        self.desktop = storage._private_dir(c, self.roaming / 'Claude', create=True)
        self.desktop_cache = storage._private_dir(c, self.desktop / 'Cache', create=True)
        self.write(self.desktop_cache / 'index', b'synthetic desktop cache')
        self.enterContext(patch.dict(os.environ, CLAUDE_CONFIG_DIR=''))
        self.enterContext(patch.object(windows, 'known_folder', side_effect=lambda _c, name: {
            'profile': self.profile, 'roaming': self.roaming}[name]))
        self.writers = self.enterContext(patch.object(windows, 'process_images', side_effect=lambda _c: (
            image for image in ('python.exe', 'unrelated.exe'))))
        self.request = {'schema': 'claude-cleanup-scope/1', 'target_alias': 'fixture',
                        'config_root': str(self.config), 'desktop_root': str(self.desktop),
                        'roots': [{'kind': 'cli-cache', 'path': str(self.cache)}]}

    def write(self, path, raw):
        with windows.pinned_directory(c, path.parent):
            windows.write_new(c, path, raw)

    def plan(self, request=None, allowed=()):
        folder = self.root / 'plan'
        result = cleanup.plan(c, request or self.request, folder, allowed)
        return folder, result['plan_sha256']

    def isolate(self, request=None):
        folder, digest = self.plan(request)
        operation = self.root / 'operation'
        result = cleanup.quarantine(c, folder, digest, operation, True, True)
        return operation, result['operation_sha256'], result

    def observe(self, operation, digest, output='observation'):
        folder = self.root / output
        result = cleanup.reconcile(c, operation, digest, folder)
        return folder, result['observation_sha256'], result

    def test_native_cache_round_trip_retains_metadata_and_independent_private_backup(self):
        before = cleanup._scan(c, self.cache)
        operation, digest, result = self.isolate()
        self.assertEqual(result['status'], 'quarantined', result)
        self.assertFalse(self.cache.exists())
        backup = operation / 'backup/0'
        isolated = operation / 'quarantine/0'
        self.assertTrue(storage._win_acl_summary(backup)['private'])
        self.assertTrue(storage._win_acl_summary(operation / 'journal')['private'])
        self.assertEqual((backup / self.data.name).read_bytes(), b'synthetic cache')
        self.assertNotEqual(cleanup._scan(c, backup)[1]['identity']['file_id'], before[1]['identity']['file_id'])
        self.assertTrue(cleanup._same_after_move(before, cleanup._scan(c, isolated)))
        for name in ('0000.prepared.json', '0000.done.json'):
            self.assertTrue((operation / 'journal' / name).is_file())
        observation, observed_digest, status = self.observe(operation, digest)
        self.assertEqual(status['isolated_roots'], 1)
        restored = cleanup.restore(c, observation, observed_digest, self.root / 'restored', True, True)
        self.assertEqual(restored['status'], 'restored', restored)
        self.assertTrue(cleanup._same_after_move(before, cleanup._scan(c, self.cache)))
        self.assertTrue(backup.is_dir())
        self.assertFalse(isolated.exists())

    def test_fails_closed_when_target_writer_exists_or_process_snapshot_unavailable(self):
        folder, digest = self.plan()
        operation = self.root / 'operation'
        self.writers.side_effect = lambda _c: (name for name in ('another.exe', 'CLAUDE.EXE'))
        with self.assertRaisesRegex(c.SetupError, 'WRITER_RUNNING'):
            cleanup.quarantine(c, folder, digest, operation, True, True)
        self.writers.side_effect = c.SetupError('CLEANUP_PROCESS_STATE_UNAVAILABLE')
        with self.assertRaisesRegex(c.SetupError, 'PROCESS_STATE_UNAVAILABLE'):
            cleanup.quarantine(c, folder, digest, operation, True, True)
        self.assertFalse(operation.exists())
        self.assertTrue(self.data.is_file())

    def test_default_cache_only_and_profile_bound_context(self):
        login = self.config / '.credentials.json'
        self.write(login, b'synthetic credentials')
        request = copy.deepcopy(self.request)
        request['roots'] = [{'kind': 'cli-login', 'path': str(login)}]
        with self.assertRaisesRegex(c.SetupError, 'CATEGORY_NOT_SELECTED'):
            self.plan(request)
        with patch.dict(os.environ, CLAUDE_CONFIG_DIR=str(self.desktop)):
            with self.assertRaisesRegex(c.SetupError, 'CONFIG_ROOT_MISMATCH'):
                self.plan()
        folder, digest = self.plan(request, ['login'])
        result = cleanup.quarantine(c, folder, digest, self.root / 'operation', True, True)
        self.assertEqual(result['status'], 'quarantined', result)
        self.assertEqual((self.root / 'operation/backup/0').read_bytes(), b'synthetic credentials')
        self.assertTrue(self.data.is_file())

    def test_hardlinks_ads_reparse_and_enumeration_budget_fail_closed(self):
        extra = self.cache / 'link.bin'
        os.link(self.desktop_cache / 'index', extra)
        with self.assertRaisesRegex(c.SetupError, 'HARDLINK'):
            self.plan()
        extra.unlink()
        stream = Path(str(self.data) + ':fixture')
        stream.write_bytes(b'synthetic ADS')
        with self.assertRaisesRegex(c.SetupError, 'NAMED_STREAM'):
            self.plan()
        stream.unlink()
        with patch.object(cleanup, 'MAX_ITEMS', 1):
            with self.assertRaisesRegex(c.SetupError, 'BUDGET'):
                self.plan()
        self.assertFalse((self.root / 'plan').exists())

    def test_reparse_entry_is_not_opened(self):
        target = self.cache / 'outside-directory'
        try:
            target.symlink_to(self.desktop_cache, target_is_directory=True)
        except OSError as exc:
            if exc.winerror == 1314:
                self.skipTest('Creating a synthetic reparse fixture requires symlink privilege')
            raise
        with self.assertRaisesRegex(c.SetupError, 'LINK'):
            self.plan()
        self.assertTrue((self.desktop_cache / 'index').exists())

    def test_partial_rename_and_interrupted_restore_reconcile_before_retry(self):
        request = copy.deepcopy(self.request)
        request['roots'].append({'kind': 'desktop-cache', 'path': str(self.desktop_cache)})
        real_move = windows.move
        attempted = []

        def lose_first_rename_reply(*args):
            attempted.append(1)
            real_move(*args)
            raise OSError('synthetic interrupted rename acknowledgement')

        with patch.object(windows, 'move', side_effect=lose_first_rename_reply):
            operation, digest, result = self.isolate(request)
        self.assertEqual((result['attempted_roots'], result['completed_roots']), (1, 0), result)
        self.assertEqual(len(attempted), 1)
        self.assertTrue((operation / 'journal/0000.prepared.json').is_file())
        self.assertFalse((operation / 'journal/0000.done.json').exists())
        self.assertTrue((operation / 'backup/1/index').is_file())
        self.assertFalse(self.cache.exists())
        self.assertTrue(self.desktop_cache.is_dir())
        observation, observed_digest, data = self.observe(operation, digest)
        self.assertEqual((data['isolated_roots'], data['original_present_roots']), (1, 1), data)
        with patch.object(windows, 'move', side_effect=lose_first_rename_reply):
            restored = cleanup.restore(c, observation, observed_digest, self.root / 'restore', True, True)
        self.assertEqual(restored['changes_state'], 'reconcile_required', restored)
        self.assertTrue(self.data.is_file())
        _, _, fresh = self.observe(operation, digest, 'fresh-observation')
        self.assertEqual((fresh['isolated_roots'], fresh['original_present_roots']), (0, 2), fresh)

    def test_parent_replacement_is_observed_without_scanning_the_replacement(self):
        operation, digest, isolated = self.isolate()
        self.assertEqual(isolated['status'], 'quarantined', isolated)
        old = self.profile / 'retained-config'
        self.config.rename(old)
        storage._private_dir(c, self.config, create=True)
        storage._private_dir(c, self.cache, create=True)
        self.write(self.data, b'new data under a different parent')
        observation, observed_digest, result = self.observe(operation, digest)
        self.assertEqual(result['conflict_roots'], 1)
        record = c.load_json((observation / 'observation.private.json').read_bytes())
        self.assertEqual(record['roots'][0]['state'], 'parent_conflict')
        self.assertIsNone(record['roots'][0]['original_snapshot'])
        with self.assertRaisesRegex(c.SetupError, 'RESTORE_CONFLICT'):
            cleanup.restore(c, observation, observed_digest, self.root / 'restore', True, True)
        self.assertEqual(self.data.read_bytes(), b'new data under a different parent')

    def test_destination_created_after_prepared_journal_is_never_overwritten(self):
        operation, digest, isolated = self.isolate()
        self.assertEqual(isolated['status'], 'quarantined', isolated)
        observation, observed_digest, _ = self.observe(operation, digest)
        real_move = windows.move

        def recreate_destination(*args):
            storage._private_dir(c, self.cache, create=True)
            self.write(self.data, b'new data created after preview')
            real_move(*args)

        with patch.object(windows, 'move', side_effect=recreate_destination):
            result = cleanup.restore(c, observation, observed_digest, self.root / 'restore', True, True)
        self.assertEqual(result['status'], 'partial_or_unconfirmed', result)
        self.assertEqual(self.data.read_bytes(), b'new data created after preview')
        self.assertTrue((operation / 'quarantine/0' / self.data.name).is_file())


if __name__ == '__main__':
    unittest.main()
