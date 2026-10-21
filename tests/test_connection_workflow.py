"""Exercise private candidate plans and readback through the shipped CLI path."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c


class ConnectionWorkflow(unittest.TestCase):
    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = c.main(list(args))
        return code, json.loads(output.getvalue())

    def test_candidate_is_private_original_unchanged_and_readback_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'current.json'
            original = {'mixed-port': 7890, 'disable-keep-alive': True,
                        'proxies': [{'name': 'private-node', 'type': 'http',
                                     'server': '192.0.2.1', 'port': 8080, 'password': 'secret-fixture'}],
                        'rules': ['MATCH,DIRECT']}
            source = c.encode(original)
            config.write_bytes(source)
            out = root / 'result'
            code, result = self.invoke('connection-plan', '--config', str(config), '--core', 'mihomo',
                                       '--core-version', '1.19.32', '--out', str(out))
            self.assertEqual(code, 0)
            self.assertTrue(result['content_changed'])
            self.assertEqual(config.read_bytes(), source)
            candidate = json.loads((out / 'candidate.json').read_bytes())
            self.assertFalse(candidate['disable-keep-alive'])
            self.assertEqual(candidate['proxies'], original['proxies'])
            self.assertEqual(candidate['rules'], original['rules'])
            report = (out / 'report.md').read_text()
            self.assertNotIn('secret-fixture', report)
            self.assertNotIn('private-node', report)
            rows = json.loads((out / 'report.json').read_bytes())['rows']
            self.assertTrue(all(row['status'] in ('已完成', '未完成') for row in rows))
            self.assertFalse(next(row for row in rows if row['id'] == 'connection_http_reuse')['status'] == '已完成')
            before = c.verify_readback(out / 'plan', config)
            self.assertNotEqual(before['status'], 'candidate_bytes_match')
            config.write_bytes((out / 'candidate.json').read_bytes())
            self.assertEqual(c.verify_readback(out / 'plan', config)['status'], 'candidate_bytes_match')

    def test_unknown_core_returns_unchanged_candidate_and_no_empty_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'current.json'
            source = b'{"rules": ["MATCH,DIRECT"]}\n'
            config.write_bytes(source)
            out = root / 'result'
            code, result = self.invoke('connection-plan', '--config', str(config), '--out', str(out))
            self.assertEqual(code, 0)
            self.assertFalse(result['content_changed'])
            self.assertEqual((out / 'candidate.json').read_bytes(), source)
            self.assertFalse((out / 'plan').exists())
            self.assertEqual(config.read_bytes(), source)


if __name__ == '__main__':
    unittest.main()
