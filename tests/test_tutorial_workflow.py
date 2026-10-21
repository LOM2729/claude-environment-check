"""End-to-end static tutorial reports must leave runtime acceptance incomplete."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import domestic_policy
from test_ai_routing import BASE


class TutorialWorkflow(unittest.TestCase):
    def test_generated_candidate_and_missing_rule_produce_honest_reports(self):
        candidate = domestic_policy.build_semantics(c, BASE, 'json', 'Customer Node', 'AI-ONLY')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'candidate.json'
            for tampered in (False, True):
                if tampered:
                    del candidate['rules'][1]
                source = c.encode(candidate)
                config.write_bytes(source)
                out = root / str(tampered)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = c.main(['tutorial-check', '--config', str(config), '--node', 'Customer Node',
                                   '--out', str(out)])
                self.assertEqual(code, 2)  # Real client traffic is never proved by static generation.
                result = json.loads(output.getvalue())
                self.assertGreater(result['incomplete'], 0)
                report = json.loads((out / 'report.json').read_bytes())
                static = [r for r in report['rows'] if r['id'] != 'community_runtime']
                self.assertTrue(all(r['status'] == ('未完成' if tampered else '已完成') for r in static))
                self.assertFalse(report['runtime_verified'])
                self.assertEqual(config.read_bytes(), source)
                self.assertFalse(report['scope']['requires_runtime_database_download'])


if __name__ == '__main__':
    unittest.main()
