"""Synthetic temporary data only; never inspect installed Claude or live processes."""
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


class FixtureHost(cleanup.NativeHost):
    def __init__(self):
        self.calls = 0
        self.running = False
        self.changed_binding = False

    def supported(self, context):
        context.require(os.name == 'posix', 'FIXTURE_POSIX_REQUIRED')

    def binding(self):
        result = storage._binding()
        return dict(result, fixture='different' if self.changed_binding else 'temporary-only')

    def guard(self, context):
        self.calls += 1
        context.require(not self.running, 'CLEANUP_TARGET_WRITER_RUNNING')

    def validate_scope(self, context, request):
        pass  # This API-only fixture never stands for the user's actual home.


@unittest.skipUnless(os.name == 'posix', 'POSIX directory-handle fixtures')
class ScopedCleanup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='clearpath-cleanup-fixture-')
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.config = self.root / '.claude'
        self.desktop = self.root / 'Claude'
        self.config.mkdir(mode=0o700)
        self.desktop.mkdir(mode=0o700)
        self.cache = self.config / 'cache'
        self.cache.mkdir(mode=0o700)
        (self.cache / 'data.bin').write_bytes(b'synthetic cache')
        self.other = self.desktop / 'Cache'
        self.other.mkdir(mode=0o700)
        (self.other / 'other.bin').write_bytes(b'synthetic desktop cache')
        self.host = FixtureHost()
        self.request = {'schema': 'claude-cleanup-scope/1', 'target_alias': 'fixture',
                        'config_root': str(self.config), 'desktop_root': str(self.desktop),
                        'roots': [{'kind': 'cli-cache', 'path': str(self.cache)}], 'protected': []}

    def tearDown(self):
        self.temp.cleanup()

    def make_plan(self, request=None, output='plan', allowed=()):
        folder = self.root / output
        result = cleanup.plan(c, request or self.request, folder, allowed, self.host)
        return folder, result['plan_sha256']

    def isolate(self, request=None, mover=os.rename):
        folder, pin = self.make_plan(request)
        operation = self.root / 'operation'
        result = cleanup.quarantine(c, folder, pin, operation, True, True, self.host, mover)
        return operation, result['operation_sha256'], result

    def observe(self, operation, pin, name='observation'):
        out = self.root / name
        result = cleanup.reconcile(c, operation, pin, out, self.host)
        return out, result['observation_sha256'], result

    def test_inventory_only_lists_requested_locations_and_default_cache(self):
        with patch.object(c, 'read_bytes', side_effect=AssertionError('must not read data')):
            result = cleanup.inventory(c, self.config, None, 'fixture', self.root / 'inventory')
        self.assertEqual(result['candidate_count'], 1)
        self.assertFalse(result['target_content_read'])
        self.assertEqual(self.host.calls, 0)

    def test_round_trip_has_independent_backup_and_retains_original_identity(self):
        inode = (self.cache / 'data.bin').stat().st_ino
        operation, pin, result = self.isolate()
        self.assertEqual(result['status'], 'quarantined', result)
        self.assertFalse(self.cache.exists())
        backup = operation / 'backup/0/data.bin'
        isolated = operation / 'quarantine/0/data.bin'
        self.assertEqual(backup.read_bytes(), b'synthetic cache')
        self.assertNotEqual(backup.stat().st_ino, inode)
        self.assertEqual(isolated.stat().st_ino, inode)
        self.assertTrue((operation / 'journal/0000.prepared.json').is_file())
        self.assertTrue((operation / 'journal/0000.done.json').is_file())
        observation, observed_pin, data = self.observe(operation, pin)
        self.assertEqual(data['isolated_roots'], 1)
        restored = cleanup.restore(c, observation, observed_pin, self.root / 'restored', True, True, self.host)
        self.assertEqual(restored['status'], 'restored', restored)
        self.assertEqual((self.cache / 'data.bin').stat().st_ino, inode)
        self.assertTrue(backup.is_file())
        self.assertFalse((operation / 'quarantine/0').exists())
        self.assertNotIn(str(self.cache), c.encode(result).decode())

    def test_preflight_budgets_entire_set_before_creating_backup_or_output(self):
        with patch.object(cleanup, 'MAX_BYTES', 4):
            with self.assertRaisesRegex(c.SetupError, 'BUDGET'):
                self.make_plan()
        self.assertFalse((self.root / 'plan').exists())
        self.assertTrue((self.cache / 'data.bin').is_file())

    def test_category_selection_is_separate_from_cache_default(self):
        login = self.config / '.credentials.json'
        login.write_bytes(b'{"fixture":true}')
        request = copy.deepcopy(self.request)
        request['roots'] = [{'kind': 'cli-login', 'path': str(login)}]
        with self.assertRaisesRegex(c.SetupError, 'CATEGORY_NOT_SELECTED'):
            self.make_plan(request)
        folder, pin = self.make_plan(request, allowed=['login'])
        self.assertTrue(folder.is_dir())
        self.assertEqual(len(pin), 64)

    def test_symlink_hardlink_special_file_and_git_are_rejected(self):
        path = self.cache / 'bad'
        path.symlink_to(self.other / 'other.bin')
        with self.assertRaisesRegex(c.SetupError, 'LINK'):
            self.make_plan()
        path.unlink()
        os.link(self.other / 'other.bin', path)
        with self.assertRaisesRegex(c.SetupError, 'HARDLINK'):
            self.make_plan()
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(c.SetupError, 'SPECIAL'):
            self.make_plan()
        path.unlink()
        (self.cache / '.git').mkdir()
        with self.assertRaisesRegex(c.SetupError, 'SOURCE_OR_CODEX'):
            self.make_plan()

    def test_unknown_root_and_protected_overlap_are_rejected(self):
        request = copy.deepcopy(self.request)
        request['roots'][0]['path'] = str(self.other)
        with self.assertRaisesRegex(c.SetupError, 'OUTSIDE_TYPED_SCOPE'):
            self.make_plan(request)
        request = copy.deepcopy(self.request)
        request['protected'] = [str(self.cache / 'data.bin')]
        with self.assertRaisesRegex(c.SetupError, 'PROTECTED_PATH'):
            self.make_plan(request)

    def test_changed_source_after_review_and_wrong_pin_do_not_move(self):
        folder, pin = self.make_plan()
        with self.assertRaisesRegex(c.SetupError, 'DOCUMENT_CHANGED'):
            cleanup.quarantine(c, folder, '0' * 64, self.root / 'operation', True, True, self.host)
        (self.cache / 'data.bin').write_bytes(b'later customer edit')
        with self.assertRaisesRegex(c.SetupError, 'SOURCE_CHANGED'):
            cleanup.quarantine(c, folder, pin, self.root / 'operation', True, True, self.host)
        self.assertFalse((self.root / 'operation').exists())
        self.assertEqual((self.cache / 'data.bin').read_bytes(), b'later customer edit')

    def test_exact_write_permission_and_live_stopped_writer_are_required(self):
        folder, pin = self.make_plan()
        with self.assertRaisesRegex(c.SetupError, 'CURRENT_WRITE'):
            cleanup.quarantine(c, folder, pin, self.root / 'operation', False, True, self.host)
        self.host.running = True
        with self.assertRaisesRegex(c.SetupError, 'WRITER_RUNNING'):
            cleanup.quarantine(c, folder, pin, self.root / 'operation', True, True, self.host)
        self.assertTrue(self.cache.exists())

    def test_partial_multi_root_failure_recovers_only_observed_moved_roots(self):
        request = copy.deepcopy(self.request)
        request['roots'].append({'kind': 'desktop-cache', 'path': str(self.other)})
        count = [0]
        def mover(a, b):
            count[0] += 1
            if count[0] == 2:
                raise OSError('synthetic second rename failure')
            os.rename(a, b)
        operation, pin, result = self.isolate(request, mover)
        self.assertEqual(result['exit_code'], 2)
        self.assertEqual(result['completed_roots'], 1)
        self.assertFalse(self.cache.exists())
        self.assertTrue(self.other.exists())
        observation, observed_pin, data = self.observe(operation, pin)
        self.assertEqual((data['isolated_roots'], data['original_present_roots']), (1, 1))
        restored = cleanup.restore(c, observation, observed_pin, self.root / 'restore', True, True, self.host)
        self.assertEqual(restored['restored_roots'], 1)
        self.assertTrue(self.cache.exists())

    def test_rename_happened_then_error_is_not_replayed_as_no_change(self):
        def uncertain(a, b):
            os.rename(a, b)
            raise OSError('synthetic lost response')
        operation, pin, result = self.isolate(mover=uncertain)
        self.assertEqual(result['completed_roots'], 0)
        self.assertEqual(result['attempted_roots'], 1)
        self.assertEqual(result['changes_state'], 'reconcile_required')
        observation, observed_pin, data = self.observe(operation, pin)
        self.assertEqual(data['isolated_roots'], 1)
        restored = cleanup.restore(c, observation, observed_pin, self.root / 'restore', True, True, self.host)
        self.assertEqual(restored['status'], 'restored')

    def test_restoration_refuses_original_new_data_and_isolated_edits(self):
        operation, pin, _ = self.isolate()
        observation, observed_pin, _ = self.observe(operation, pin)
        self.cache.mkdir()
        (self.cache / 'new.bin').write_bytes(b'new customer data')
        with self.assertRaisesRegex(c.SetupError, 'OBSERVATION_CHANGED'):
            cleanup.restore(c, observation, observed_pin, self.root / 'restore', True, True, self.host)
        self.assertEqual((self.cache / 'new.bin').read_bytes(), b'new customer data')
        (self.cache / 'new.bin').unlink()
        self.cache.rmdir()
        (operation / 'quarantine/0/data.bin').write_bytes(b'changed after isolation')
        _, _, result = self.observe(operation, pin, 'changed')
        self.assertEqual(result['conflict_roots'], 1)

    def test_backup_corruption_blocks_restore_and_no_permanent_purge_exists(self):
        operation, pin, _ = self.isolate()
        (operation / 'backup/0/data.bin').write_bytes(b'corrupted')
        observation, observed_pin, result = self.observe(operation, pin)
        self.assertEqual(result['conflict_roots'], 1)
        with self.assertRaisesRegex(c.SetupError, 'RESTORE_CONFLICT'):
            cleanup.restore(c, observation, observed_pin, self.root / 'restore', True, True, self.host)
        self.assertNotIn('cleanup-purge', cleanup.COMMANDS)

    def test_prepared_journal_failure_keeps_roots_and_backs_up_before_move(self):
        original = cleanup._write
        def fail_prepared(context, p, value, **kwargs):
            if p.name.endswith('.prepared.json'):
                raise OSError('synthetic durable journal failure')
            return original(context, p, value, **kwargs)
        with patch.object(cleanup, '_write', side_effect=fail_prepared):
            operation, pin, result = self.isolate()
        self.assertEqual(result['attempted_roots'], 0)
        self.assertEqual(result['exit_code'], 2)
        self.assertTrue((operation / 'backup/0/data.bin').is_file())
        self.assertTrue((self.cache / 'data.bin').is_file())
        _, _, data = self.observe(operation, pin)
        self.assertEqual(data['original_present_roots'], 1)

    def test_binding_and_expired_plan_stop_new_moves_but_not_recovery(self):
        folder, pin = self.make_plan()
        self.host.changed_binding = True
        with self.assertRaisesRegex(c.SetupError, 'BINDING_CHANGED'):
            cleanup.quarantine(c, folder, pin, self.root / 'operation', True, True, self.host)
        self.host.changed_binding = False
        with patch.object(c, 'now', return_value='2099-01-01T00:00:00+00:00'):
            with self.assertRaisesRegex(c.SetupError, 'PLAN_EXPIRED'):
                cleanup.quarantine(c, folder, pin, self.root / 'operation', True, True, self.host)

    def test_symlink_destination_is_not_treated_as_absent_original(self):
        operation, pin, _ = self.isolate()
        self.cache.symlink_to(self.root / 'missing-target', target_is_directory=True)
        with self.assertRaises(c.SetupError):
            self.observe(operation, pin)

    def test_observation_output_cannot_mutate_quarantine(self):
        operation, pin, _ = self.isolate()
        destination = operation / 'quarantine/0/new-observation'
        with self.assertRaisesRegex(c.SetupError, 'OUTPUT_OVERLAP'):
            cleanup.reconcile(c, operation, pin, destination, self.host)
        self.assertFalse(destination.exists())

    def test_restore_interruption_can_reconcile_then_finish_remaining_only(self):
        request = copy.deepcopy(self.request)
        request['roots'].append({'kind': 'desktop-cache', 'path': str(self.other)})
        operation, pin, _ = self.isolate(request)
        observation, observed_pin, _ = self.observe(operation, pin)
        def uncertain(a, b):
            os.rename(a, b)
            raise OSError('synthetic interrupted restore')
        result = cleanup.restore(c, observation, observed_pin, self.root / 'restore-first',
                                 True, True, self.host, uncertain)
        self.assertEqual(result['exit_code'], 2)
        self.assertTrue(self.cache.exists())
        self.assertFalse(self.other.exists())
        fresh, fresh_pin, data = self.observe(operation, pin, 'fresh-observation')
        self.assertEqual((data['isolated_roots'], data['original_present_roots']), (1, 1))
        result = cleanup.restore(c, fresh, fresh_pin, self.root / 'restore-second', True, True, self.host)
        self.assertEqual(result['restored_roots'], 1)
        self.assertTrue(self.other.exists())

    def test_restore_output_overlap_is_rejected_before_creating_anything(self):
        request = copy.deepcopy(self.request)
        request['roots'].append({'kind': 'desktop-cache', 'path': str(self.other)})
        count = [0]
        def fail_second(a, b):
            count[0] += 1
            if count[0] == 2:
                raise OSError('second root untouched')
            os.rename(a, b)
        operation, pin, _ = self.isolate(request, fail_second)
        observation, observed_pin, _ = self.observe(operation, pin)
        destination = self.other / 'unexpected-artifact'
        with self.assertRaisesRegex(c.SetupError, 'OUTPUT_OVERLAP'):
            cleanup.restore(c, observation, observed_pin, destination, True, True, self.host)
        self.assertFalse(destination.exists())

    def test_replaced_original_parent_never_becomes_a_new_restore_target(self):
        operation, pin, _ = self.isolate()
        old_observation, old_pin, _ = self.observe(operation, pin)
        self.config.rename(self.root / 'preserved-old-config')
        self.config.mkdir(mode=0o700)
        fresh, fresh_pin, result = self.observe(operation, pin, 'parent-conflict')
        self.assertEqual(result['conflict_roots'], 1)
        record = c.load_json((fresh / 'observation.private.json').read_bytes())
        self.assertEqual(record['roots'][0]['state'], 'parent_conflict')
        self.assertIsNone(record['roots'][0]['original_snapshot'])
        for folder, digest in [(old_observation, old_pin), (fresh, fresh_pin)]:
            with self.assertRaises(c.SetupError):
                cleanup.restore(c, folder, digest, self.root / 'restore', True, True, self.host)
        self.assertFalse(self.cache.exists())
        self.assertTrue((operation / 'quarantine/0/data.bin').is_file())

    def test_directory_enumeration_stops_at_first_over_budget_entry(self):
        for index in range(8):
            (self.cache / ('extra-%d' % index)).write_bytes(b'x')
        original = os.scandir
        calls = [0]
        class Counted:
            def __init__(self, path):
                self.iterator = original(path)
            def __enter__(self):
                return self
            def __exit__(self, *unused):
                self.iterator.close()
            def __iter__(self):
                return self
            def __next__(self):
                calls[0] += 1
                if calls[0] > 3:
                    raise AssertionError('enumeration continued after the first overflowing entry')
                return next(self.iterator)
        with patch.object(cleanup, 'MAX_ITEMS', 3), patch.object(cleanup.os, 'scandir', side_effect=Counted):
            with self.assertRaisesRegex(c.SetupError, 'BUDGET_EXCEEDED'):
                self.make_plan()
        self.assertEqual(calls[0], 3)  # root + 2 allowed children, then one overflow witness
        self.assertFalse((self.root / 'plan').exists())


class UnsupportedCleanup(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Mismatch fixture requires a non-Windows runtime')
    def test_windows_platform_name_cannot_activate_native_adapter_on_posix(self):
        with patch.object(cleanup.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(c.SetupError, 'PLATFORM_UNSUPPORTED'):
                cleanup.NativeHost().supported(c)

    @unittest.skipUnless(os.name == 'posix', 'Native Mac scope adapter is POSIX')
    def test_native_scope_rejects_arbitrary_labeled_cache_context(self):
        with patch.object(cleanup.platform, 'system', return_value='Darwin'):
            with self.assertRaisesRegex(c.SetupError, 'CONFIG_ROOT_MISMATCH'):
                cleanup.NativeHost().validate_scope(c, {'config_root': '/unrelated/claimed-Claude'})


if __name__ == '__main__':
    unittest.main()
