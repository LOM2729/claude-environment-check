"""Exercise shipped command boundaries using temporary synthetic files."""
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'src/claude_setup.py'


class WorkflowCLI(unittest.TestCase):
    def test_save_resume_and_subscription_drift_do_not_replay_changes(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-customer-resume-') as temporary:
            folder = Path(temporary).resolve()
            config = folder / 'current.json'
            config.write_bytes(b'{"mode":"rule","rules":["MATCH,DIRECT"]}\n')
            scope = folder / 'scope.md'
            scope.write_text('仅验证所选桌面入口；视频与远控保留。没有批准换节点。', encoding='utf-8')
            recovery = folder / 'offline.md'
            recovery.write_text('合成恢复说明，仅用于测试文件往返。', encoding='utf-8')
            checkpoint = folder / 'saved'
            target = 'windows' if platform.system() == 'Windows' else 'macos'
            native = platform.system() in ('Darwin', 'Windows')

            def run(*args, expected=0):
                result = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True,
                                        text=True, encoding='utf-8', timeout=30)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                data = json.loads(result.stdout)
                self.assertFalse(data['actions_executed'])
                self.assertFalse(data['authorization_restored'])
                self.assertTrue(data['network_revalidation_required'])
                self.assertEqual(data['network_requests'], 0)
                return data

            run('workflow-save', '--config', config, '--scope-file', scope, '--target-alias', 'synthetic',
                '--platform', target, '--stage', 'configure', '--waiting-for', 'restart',
                '--next-step', '客户恢复连接后核对现状', '--artifact', recovery, '--out', checkpoint)
            self.assertTrue((checkpoint / '继续配置.md').is_file())
            self.assertTrue((checkpoint / '材料索引.private.md').is_file())
            result = run('workflow-resume', '--config', config, '--checkpoint', checkpoint,
                         '--target-alias', 'synthetic', '--platform', target, '--out', folder / 'matched',
                         expected=0 if native else 2)
            self.assertEqual(result['checkpoint_matches'], native)
            changed = b'{"mode":"rule","rules":["MATCH,REJECT"]}\n'
            config.write_bytes(changed)
            result = run('workflow-resume', '--config', config, '--checkpoint', checkpoint,
                         '--target-alias', 'synthetic', '--platform', target, '--out', folder / 'drifted', expected=2)
            self.assertFalse(result['checkpoint_matches'])
            self.assertEqual(config.read_bytes(), changed)
            report = json.loads((folder / 'drifted/report.json').read_text(encoding='utf-8'))
            for row in report['rows']:
                self.assertIn(row['status'], ('已完成', '未完成'))
                if row['status'] == '未完成':
                    self.assertTrue(row['reason'] and row['next_step'])
            for name in ('report.md', 'report.html', 'report.json'):
                text = (folder / 'drifted' / name).read_text(encoding='utf-8')
                self.assertNotIn(str(folder), text)
                self.assertNotIn(scope.read_text(encoding='utf-8'), text)


if __name__ == '__main__':
    unittest.main()
