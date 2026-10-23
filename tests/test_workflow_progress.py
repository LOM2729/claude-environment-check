"""Temporary synthetic progress materials only; no user settings or network."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c
import workflow_progress as progress

TARGET_PLATFORM = 'windows' if platform.system() == 'Windows' else 'macos'
NATIVE = platform.system() in ('Darwin', 'Windows')
NOTE = '等待客户手动重启，连接恢复后重新核验 DNS 和代理'
CONFIG = b'{"mode":"rule","private":"synthetic-only-value"}\n'
SCOPE = ('用途入口：仅桌面 Claude 和 Codex。\n明确保留业务：国内视频及当前远控必须保留。\n'
         '指定节点：synthetic-node-private。\n本轮必需：核对分流、DNS 和 UDP。\n'
         '后续验收：重启、换网和故障演练待客户安排。\n待确认项：登录入口未知，不扩大范围。\n')


class WorkflowProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-workflow-progress-')
        self.root = Path(self.temp.name).resolve()
        if os.name != 'nt':
            self.root.chmod(0o700)
        self.config = self.root / 'customer.json'
        self.config.write_bytes(CONFIG)
        self.artifact = self.root / 'candidate.json'
        self.artifact.write_bytes(b'{"candidate":"synthetic"}\n')
        self.scope = self.root / '本轮 范围说明.md'
        self.scope.write_text(SCOPE, encoding='utf-8')
        self.number = 0

    def tearDown(self):
        self.temp.cleanup()

    def output(self, label):
        self.number += 1
        return self.root / (label + str(self.number))

    def save(self, **kwargs):
        folder = self.output('saved')
        options = {'mode': 'automatic', 'waiting_for': 'restart', 'artifacts': [self.artifact], 'scope_file': self.scope}
        options.update(kwargs)
        result = progress.save(c, self.config, 'customer-one', TARGET_PLATFORM, 'configure', NOTE, folder, **options)
        self.assertEqual(result['status'], '已完成', result)
        self.assertTrue(result['required_checks_completed'])
        self.assert_safety(result)
        return folder

    def resume(self, folder, **kwargs):
        out = self.output('resumed')
        options = {'config': self.config, 'checkpoint': folder, 'target_alias': 'customer-one',
                   'target_platform': TARGET_PLATFORM, 'output': out}
        options.update(kwargs)
        result = progress.resume(c, **options)
        self.assert_safety(result)
        return out, result

    def assert_safety(self, result):
        self.assertFalse(result['authorization_restored'])
        self.assertFalse(result['authorization_saved'])
        self.assertFalse(result['actions_executed'])
        self.assertFalse(result['system_settings_changed'])
        self.assertFalse(result['config_file_changed'])
        self.assertTrue(result['network_revalidation_required'])
        self.assertTrue(result['progress_only'])
        self.assertEqual(result['network_requests'], 0)

    def rows(self, folder):
        report = c.load_json((folder / 'report.json').read_bytes())
        for row in report['rows']:
            self.assertIn(row['status'], ('已完成', '未完成'))
            if row['status'] == '未完成':
                self.assertTrue(row['reason'])
                self.assertTrue(row['next_step'])
        return {row['id']: row for row in report['rows']}

    def reseal(self, folder, mutate):
        path = folder / 'checkpoint.private.json'
        record = c.load_json(path.read_bytes())
        mutate(record)
        raw = c.encode(record)
        path.write_bytes(raw)
        (folder / 'checkpoint.sha256').write_text(c.sha(raw) + '\n', encoding='ascii')

    def test_save_and_resume_are_progress_only_without_replaying_any_action(self):
        with (patch.object(c, 'run_fixed', side_effect=AssertionError('no native commands')),
              patch.object(c, 'collect', side_effect=AssertionError('no environment collection')),
              patch.object(subprocess, 'Popen', side_effect=AssertionError('no launch')),
              patch.object(progress.reports.network_checks, 'run_checks', side_effect=AssertionError('no probes'))):
            saved = self.save()
            out, result = self.resume(saved)
        self.assertEqual(result['checkpoint_matches'], NATIVE)
        self.assertEqual(self.rows(out)['fresh_review']['status'], '未完成')

    def test_roundtrip_preserves_file_bytes_and_has_utf8_private_note(self):
        before = self.config.stat()
        saved = self.save()
        out, result = self.resume(saved)
        self.assertEqual(result['status'], '已完成' if NATIVE else '未完成')
        self.assertEqual(result['checkpoint_matches'], NATIVE)
        self.assertEqual(result['stage'], 'configure')
        self.assertEqual(result['waiting_for'], 'restart')
        self.assertEqual(self.config.read_bytes(), CONFIG)
        self.assertEqual((self.config.stat().st_size, self.config.stat().st_mtime_ns), (before.st_size, before.st_mtime_ns))
        record = c.load_json((saved / 'checkpoint.private.json').read_bytes())
        self.assertEqual(record['config']['path'], str(self.config))
        self.assertEqual(record['artifacts'][0]['path'], str(self.artifact))
        self.assertEqual(record['scope'], {'path': str(self.scope), 'sha256': c.sha(SCOPE.encode('utf-8'))})
        self.assertEqual(record['kit_version'], c.VERSION)
        self.assertEqual(record['binding'], progress.storage._binding())
        self.assertEqual(record['config']['sha256'], c.sha(CONFIG))
        self.assertEqual(self.rows(out)['fresh_review']['status'], '未完成')
        self.assertFalse(self.rows(out)['fresh_review']['required'])
        for directory in (saved, out):
            note = (directory / '继续配置.md').read_text(encoding='utf-8')
            self.assertIn('客户手动重启', note)
            self.assertIn('START-HERE.md', note)
            self.assertIn('旧 dns-ready', note)
            self.assertIn('[私有材料索引](材料索引.private.md)', note)
            self.assertNotIn(str(self.root), note)
            self.assertNotIn('synthetic-only-value', note)
            self.assertNotIn('customer-one', note)
            self.assertNotIn('checkpoint.private.json', note)
            for filename in ('report.json', 'report.md', 'report.html'):
                public = (directory / filename).read_text(encoding='utf-8')
                self.assertNotIn(str(self.root), public)
                self.assertNotIn('synthetic-only-value', public)
                self.assertNotIn('customer-one', public)
                self.assertNotIn('synthetic-node-private', public)
                self.assertNotIn(SCOPE, public)
            index = (directory / '材料索引.private.md').read_text(encoding='utf-8')
            self.assertIn('1. 本轮范围说明', index)
            self.assertIn(str(self.scope), index)
            self.assertIn(str(self.artifact), index)
            self.assertNotIn(str(self.config), index)
            self.assertNotIn('synthetic-only-value', index)
            self.assertNotIn('synthetic-node-private', index)

    def test_cli_never_has_write_network_or_launch_switches(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest='command', required=True)
        progress.register_commands(sub)
        out = self.output('cli')
        args = parser.parse_args(['workflow-save', '--config', str(self.config), '--scope-file', str(self.scope), '--target-alias', 'customer-one',
                                  '--platform', TARGET_PLATFORM, '--stage', 'prepare', '--next-step', '核对当前文件和节点', '--out', str(out)])
        self.assertFalse(hasattr(args, 'allow_write'))
        self.assertFalse(hasattr(args, 'allow_network'))
        self.assertFalse(hasattr(args, 'launch'))
        result = progress.run(c, args)
        self.assert_safety(result)
        self.assertEqual(result['status'], '已完成')

    def test_config_changed_missing_or_different_path_is_incomplete(self):
        saved = self.save()
        self.config.write_bytes(b'{"changed":"synthetic"}')
        out, result = self.resume(saved)
        self.assertEqual(result['status'], '未完成')
        self.assertEqual(self.rows(out)['config']['status'], '未完成')
        self.assertIn('不要自动覆盖', self.rows(out)['config']['next_step'])
        self.config.unlink()
        out, result = self.resume(saved)
        self.assertFalse(result['required_checks_completed'])
        self.assertEqual(self.rows(out)['config']['status'], '未完成')
        other = self.root / 'same-content-other-path.json'
        other.write_bytes(CONFIG)
        out, result = self.resume(saved, config=other)
        self.assertEqual(self.rows(out)['config']['status'], '未完成')
        self.assertEqual(other.read_bytes(), CONFIG)

    def test_artifact_changed_or_missing_is_incomplete(self):
        saved = self.save()
        self.artifact.write_bytes(b'{"changed":"synthetic"}')
        out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['artifacts']['status'], '未完成')
        self.assertFalse(result['checkpoint_matches'])
        self.artifact.unlink()
        out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['artifacts']['status'], '未完成')
        self.assertFalse(result['required_checks_completed'])

    def test_machine_target_platform_and_version_drift_need_new_review(self):
        saved = self.save()
        options = [{'target_alias': 'different'}, {'target_platform': 'macos' if TARGET_PLATFORM == 'windows' else 'windows'}]
        for kwargs in options:
            out, result = self.resume(saved, **kwargs)
            self.assertEqual(self.rows(out)['target']['status'], '未完成')
            self.assertEqual(result['status'], '未完成')
        binding = dict(progress.storage._binding(), machine_user_sha256='0' * 64)
        with patch.object(progress.storage, '_binding', return_value=binding):
            out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['machine']['status'], '未完成')
        self.assertFalse(result['checkpoint_matches'])
        with patch.object(c, 'VERSION', 'different-synthetic-kit'):
            out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['kit']['status'], '未完成')
        self.assertFalse(result['required_checks_completed'])

    def test_foreign_machine_does_not_follow_historical_artifact_paths(self):
        saved = self.save()
        real_file = progress._file
        reads = []
        def observed_file(context, path):
            reads.append(str(path))
            return real_file(context, path)
        binding = dict(progress.storage._binding(), machine_user_sha256='f' * 64)
        with patch.object(progress.storage, '_binding', return_value=binding), patch.object(progress, '_file', side_effect=observed_file):
            out, result = self.resume(saved)
        self.assertNotIn(str(self.artifact), reads)
        self.assertIn(str(self.config), reads)
        self.assertEqual(self.rows(out)['artifacts']['status'], '未完成')
        self.assertIn('未读取历史材料', self.rows(out)['artifacts']['reason'])

    def test_corrupt_missing_or_resealed_authorization_records_are_incomplete(self):
        saved = self.save()
        path = saved / 'checkpoint.private.json'
        path.write_bytes(b'{"corrupt":true}')
        out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['checkpoint']['status'], '未完成')
        self.assertFalse(result['checkpoint_matches'])
        self.assertNotIn(NOTE, (out / '继续配置.md').read_text(encoding='utf-8'))
        path.unlink()
        out, result = self.resume(saved)
        self.assertEqual(result['status'], '未完成')
        for key, value in (('authorization_saved', True), ('authorization_restored', True),
                           ('actions_executed', True), ('allow_write', True), ('allow_network', True)):
            saved = self.save()
            self.reseal(saved, lambda record: record.update({key: value}))
            out, result = self.resume(saved)
            self.assertEqual(self.rows(out)['checkpoint']['status'], '未完成')
            self.assertFalse(result['required_checks_completed'])

    def test_old_dns_ready_artifact_never_becomes_current_authorization(self):
        self.artifact.write_bytes(c.encode({'schema': 'synthetic-old-readiness', 'dns_path_verified': True,
                                           'allow_network': True, 'launch': True}))
        with (patch.object(c, 'run_fixed', side_effect=AssertionError('no commands')),
              patch.object(subprocess, 'Popen', side_effect=AssertionError('no launch')),
              patch.object(progress.reports.network_checks, 'run_checks', side_effect=AssertionError('no probes'))):
            saved = self.save()
            out, result = self.resume(saved)
        self.assertEqual(result['checkpoint_matches'], NATIVE)
        self.assertTrue(result['network_revalidation_required'])
        self.assertFalse(result['authorization_restored'])
        self.assertEqual(self.rows(out)['fresh_review']['status'], '未完成')

    def test_cross_platform_save_stays_offline_and_resume_is_incomplete(self):
        target_platform = 'macos' if platform.system() == 'Windows' else 'windows'
        saved = self.output('cross-platform')
        result = progress.save(c, self.config, 'customer-one', target_platform, 'prepare', '只准备当前离线材料', saved,
                               artifacts=[self.artifact], scope_file=self.scope)
        self.assertEqual(result['status'], '已完成')
        out, result = self.resume(saved, target_platform=target_platform)
        self.assertEqual(result['status'], '未完成')
        self.assertFalse(result['checkpoint_matches'])
        self.assertEqual(self.rows(out)['execution_platform']['status'], '未完成')
        self.assertIn('只能离线准备', self.rows(out)['execution_platform']['reason'])
        self.assert_safety(result)

    def test_native_platform_mapping_does_not_treat_linux_or_wsl_as_target_machine(self):
        for actual in ('Linux', 'WSL', 'unknown'):
            for target in ('macos', 'windows'):
                self.assertFalse(progress._execution_matches({'platform': actual}, target))
        self.assertTrue(progress._execution_matches({'platform': 'Darwin'}, 'macos'))
        self.assertTrue(progress._execution_matches({'platform': 'Windows'}, 'windows'))

    def test_private_material_index_locates_selected_offline_note_without_copying_its_body(self):
        recovery_note = self.root / '恢复 使用说明.md'
        secret_body = '这是合成恢复材料正文，不应复制到索引或客户报告。'
        recovery_note.write_text(secret_body, encoding='utf-8')
        saved = self.save(artifacts=[recovery_note])
        out, result = self.resume(saved)
        for directory in (saved, out):
            note = (directory / '继续配置.md').read_text(encoding='utf-8')
            index = (directory / '材料索引.private.md').read_text(encoding='utf-8')
            self.assertIn('事先准备的具体离线恢复说明', note)
            self.assertIn(str(recovery_note), index)
            self.assertIn('Markdown 说明', index)
            self.assertNotIn(secret_body, index)
            self.assertNotIn(secret_body, note)
            self.assertNotIn(str(recovery_note), (directory / 'report.json').read_text(encoding='utf-8'))

    def test_missing_artifact_index_never_invents_a_recovery_file(self):
        saved = self.save(artifacts=[])
        index = (saved / '材料索引.private.md').read_text(encoding='utf-8')
        self.assertIn('没有选择额外材料', index)
        self.assertIn('具体离线恢复说明', index)
        self.assertNotIn(str(self.config), index)

    def test_next_step_rejects_paths_links_credentials_and_non_descriptive_payload(self):
        for text in ('', ' x ', 'x\ny', '\u202etest', '/Users/customer/config', r'C:\Users\name\config',
                     'https://example.com', 'www.example.com', 'sk-secret-token-example', 'Bearer abcdefgh',
                     'token=private', '203.0.113.9', '`run a command`', 'x' * 161,
                     'abcdefghijklmnopqrstuvwx123456789', '[label](payload)', '<script>payload</script>'):
            with self.subTest(text_index=len(text)):
                with self.assertRaisesRegex(c.SetupError, 'SHORT_SAFE_NOTE'):
                    progress.save(c, self.config, 'customer-one', TARGET_PLATFORM, 'prepare', text, self.output('invalid'), scope_file=self.scope)

    def test_symlink_hardlink_and_artifact_replacement_are_not_followed(self):
        link = self.root / 'linked.json'
        try:
            os.link(self.config, link)
        except OSError:
            self.skipTest('filesystem has no hard-link support')
        with self.assertRaises(c.SetupError):
            self.save()
        link.unlink()
        saved = self.save()
        self.artifact.unlink()
        try:
            self.artifact.symlink_to(self.config)
        except OSError:
            return  # Windows CI can lack symbolic-link privileges.
        out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['artifacts']['status'], '未完成')
        self.assertFalse(result['checkpoint_matches'])
        with self.assertRaises(c.SetupError):
            self.save()

    def test_duplicate_and_too_many_artifacts_do_not_create_a_checkpoint(self):
        with self.assertRaisesRegex(c.SetupError, 'DUPLICATE_ARTIFACT'):
            self.save(artifacts=[self.artifact, self.artifact])
        with self.assertRaisesRegex(c.SetupError, 'ARTIFACT_LIMIT'):
            self.save(artifacts=[self.artifact] * 17)
        with self.assertRaisesRegex(c.SetupError, 'NONIDENTIFYING_ALIAS'):
            progress.save(c, self.config, 'contains private spaces', TARGET_PLATFORM, 'prepare', NOTE, self.output('bad-alias'), scope_file=self.scope)

    def test_checkpoint_output_is_never_overwritten(self):
        saved = self.save()
        original = (saved / 'checkpoint.private.json').read_bytes()
        with self.assertRaises(c.SetupError):
            progress.save(c, self.config, 'customer-one', TARGET_PLATFORM, 'prepare', NOTE, saved, scope_file=self.scope)
        self.assertEqual((saved / 'checkpoint.private.json').read_bytes(), original)

    def test_save_detects_material_change_before_creating_checkpoint(self):
        real_file = progress._file
        output = self.output('racing-save')
        def changed_during_read(context, value):
            result = real_file(context, value)
            if Path(value) == self.artifact:
                self.config.write_bytes(b'{"changed":"during synthetic save"}')
            return result
        with patch.object(progress, '_file', side_effect=changed_during_read):
            with self.assertRaisesRegex(c.SetupError, 'INPUT_CHANGED_DURING_SAVE'):
                progress.save(c, self.config, 'customer-one', TARGET_PLATFORM, 'prepare', NOTE, output,
                              artifacts=[self.artifact], scope_file=self.scope)
        self.assertFalse(output.exists())

    def test_checkpoint_and_private_material_index_use_private_storage(self):
        saved = self.save()
        if os.name == 'nt':
            self.assertTrue(progress.storage._win_acl_summary(saved)['private'])
        else:
            self.assertEqual(saved.stat().st_mode & 0o777, 0o700)
            for filename in ('checkpoint.private.json', 'checkpoint.sha256', '继续配置.md', '材料索引.private.md'):
                self.assertEqual((saved / filename).stat().st_mode & 0o777, 0o600)

    def test_changed_or_missing_scope_never_allows_resume_from_defaults(self):
        saved = self.save()
        self.scope.write_text(SCOPE + '范围后来改变，必须重新核对。\n', encoding='utf-8')
        out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['scope']['status'], '未完成')
        self.assertFalse(result['checkpoint_matches'])
        self.assertFalse(result['required_checks_completed'])
        if NATIVE:
            self.assertIn('缺失、改变', self.rows(out)['scope']['reason'])
        note = (out / '继续配置.md').read_text(encoding='utf-8')
        self.assertIn('不能按默认扩大配置', note)
        self.assertNotIn(NOTE, note)
        self.scope.unlink()
        out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['scope']['status'], '未完成')
        self.assertEqual(result['status'], '未完成')
        self.assert_safety(result)

    def test_scope_argument_and_nonempty_utf8_file_are_required(self):
        with self.assertRaisesRegex(c.SetupError, 'SCOPE_FILE_REQUIRED'):
            progress.save(c, self.config, 'customer-one', TARGET_PLATFORM, 'prepare', NOTE, self.output('no-scope'))
        for raw in (b'', b' \n\t', b'\xef\xbb\xbf', b'\x00invalid', b'\xff'):
            self.scope.write_bytes(raw)
            out = self.output('empty-scope')
            with self.assertRaises(c.SetupError):
                progress.save(c, self.config, 'customer-one', TARGET_PLATFORM, 'prepare', NOTE, out, scope_file=self.scope)
            self.assertFalse(out.exists())
        parser = argparse.ArgumentParser()
        progress.register_commands(parser.add_subparsers(dest='command', required=True))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            parser.parse_args(['workflow-save', '--config', str(self.config), '--target-alias', 'customer-one',
                               '--platform', TARGET_PLATFORM, '--stage', 'prepare', '--next-step', NOTE,
                               '--out', str(self.output('cli-no-scope'))])
        self.assertEqual(error.exception.code, 2)

    def test_scope_change_during_save_is_detected_before_output(self):
        real_file = progress._file
        output = self.output('racing-scope')
        def scope_changes_during_artifact_read(context, value):
            result = real_file(context, value)
            if Path(value) == self.artifact:
                self.scope.write_text(SCOPE + '并发变化\n', encoding='utf-8')
            return result
        with patch.object(progress, '_file', side_effect=scope_changes_during_artifact_read):
            with self.assertRaisesRegex(c.SetupError, 'INPUT_CHANGED_DURING_SAVE'):
                progress.save(c, self.config, 'customer-one', TARGET_PLATFORM, 'prepare', NOTE, output,
                              artifacts=[self.artifact], scope_file=self.scope)
        self.assertFalse(output.exists())

    def test_checkpoint_without_bound_scope_is_incomplete_even_if_resealed(self):
        saved = self.save()
        self.reseal(saved, lambda record: record.pop('scope'))
        out, result = self.resume(saved)
        self.assertEqual(self.rows(out)['checkpoint']['status'], '未完成')
        self.assertFalse(result['checkpoint_matches'])
        self.assertFalse(result['required_checks_completed'])


if __name__ == '__main__':
    unittest.main()
