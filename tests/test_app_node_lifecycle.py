"""Synthetic app-local metadata baselines; no collection, app launch or probes."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ai_routing as ai
import claude_group as cg
import claude_setup as c
import domestic_policy as domestic
import readiness_lifecycle as life
import unified_policy as unified


class Context:
    def __init__(self, binding):
        self.app_node_binding = binding

    def __getattr__(self, key):
        return getattr(c, key)


class AppNodeLifecycle(unittest.TestCase):
    node = 'Synthetic Node'
    group = 'Synthetic AI'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binding = {'schema': 'shadowrocket-app-node/1', 'name': self.node,
                        'type': 'vless', 'server_family': 'ipv4', 'port': 8443,
                        'chain': 'none', 'client_version': '1.0.0', 'observation_source': 'native_ui'}
        self.context = Context(copy.deepcopy(self.binding))
        guards = cg.guarded_rules(ai.catalog(c), 'shadowrocket', self.group)
        rules = ['GEOIP,CN,DIRECT'] + guards[:3] + ['DOMAIN,custom-business.test,PROXY', 'FINAL,PROXY']
        rules[2] = rules[2].replace(cg.name(self.group), cg.name(self.group).upper())
        self.text = ('[General]\nipv6 = false\n[Proxy Group]\n' +
                     '\n'.join(label + ' = select, ' + self.node for label in (self.group, cg.name(self.group))) +
                     '\n[Rule]\n' + '\n'.join(rules) + '\n')
        self.original = self.root / 'original.conf'
        self.original.write_text(self.text)
        source = c.parse_config(self.text.encode(), 'shadowrocket')
        candidate = domestic.build_semantics(self.context, source, 'shadowrocket', self.node,
                                              self.group, reconcile_existing=True)
        self.current = self.root / 'candidate.conf'
        self.current.write_text(unified.render_shadow(c, self.text, candidate))
        self.baseline = self.root / 'baseline'
        self.executable = self.root / 'synthetic-never-execute'
        self.native = {'platform': 'Synthetic', 'values': {'https_proxy_enabled': True},
                       'dns_identity_sha256': 'a' * 64}
        for patcher in (patch.object(life, 'native_state', return_value=self.native),
                        patch.object(life, 'client_identity', return_value={'path': 'synthetic', 'binary_sha256': 'b' * 64}),
                        patch.object(life, 'machine_id', return_value='synthetic-machine')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def create(self, **kwargs):
        return life.create_baseline(self.context, self.current, 'shadowrocket', self.original,
                                    self.node, self.group, self.executable, None, self.baseline,
                                    policy='domestic-v4', reconcile_existing=True, **kwargs)

    def check(self, context=None):
        return life.recheck(self.context if context is None else context, self.baseline,
                            self.current, self.executable)

    def replace_record(self, record):
        raw = c.encode(record)
        (self.baseline / 'baseline.json').write_bytes(raw)
        (self.baseline / 'baseline.sha256').write_text(c.sha(raw) + '\n')

    def test_reconciliation_intent_and_metadata_snapshot_are_hash_bound_static_inputs(self):
        with patch.object(domestic, 'audit', wraps=domestic.audit) as audit:
            result = self.create()
            self.assertTrue(audit.call_args.kwargs['reconcile_existing'])
        saved, _, _ = life.read_baseline(c, self.baseline)
        snapshot = (self.baseline / 'app-node.private.json').read_bytes()
        self.assertEqual(saved['app_node_metadata_sha256'], c.sha(snapshot))
        self.assertEqual(c.load_json(snapshot), self.binding)
        self.assertTrue(saved['reconcile_existing'])
        self.assertEqual(saved['app_node_context_kind'], 'caller_supplied_static_declaration')
        self.assertFalse(saved['runtime_adoption_verified'])
        self.assertFalse(result['runtime_adoption_verified'])
        self.assertNotIn(self.node, str(result))
        with patch.object(domestic, 'audit', wraps=domestic.audit) as audit:
            rows, _ = self.check()
        self.assertTrue(audit.call_args.kwargs['reconcile_existing'])
        self.assertEqual(next(r for r in rows if r['id'] == 'ai_policy')['status'], '已完成')
        self.assertEqual(next(r for r in rows if r['id'] == 'app_node_context')['status'], '已完成')

    def test_saved_metadata_is_not_restored_as_current_evidence(self):
        self.create()
        before = self.current.read_bytes()
        with patch.object(domestic, 'audit') as audit:
            rows, _ = self.check(c)
        audit.assert_not_called()
        row = next(r for r in rows if r['id'] == 'app_node_context')
        self.assertEqual(row['status'], '未完成')
        self.assertTrue(row['required'])
        self.assertIn('--app-node-reference', row['next_step'])
        self.assertEqual(next(r for r in rows if r['id'] == 'ai_policy')['status'], '未完成')
        self.assertEqual(self.current.read_bytes(), before)
        self.assertIsNone(getattr(c, 'app_node_binding', None))

    def test_changed_or_invalid_current_metadata_blocks_policy_audit(self):
        self.create()
        for changes in ({'port': 8444}, {'chain': 'unknown'}, {'name': 'Different Node'}):
            with self.subTest(changes=changes), patch.object(domestic, 'audit') as audit:
                rows, _ = self.check(Context(dict(self.binding, **changes)))
                audit.assert_not_called()
                self.assertEqual(next(r for r in rows if r['id'] == 'app_node_context')['status'], '未完成')
                self.assertEqual(next(r for r in rows if r['id'] == 'ai_policy')['status'], '未完成')

    def test_metadata_snapshot_tampering_and_baseline_hash_tampering_are_rejected(self):
        self.create()
        snapshot = self.baseline / 'app-node.private.json'
        original = snapshot.read_bytes()
        snapshot.write_bytes(c.encode(dict(self.binding, port=8444)))
        with self.assertRaisesRegex(c.SetupError, 'BASELINE_APP_NODE_SNAPSHOT_MISMATCH'):
            life.read_baseline(c, self.baseline)
        snapshot.write_bytes(original)
        record = c.load_json((self.baseline / 'baseline.json').read_bytes())
        record['reconcile_existing'] = False
        (self.baseline / 'baseline.json').write_bytes(c.encode(record))
        with self.assertRaisesRegex(c.SetupError, 'BASELINE_INTEGRITY_MISMATCH'):
            life.read_baseline(c, self.baseline)

    def test_old_records_without_optional_fields_remain_readable(self):
        self.create()
        record = c.load_json((self.baseline / 'baseline.json').read_bytes())
        for key in ('app_node_metadata_sha256', 'app_node_context_kind', 'reconcile_existing', 'runtime_adoption_verified'):
            record.pop(key)
        self.replace_record(record)
        saved, _, _ = life.read_baseline(c, self.baseline)
        self.assertNotIn('app_node_metadata_sha256', saved)
        with patch.object(domestic, 'audit', return_value={'status': 'static_policy_matches'}) as audit:
            rows, _ = self.check(c)
        self.assertFalse(audit.call_args.kwargs['reconcile_existing'])
        self.assertNotIn('app_node_context', [r['id'] for r in rows])

    def test_new_reconciliation_keyword_is_not_forwarded_to_other_policy_apis(self):
        for policy, module in (('unified-v4', unified), ('ai-only', ai)):
            with self.subTest(policy=policy), patch.object(module, 'audit', return_value={'status': 'static_policy_matches'}) as audit:
                output = self.root / policy
                life.create_baseline(c, self.current, 'shadowrocket', self.original, self.node, self.group,
                                     self.executable, None, output, policy=policy)
                self.assertNotIn('reconcile_existing', audit.call_args.kwargs)
                life.recheck(c, output, self.current, self.executable)
                self.assertNotIn('reconcile_existing', audit.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
