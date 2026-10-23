"""Only temporary synthetic files. No installed clients, network or OS settings."""
import argparse
import ctypes
import getpass
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c
import config_recovery as recovery

NATIVE = platform.system() in ('Darwin', 'Windows')
BEFORE = b'{"mode":"rule","rules":["MATCH,DIRECT"]}\n'
AFTER = b'{"mode":"rule","rules":["DOMAIN,example.com,REJECT","MATCH,DIRECT"]}\n'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-config-recovery-')
        # macOS /var is a system symlink; callers must select the real path.
        self.root = Path(self.temp.name).resolve()
        if os.name != 'nt':
            self.root.chmod(0o700)
        self.target = self.root / 'customer.json'
        self.candidate = self.root / 'candidate.json'
        self.target.write_bytes(BEFORE)
        self.candidate.write_bytes(AFTER)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, name='plan'):
        dest = self.root / name
        result = recovery.prepare(c, self.target, self.candidate, dest)
        self.assertFalse(result['config_file_changed'])
        self.assertEqual(self.target.read_bytes(), BEFORE)
        return dest, result['plan_sha256']

    def applied(self):
        folder, pin = self.plan()
        dest = self.root / 'apply'
        result = recovery.apply(c, folder, pin, True, True, dest)
        self.assertEqual(result['status'], '已完成', result)
        self.assertTrue(result['config_file_changed'])
        self.assertTrue(result['system_settings_changed'])
        self.assertEqual(self.target.read_bytes(), AFTER)
        return dest, result['receipt_sha256'], result

    def assert_status_schema(self, directory):
        report = c.load_json((directory / 'report.json').read_bytes())
        for row in report['rows']:
            self.assertIn(row['status'], ('已完成', '未完成'))
            if row['status'] == '未完成':
                self.assertTrue(row['reason'])
                self.assertTrue(row['next_step'])
        # Customer summary must not contain paths, raw rules or credentials.
        for filename in ('report.json', 'report.md', 'report.html'):
            public = (directory / filename).read_text(encoding='utf-8')
            self.assertNotIn(str(self.target), public)
            self.assertNotIn('example.com', public)
            self.assertNotIn('MATCH,DIRECT', public)

    def test_plan_private_diff_pins_bytes_without_target_writes(self):
        original = recovery._snapshot(c, self.target)[1]
        folder, pin = self.plan()
        self.assertEqual(recovery._snapshot(c, self.target)[1], original)
        self.assertEqual(c.sha((folder / 'plan.json').read_bytes()), pin)
        self.assertIn('example.com', (folder / 'diff.private.txt').read_text(encoding='utf-8'))
        self.assertFalse(c.load_json((folder / 'plan.json').read_bytes())['authorization_saved'])
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((folder / 'original.private.bin').stat().st_mode), 0o600)
        else:
            security = recovery._win_security(folder)
            self.assertIn('D:P', security)
            self.assertNotIn(';;;WD)', security)
        self.assert_status_schema(folder)

    def test_parser_rejects_nontext_database_and_invalid_candidate(self):
        for data in (b'SQLite format 3\x00anything', b'\x80\x80', b'{"a":1,"a":2}', b'not JSON'):
            self.candidate.write_bytes(data)
            with self.assertRaises(c.SetupError):
                recovery.prepare(c, self.target, self.candidate, self.root / 'rejected')
            self.assertFalse((self.root / 'rejected').exists())
            self.assertEqual(self.target.read_bytes(), BEFORE)
        self.candidate.write_bytes(AFTER)
        database = self.root / 'profile.db'
        database.write_bytes(BEFORE)
        with self.assertRaisesRegex(c.SetupError, 'TEXT_CONFIG'):
            recovery.prepare(c, database, self.candidate, self.root / 'bad-db')

    def test_symlinks_and_hardlinks_are_rejected(self):
        hard = self.root / 'hard.json'
        try:
            os.link(self.target, hard)
        except OSError:
            self.skipTest('filesystem does not support hard links')
        with self.assertRaisesRegex(c.SetupError, 'SINGLE_REGULAR'):
            recovery.prepare(c, self.target, self.candidate, self.root / 'bad-hard')
        hard.unlink()
        symbolic = self.root / 'symbolic.json'
        try:
            symbolic.symlink_to(self.target)
        except OSError:
            return  # Native Windows CI may lack symlink privilege.
        with self.assertRaisesRegex(c.SetupError, 'LINK_OR_REPARSE'):
            recovery.prepare(c, symbolic, self.candidate, self.root / 'bad-link')
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(c.SetupError, 'LINK_OR_REPARSE'):
            recovery.prepare(c, alias / 'customer.json', self.candidate, self.root / 'bad-parent')

    def test_path_and_managed_store_rejections(self):
        with self.assertRaisesRegex(c.SetupError, 'PATH_INVALID'):
            recovery.prepare(c, str(self.root / 'sub' / '..' / 'customer.json'), self.candidate, self.root / 'bad')
        managed = self.root / 'Library' / 'Group Containers' / 'app'
        managed.mkdir(parents=True)
        (managed / 'profile.conf').write_bytes(b'[General]\nipv6=false\n')
        with self.assertRaisesRegex(c.SetupError, 'MANAGED_STORE'):
            recovery.prepare(c, managed / 'profile.conf', self.candidate, self.root / 'bad-managed')

    def test_already_existing_output_refused(self):
        dest = self.root / 'exists'
        dest.mkdir(mode=0o700)
        (dest / 'keep').write_text('customer')
        with self.assertRaises(c.SetupError):
            recovery.prepare(c, self.target, self.candidate, dest)
        self.assertEqual((dest / 'keep').read_text(encoding='utf-8'), 'customer')

    def test_cli_has_explicit_write_flags(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest='command', required=True)
        recovery.register_commands(sub)
        args = parser.parse_args(['recovery-apply', '--plan', 'x', '--plan-sha256', 'a' * 64, '--out', 'y'])
        self.assertFalse(args.allow_write)
        self.assertFalse(args.writer_stopped)
        with self.assertRaisesRegex(c.SetupError, 'CURRENT_WRITE_AND_STOPPED'):
            recovery.run(c, args)

    @unittest.skipUnless(NATIVE, 'writes require actual macOS or Windows; Linux has no native adapter')
    def test_roundtrip_then_repeated_rollback_refuses_overwrite(self):
        dest, receipt_pin, result = self.applied()
        check = recovery.check(c, dest, receipt_pin, self.root / 'check')
        self.assertTrue(check['safe_automatic_rollback_available'])
        self.assertFalse(check['config_file_changed'])
        undo = recovery.rollback(c, dest, receipt_pin, True, True, self.root / 'rollback')
        self.assertEqual(undo['status'], '已完成', undo)
        self.assertEqual(self.target.read_bytes(), BEFORE)
        with self.assertRaisesRegex(c.SetupError, 'ROLLBACK_CONFLICT'):
            recovery.rollback(c, dest, receipt_pin, True, True, self.root / 'second-rollback')
        self.assert_status_schema(self.root / 'rollback')

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_same_plan_cannot_apply_twice(self):
        folder, pin = self.plan()
        first = recovery.apply(c, folder, pin, True, True, self.root / 'first')
        self.assertEqual(first['status'], '已完成')
        with self.assertRaisesRegex(c.SetupError, 'TARGET_CONFLICT'):
            recovery.apply(c, folder, pin, True, True, self.root / 'second')
        self.assertEqual(self.target.read_bytes(), AFTER)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_yaml_and_shadowrocket_text_roundtrips(self):
        cases = [('.yaml', b'mode: rule\nrules:\n  - MATCH,DIRECT\n', b'mode: rule\nrules:\n  - DOMAIN,example.com,REJECT\n  - MATCH,DIRECT\n'),
                 ('.conf', b'[General]\nipv6=false\n[Rule]\nFINAL,DIRECT\n', b'[General]\nipv6=false\n[Rule]\nDOMAIN,example.com,REJECT\nFINAL,DIRECT\n')]
        for index, (ext, before, after) in enumerate(cases):
            target = self.root / ('sample' + ext)
            candidate = self.root / ('sample-candidate' + ext)
            target.write_bytes(before)
            candidate.write_bytes(after)
            plan = recovery.prepare(c, target, candidate, self.root / ('text-plan' + str(index)))
            applied = recovery.apply(c, self.root / ('text-plan' + str(index)), plan['plan_sha256'], True, True, self.root / ('text-apply' + str(index)))
            self.assertEqual(applied['status'], '已完成', applied)
            self.assertEqual(target.read_bytes(), after)
            undone = recovery.rollback(c, self.root / ('text-apply' + str(index)), applied['receipt_sha256'], True, True, self.root / ('text-undo' + str(index)))
            self.assertEqual(undone['status'], '已完成', undone)
            self.assertEqual(target.read_bytes(), before)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_missing_current_authorization_never_writes(self):
        folder, pin = self.plan()
        for allow, stopped in ((False, False), (True, False), (False, True)):
            with self.assertRaisesRegex(c.SetupError, 'CURRENT_WRITE_AND_STOPPED'):
                recovery.apply(c, folder, pin, allow, stopped, self.root / 'never')
        self.assertEqual(self.target.read_bytes(), BEFORE)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_pin_platform_and_machine_changes_rejected(self):
        folder, pin = self.plan()
        for wrong in ('0' * 64, 'not-a-pin'):
            with self.assertRaisesRegex(c.SetupError, 'PIN_MISMATCH'):
                recovery.apply(c, folder, wrong, True, True, self.root / 'bad-pin')
        original_binding = recovery._binding()
        fake = dict(original_binding, machine_user_sha256='f' * 64)
        with patch.object(recovery, '_binding', return_value=fake):
            with self.assertRaisesRegex(c.SetupError, 'BINDING_MISMATCH'):
                recovery.apply(c, folder, pin, True, True, self.root / 'bad-host')
        self.assertEqual(self.target.read_bytes(), BEFORE)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_changed_target_and_tampered_backup_are_rejected(self):
        folder, pin = self.plan()
        self.target.write_bytes(b'{"customer":"newer"}\n')
        with self.assertRaisesRegex(c.SetupError, 'TARGET_CONFLICT'):
            recovery.apply(c, folder, pin, True, True, self.root / 'never')
        self.target.write_bytes(BEFORE)
        # Even the same bytes written later are a different reviewed identity.
        with self.assertRaisesRegex(c.SetupError, 'TARGET_CONFLICT'):
            recovery.apply(c, folder, pin, True, True, self.root / 'still-never')
        (folder / 'original.private.bin').write_bytes(b'{}')
        with self.assertRaisesRegex(c.SetupError, 'BACKUP_INTEGRITY'):
            recovery.apply(c, folder, pin, True, True, self.root / 'tampered')

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_rollback_protects_later_content_identity_and_metadata(self):
        dest, pin, _ = self.applied()
        self.target.write_bytes(b'{"customer":"later"}\n')
        check = recovery.check(c, dest, pin, self.root / 'conflict-check')
        self.assertEqual(check['status'], '未完成')
        self.assertFalse(check['safe_automatic_rollback_available'])
        self.assert_status_schema(self.root / 'conflict-check')
        with self.assertRaisesRegex(c.SetupError, 'ROLLBACK_CONFLICT'):
            recovery.rollback(c, dest, pin, True, True, self.root / 'unsafe')
        self.assertIn(b'later', self.target.read_bytes())
        self.target.write_bytes(AFTER)
        with self.assertRaisesRegex(c.SetupError, 'ROLLBACK_CONFLICT'):
            recovery.rollback(c, dest, pin, True, True, self.root / 'same-bytes-new-write')

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_caller_cannot_reuse_intent_pin_to_trust_a_final_receipt(self):
        dest, pin, result = self.applied()
        check = recovery.check(c, dest, result['intent_sha256'], self.root / 'intent-only')
        self.assertEqual(check['status'], '未完成')
        self.assertFalse(check['safe_automatic_rollback_available'])
        with self.assertRaisesRegex(c.SetupError, 'ROLLBACK_CONFLICT'):
            recovery.rollback(c, dest, result['intent_sha256'], True, True, self.root / 'no-final-pin')
        self.assertEqual(self.target.read_bytes(), AFTER)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_tampered_final_receipt_cannot_be_resealed_locally(self):
        dest, pin, _ = self.applied()
        final = c.load_json((dest / 'receipt.private.json').read_bytes())
        final['created_at'] = 'tampered'
        data = c.encode(final)
        (dest / 'receipt.private.json').write_bytes(data)
        (dest / 'receipt.sha256').write_text(c.sha(data) + '\n')
        with self.assertRaisesRegex(c.SetupError, 'RECEIPT_INTEGRITY'):
            recovery.rollback(c, dest, pin, True, True, self.root / 'tampered-final')

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_changed_while_staging_never_commits(self):
        folder, pin = self.plan()
        real_stage = recovery._stage
        def racing_stage(*args):
            result = real_stage(*args)
            self.target.write_bytes(b'{"customer":"concurrent"}\n')
            return result
        with patch.object(recovery, '_stage', side_effect=racing_stage):
            result = recovery.apply(c, folder, pin, True, True, self.root / 'race')
        self.assertFalse(result['write_attempted'])
        self.assertFalse(result['config_file_changed'])
        self.assertEqual(result['status'], '未完成')
        self.assertIn(b'concurrent', self.target.read_bytes())

    @unittest.skipUnless(NATIVE and os.name != 'nt', 'actual POSIX directory descriptor safety')
    def test_parent_replaced_at_commit_is_not_the_planned_directory(self):
        original_parent = self.root / 'target-parent'
        original_parent.mkdir(mode=0o700)
        self.target = original_parent / 'customer.json'
        self.target.write_bytes(BEFORE)
        folder, pin = self.plan()
        real_replace = recovery._replace
        def swapped_parent(*args):
            original_parent.rename(self.root / 'moved-parent')
            original_parent.mkdir(mode=0o700)
            self.target.write_bytes(b'{"customer":"other directory"}\n')
            return real_replace(*args)
        with patch.object(recovery, '_replace', side_effect=swapped_parent):
            result = recovery.apply(c, folder, pin, True, True, self.root / 'parent-race')
        self.assertEqual(result['status'], '未完成')
        self.assertEqual(result['reason_code'], 'RECOVERY_PARENT_CHANGED')
        self.assertEqual(self.target.read_bytes(), b'{"customer":"other directory"}\n')
        self.assertEqual((self.root / 'moved-parent/customer.json').read_bytes(), BEFORE)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_replace_failure_reports_observed_state_and_keeps_backup(self):
        folder, pin = self.plan()
        dest = self.root / 'replace-failure'
        with patch.object(recovery, '_replace', side_effect=OSError('synthetic')):
            result = recovery.apply(c, folder, pin, True, True, dest)
        self.assertEqual(result['status'], '未完成')
        self.assertTrue(result['write_attempted'])
        self.assertFalse(result['config_file_changed'])
        self.assertEqual(self.target.read_bytes(), BEFORE)
        self.assertEqual((dest / 'original.private.bin').read_bytes(), BEFORE)
        check = recovery.check(c, dest, result['receipt_sha256'], self.root / 'replace-check')
        self.assertEqual(check['recovery_state'], 'original_unchanged')

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_replace_then_error_does_not_claim_unchanged(self):
        folder, pin = self.plan()
        real_replace = recovery._replace
        def committed_then_error(*args):
            real_replace(*args)
            raise OSError('synthetic-after-rename')
        with patch.object(recovery, '_replace', side_effect=committed_then_error):
            result = recovery.apply(c, folder, pin, True, True, self.root / 'uncertain')
        self.assertTrue(result['config_file_changed'])
        self.assertTrue(result['system_settings_changed'])
        self.assertEqual(result['status'], '未完成')
        self.assertEqual(self.target.read_bytes(), AFTER)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_final_receipt_failure_retains_intent_and_never_enables_undo(self):
        folder, pin = self.plan()
        dest = self.root / 'receipt-failure'
        real_write = recovery._write
        def failed_receipt(context, path, data):
            if path.name == 'receipt.private.json':
                raise c.SetupError('SYNTHETIC_DISK_FULL')
            return real_write(context, path, data)
        with patch.object(recovery, '_write', side_effect=failed_receipt):
            result = recovery.apply(c, folder, pin, True, True, dest)
        self.assertEqual(result['status'], '未完成')
        self.assertTrue(result['config_file_changed'])
        self.assertFalse(result['receipt_complete'])
        self.assertEqual(self.target.read_bytes(), AFTER)
        self.assertEqual((dest / 'original.private.bin').read_bytes(), BEFORE)
        check = recovery.check(c, dest, result['intent_sha256'], self.root / 'interrupted-check')
        self.assertEqual(check['recovery_state'], 'candidate_observed_receipt_incomplete')
        with self.assertRaisesRegex(c.SetupError, 'ROLLBACK_CONFLICT'):
            recovery.rollback(c, dest, result['intent_sha256'], True, True, self.root / 'unsafe-undo')

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_report_failure_after_commit_reports_real_write(self):
        folder, pin = self.plan()
        import readiness_lifecycle
        with patch.object(readiness_lifecycle, 'save_report', side_effect=c.SetupError('SYNTHETIC_REPORT_IO')):
            result = recovery.apply(c, folder, pin, True, True, self.root / 'no-report')
        self.assertTrue(result['config_file_changed'])
        self.assertTrue(result['system_changes_performed'])
        self.assertFalse(result['report_written'])
        self.assertFalse(result['required_checks_completed'])
        self.assertEqual(result['status'], '未完成')
        self.assertEqual(self.target.read_bytes(), AFTER)

    @unittest.skipUnless(NATIVE, 'native writes only')
    def test_lock_conflict_does_not_remove_other_operations_lock(self):
        folder, pin = self.plan()
        name = '.claude-recovery-' + recovery.hashlib.sha256(str(self.target).encode()).hexdigest()[:24] + '.lock'
        lock = self.root / name
        lock.write_bytes(b'another-operation')
        result = recovery.apply(c, folder, pin, True, True, self.root / 'locked')
        self.assertEqual(result['status'], '未完成')
        self.assertEqual(lock.read_bytes(), b'another-operation')
        self.assertEqual(self.target.read_bytes(), BEFORE)

    @unittest.skipUnless(NATIVE and os.name != 'nt', 'native POSIX metadata test')
    def test_mode_and_extended_attributes_survive_apply_and_restore(self):
        self.target.chmod(0o640)
        attr = 'com.example.synthetic-recovery' if platform.system() == 'Darwin' else 'user.synthetic-recovery'
        if hasattr(os, 'setxattr'):
            os.setxattr(self.target, attr, b'synthetic-metadata')
        elif platform.system() == 'Darwin':
            libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
            libc.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
            libc.setxattr.restype = ctypes.c_int
            self.assertEqual(libc.setxattr(os.fsencode(self.target), attr.encode(), b'synthetic-metadata', 18, 0, 1), 0)
        before_meta = recovery._metadata(self.target)
        self.assertEqual(before_meta['xattrs'][attr], b'synthetic-metadata'.hex())
        dest, pin, _ = self.applied()
        self.assertEqual(recovery._metadata(self.target), before_meta)
        recovery.rollback(c, dest, pin, True, True, self.root / 'restore-metadata')
        self.assertEqual(recovery._metadata(self.target), before_meta)

    @unittest.skipUnless(platform.system() == 'Darwin', 'actual Darwin ACL/fcopyfile test')
    def test_mac_extended_acl_preserved_on_synthetic_file(self):
        subprocess.run(['/bin/chmod', '+a', 'user:' + getpass.getuser() + ' allow read', str(self.target)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        acl = recovery._metadata(self.target)['acl']
        self.assertIsNotNone(acl)
        dest, pin, _ = self.applied()
        self.assertEqual(recovery._metadata(self.target)['acl'], acl)
        undone = recovery.rollback(c, dest, pin, True, True, self.root / 'acl-restore')
        self.assertEqual(undone['status'], '已完成', undone)
        self.assertEqual(recovery._metadata(self.target)['acl'], acl)

    @unittest.skipUnless(platform.system() == 'Darwin', 'actual Darwin backup privacy boundary')
    def test_mac_extended_acl_on_private_artifacts_is_not_treated_as_mode_700(self):
        folder, pin = self.plan()
        subprocess.run(['/bin/chmod', '+a', 'everyone allow list,search', str(folder)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        with self.assertRaisesRegex(c.SetupError, 'PRIVATE_ACL_REQUIRED'):
            recovery.apply(c, folder, pin, True, True, self.root / 'acl-exposed')
        self.assertEqual(self.target.read_bytes(), BEFORE)

    @unittest.skipUnless(os.name == 'nt', 'actual Windows ACL/ReplaceFileW test')
    def test_windows_native_security_descriptor_is_preserved(self):
        descriptor = recovery._win_security(self.target)
        dest, pin, _ = self.applied()
        self.assertEqual(recovery._win_security(self.target), descriptor)
        recovery.rollback(c, dest, pin, True, True, self.root / 'windows-restore')
        self.assertEqual(recovery._win_security(self.target), descriptor)

    @unittest.skipUnless(os.name == 'nt', 'actual Windows alternate-stream boundary')
    def test_windows_named_streams_refused_before_plan(self):
        Path(str(self.target) + ':synthetic-metadata').write_bytes(b'not a plain default stream')
        with self.assertRaisesRegex(c.SetupError, 'METADATA_UNAVAILABLE_OR_UNSUPPORTED'):
            self.plan()
        self.assertEqual(self.target.read_bytes(), BEFORE)

    @unittest.skipUnless(platform.system() == 'Linux', 'actual unsupported host check')
    def test_linux_cannot_apply_by_reusing_an_existing_plan(self):
        folder, pin = self.plan()
        with self.assertRaisesRegex(c.SetupError, 'NATIVE_MAC_OR_WINDOWS'):
            recovery.apply(c, folder, pin, True, True, self.root / 'linux-write')
        self.assertEqual(self.target.read_bytes(), BEFORE)


if __name__ == '__main__':
    unittest.main()
