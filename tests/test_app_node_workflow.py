"""Offline CLI compatibility; no native client access or application writes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import ai_routing as ai
import claude_group as cg
import claude_setup as c
import shadow_domestic
import unified_policy as u


class AppNodeWorkflow(unittest.TestCase):
    def metadata(self):
        return {'schema': 'shadowrocket-app-node/1', 'name': 'App Node', 'type': 'vless',
                'server_family': 'ipv4', 'port': 443, 'chain': 'none',
                'client_version': '2.2.92', 'observation_source': 'native_ui'}

    def baseline(self):
        guards = cg.guarded_rules(ai.catalog(c), 'shadowrocket', 'AI-ONLY')[:9]
        guards = [u.replace_target(rule, ai.target(rule).upper()) for rule in guards]
        rules = ['DOMAIN,blocked.test,REJECT'] + guards + [
            'DOMAIN,customer-internal.test,DIRECT', 'GEOIP,CN,DIRECT',
            'AND,((PROTOCOL,UDP)),REJECT', 'FINAL,PROXY']
        return '[General]\nipv6 = false\n\n[Proxy Group]\nAI-ONLY = select, App Node\n' + \
            'AI-ONLY-Claude = select, App Node\n\n[Rule]\n' + '\n'.join(rules) + '\n'

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'src/claude_setup.py'), *map(str, args)],
                              capture_output=True, text=True, timeout=90)

    def test_reference_requires_narrow_metadata_and_no_secrets(self):
        for key, value in (('port', True), ('chain', 'other'), ('type', 'unknown'), ('type', []),
                           ('client_version', 'unknown'), ('name', 'Other Node')):
            binding = self.metadata(); binding[key] = value
            context = SimpleNamespace(**vars(c), app_node_binding=binding)
            with self.subTest(key=key), self.assertRaises(c.SetupError):
                ai.app_node(context, 'App Node')
        binding = self.metadata(); binding['password'] = 'must-not-be-copied'
        with self.assertRaises(c.SetupError):
            ai.app_node(SimpleNamespace(**vars(c), app_node_binding=binding), 'App Node')
        context = SimpleNamespace(**vars(c), app_node_binding=self.metadata())
        with self.assertRaisesRegex(c.SetupError, 'APP_NODE_SHADOWROCKET_ONLY'):
            ai.layout(context, {}, 'json', 'App Node', 'AI-ONLY')

    def test_unconditional_udp_equivalence_stays_narrow(self):
        self.assertTrue(shadow_domestic.unconditional_udp(' AND, ((PROTOCOL,UDP)), REJECT '))
        self.assertFalse(shadow_domestic.unconditional_udp(
            'AND,((DOMAIN,private.test),(PROTOCOL,UDP)),REJECT'))
        self.assertFalse(shadow_domestic.unconditional_udp('AND,((PROTOCOL,UDP)),DIRECT'))

    def test_cli_prepares_audits_and_rejects_drift_without_applying(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'source.conf'; before = self.baseline().encode()
            source.write_bytes(before)
            node = root / 'node.json'; node.write_bytes(c.encode(self.metadata()))
            review = root / 'review.json'
            result = self.cli('direct-review', '--config', source, '--classify-known',
                              '--preserve-existing', '--output', review)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['pending_rules'], 0)
            common = ['--node', 'App Node', '--group', 'AI-ONLY', '--direct-review', review,
                      '--app-node-reference', node]
            strict = self.cli('ai-route', '--config', source, *common, '--out', root / 'strict')
            self.assertEqual(strict.returncode, 1)
            output = root / 'prepared'
            built = self.cli('ai-route', '--config', source, *common,
                             '--reconcile-existing', '--out', output)
            self.assertEqual(built.returncode, 0, built.stderr)
            report = json.loads(built.stdout)
            self.assertFalse(report['apply_supported']); self.assertFalse(report['runtime_verified'])
            self.assertTrue(report['candidate_requires_same_app_node'])
            self.assertFalse(report['app_node_runtime_verified'])
            candidate = output / 'candidate.conf'
            data = c.parse_config(candidate.read_bytes(), 'shadowrocket')
            self.assertNotIn('proxy', data)  # Never invent credentials or a fake concrete node.
            guards = cg.guarded_rules(ai.catalog(c), 'shadowrocket', 'AI-ONLY')
            self.assertEqual(data['rule'][:len(guards)], guards)
            self.assertIn('DOMAIN,customer-internal.test,DIRECT', data['rule'])
            self.assertEqual(data['rule'].count(shadow_domestic.UDP_RULE), 1)
            self.assertEqual(data['rule'].count(shadow_domestic.V6_RULE), 1)
            audited = self.cli('ai-audit', '--config', candidate, '--baseline', source,
                               *common, '--reconcile-existing')
            self.assertEqual(audited.returncode, 0, audited.stderr)
            audit = json.loads(audited.stdout)
            self.assertEqual(audit['status'], 'static_policy_matches')
            self.assertFalse(audit['runtime_verified'])
            self.assertFalse(audit['reconciliation']['writes_performed'])
            # Reusing the explicit migration option on already canonical policy
            # must not tear down and reinterpret its managed domestic block.
            repeat_review = root / 'repeat-review.json'
            classified = self.cli('direct-review', '--config', candidate, '--classify-known',
                                  '--preserve-existing', '--output', repeat_review)
            self.assertEqual(classified.returncode, 0, classified.stderr)
            repeated = self.cli('ai-route', '--config', candidate, '--node', 'App Node',
                                '--group', 'AI-ONLY', '--direct-review', repeat_review,
                                '--app-node-reference', node, '--reconcile-existing',
                                '--out', root / 'repeat')
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertFalse(json.loads(repeated.stdout)['content_changed'])
            self.assertEqual((root / 'repeat/candidate.conf').read_bytes(), candidate.read_bytes())
            tampered = root / 'tampered.conf'
            changed = candidate.read_text().replace('DOMAIN,customer-internal.test,DIRECT',
                                                     'DOMAIN,customer-internal.test,AI-ONLY')
            tampered.write_text(changed)
            drift = self.cli('ai-audit', '--config', tampered, '--baseline', source,
                             *common, '--reconcile-existing')
            self.assertEqual(drift.returncode, 2, drift.stderr)
            self.assertEqual(source.read_bytes(), before)
            bad_binding = self.metadata(); bad_binding['server_family'] = 'ipv6'
            node.write_bytes(c.encode(bad_binding))
            invalid = self.cli('ai-route', '--config', source, *common,
                               '--reconcile-existing', '--out', root / 'ipv6')
            self.assertEqual(invalid.returncode, 1)
            self.assertIn('UNIFIED_IPV6_NODE_REVIEW_REQUIRED', invalid.stderr)


if __name__ == '__main__':
    unittest.main()
