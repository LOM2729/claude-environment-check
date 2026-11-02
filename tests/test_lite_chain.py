"""Synthetic offline graph/export checks. No private customer fixtures or I/O."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
import ai_routing as ai
import chain_routing as chain
import claude_setup as c
import domestic_policy as domestic
import unified_policy as unified
from lite import config_engine as engine


BASE = {
    'mode': 'rule',
    'mixed-port': 7890,
    'proxies': [{'name': 'Exit', 'type': 'socks5', 'server': '192.0.2.10', 'port': 1080,
                 'username': 'synthetic-user', 'password': 'SYNTHETIC_SECRET'}],
    'proxy-groups': [{'name': 'Foreign', 'type': 'select', 'proxies': ['Exit']}],
    'dns': {'enable': True, 'nameserver': ['https://dns.example.test/dns-query']},
    'rules': ['GEOIP,CN,DIRECT', 'MATCH,Foreign'],
    'x-original-extension': {'nested': ['retain', 7]},
}


def chained():
    obj = copy.deepcopy(BASE)
    obj['proxies'][0]['dialer-proxy'] = 'Upstream'
    obj['proxies'].extend([
        {'name': 'Hop A', 'type': 'socks5', 'server': '192.0.2.11', 'port': 1080,
         'password': 'SYNTHETIC_HOP_SECRET'},
        {'name': 'Hop B', 'type': 'socks5', 'server': '192.0.2.12', 'port': 1080},
    ])
    obj['proxy-groups'].append({'name': 'Upstream', 'type': 'select', 'proxies': ['Hop B', 'Hop A']})
    return obj


class LiteChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Graph/export behavior does not need to reparse the full bundled
        # domestic snapshot on every case. Existing policy tests cover it.
        self.snapshot = patch.object(domestic, 'snapshot', return_value={
            domestic.CN: {'type': 'inline', 'behavior': 'domain', 'payload': ['+.bilibili.com']},
            domestic.VIDEO: {'type': 'inline', 'behavior': 'domain', 'payload': ['+.video.example.test']},
        })
        self.snapshot.start()
        unified._domestic_domain_index.cache_clear()

    def tearDown(self):
        self.snapshot.stop()
        unified._domestic_domain_index.cache_clear()
        self.tmp.cleanup()

    def source(self, obj=None, name='source.json'):
        path = self.root / name
        path.write_bytes(c.encode(BASE if obj is None else obj))
        return path

    def export(self, obj=None, preserve=False):
        source = self.source(obj)
        before = source.read_bytes()
        result = engine.prepare_candidate(source, 'Exit', self.root / 'export', preserve)
        self.assertEqual(before, source.read_bytes())
        return source, result, c.parse_config(Path(result['candidate_path']).read_bytes(), 'yaml')

    def reject_graph(self, obj, code):
        with self.assertRaisesRegex(c.SetupError, '^' + code + '$'):
            chain.validate(c, obj, 'Exit')

    def test_direct_node_export_preserves_input_and_unknown_fields(self):
        source, result, actual = self.export()
        self.assertTrue(result['export_ready'])
        self.assertFalse(result['runtime_verified'])
        self.assertFalse(result['apply_supported'])
        self.assertEqual(actual['proxies'], BASE['proxies'])
        self.assertEqual(actual['proxy-groups'][:1], BASE['proxy-groups'])
        self.assertEqual(actual['x-original-extension'], BASE['x-original-extension'])
        self.assertEqual(actual['mixed-port'], 7890)
        self.assertEqual(actual['proxy-groups'][-1]['proxies'], ['Exit'])
        self.assertEqual((Path(result['candidate_path']).parent / 'original.private.bin').read_bytes(), source.read_bytes())
        self.assertIn('GEODATA_RESOURCE_NOT_VERIFIED', result['warnings'])
        self.assertTrue(result['same_client_required'])
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(result))

    def test_chain_selector_order_and_credentials_preserved(self):
        obj = chained()
        _, result, actual = self.export(obj)
        self.assertEqual(actual['proxies'], obj['proxies'])
        self.assertEqual(actual['proxy-groups'][:2], obj['proxy-groups'])
        self.assertEqual(actual['proxies'][0]['dialer-proxy'], 'Upstream')
        self.assertEqual(actual['proxy-groups'][1]['proxies'], ['Hop B', 'Hop A'])
        self.assertEqual(result['private_summary']['chain']['edges']['Upstream'], ['Hop B', 'Hop A'])
        self.assertNotIn('SYNTHETIC_HOP_SECRET', json.dumps(result))

    def test_transitive_chain_and_disconnected_cycles(self):
        obj = chained()
        obj['proxies'][1]['dialer-proxy'] = 'Last'
        obj['proxies'].append({'name': 'Last', 'type': 'socks5', 'server': '192.0.2.20', 'port': 1080})
        self.assertIn('Last', chain.validate(c, obj, 'Exit')['dependencies'])
        obj['proxies'][-1]['dialer-proxy'] = 'Exit'
        self.reject_graph(obj, 'CHAIN_DEPENDENCY_CYCLE')
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'] += [{'name': 'Unused A', 'type': 'select', 'proxies': ['Unused B']},
                                {'name': 'Unused B', 'type': 'select', 'proxies': ['Unused A']}]
        self.reject_graph(obj, 'CHAIN_DEPENDENCY_CYCLE')

    def test_missing_and_invalid_references(self):
        obj = chained()
        obj['proxies'][1]['dialer-proxy'] = 'Missing'
        self.reject_graph(obj, 'CHAIN_REFERENCE_MISSING')
        obj = chained()
        obj['proxy-groups'][1]['proxies'] = ['Missing']
        self.reject_graph(obj, 'CHAIN_REFERENCE_MISSING')
        obj = chained()
        obj['proxies'][0]['dialer-proxy'] = []
        self.reject_graph(obj, 'CHAIN_REFERENCE_INVALID')

    def test_missing_transit_endpoint_blocks_selected_chain_before_export(self):
        obj = chained()
        obj['proxies'][1].pop('server')
        self.reject_graph(obj, 'CHAIN_NODE_ENDPOINT_INCOMPLETE')
        source = self.source(obj)
        rows = {row['name']: row for row in engine.inspect_config(source)['nodes']}
        self.assertFalse(rows['Exit']['selectable'])
        self.assertEqual(rows['Exit']['reason'], 'CHAIN_NODE_ENDPOINT_INCOMPLETE')
        self.assertTrue(rows['Hop B']['selectable'])
        with self.assertRaisesRegex(c.SetupError, '^CHAIN_NODE_ENDPOINT_INCOMPLETE$'):
            engine.prepare_candidate(source, 'Exit', self.root / 'blocked')
        self.assertFalse((self.root / 'blocked').exists())

    def test_bad_direct_node_is_individually_unselectable(self):
        obj = copy.deepcopy(BASE)
        obj['proxies'].append({'name': 'Incomplete', 'type': 'socks5', 'server': '192.0.2.30'})
        source = self.source(obj)
        rows = {row['name']: row for row in engine.inspect_config(source)['nodes']}
        self.assertTrue(rows['Exit']['selectable'])
        self.assertFalse(rows['Incomplete']['selectable'])
        self.assertEqual(rows['Incomplete']['reason'], 'CHAIN_NODE_ENDPOINT_INCOMPLETE')
        for field, value in (('server', 'https://example.test'), ('server', 'user@example.test'),
                             ('server', 'host name'), ('server', 'host\nname'),
                             ('port', 0), ('port', 65536), ('port', True), ('port', '1080')):
            bad = copy.deepcopy(BASE)
            bad['proxies'][0][field] = value
            with self.subTest(field=field, value=value):
                self.reject_graph(bad, 'CHAIN_NODE_ENDPOINT_INVALID')

    def test_global_mode_has_precise_review_error(self):
        obj = copy.deepcopy(BASE)
        obj['mode'] = 'global'
        source = self.source(obj)
        with self.assertRaisesRegex(c.SetupError, '^LITE_RULE_MODE_REVIEW_REQUIRED$'):
            engine.inspect_config(source)
        with self.assertRaisesRegex(c.SetupError, '^LITE_RULE_MODE_REVIEW_REQUIRED$'):
            engine.prepare_candidate(source, 'Exit', self.root / 'blocked')
        self.assertFalse((self.root / 'blocked').exists())

    def test_legacy_and_nonstandard_chain_refused(self):
        obj = chained()
        obj['proxy-groups'][1]['type'] = 'relay'
        self.reject_graph(obj, 'CHAIN_RELAY_UNSUPPORTED')
        obj = chained()
        obj['proxies'][0]['detour'] = 'Hop A'
        self.reject_graph(obj, 'CHAIN_SYNTAX_UNSUPPORTED')

    def test_label_collisions_and_invalid_labels(self):
        obj = chained()
        obj['proxies'][1]['name'] = 'exit'
        self.reject_graph(obj, 'CHAIN_LABEL_COLLISION')
        for name in ('DIRECT', 'bad,node', ' leading', 'line\nend'):
            obj = copy.deepcopy(BASE)
            obj['proxies'][0]['name'] = name
            with self.assertRaises(c.SetupError):
                chain.graph(c, obj)

    def test_managed_collision_chooses_fresh_group_without_touching_existing(self):
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'] += [{'name': 'AI-ONLY', 'type': 'select', 'proxies': ['Exit']},
                                {'name': 'ai-only-2-claude', 'type': 'select', 'proxies': ['Exit']}]
        source, result, actual = self.export(obj)
        self.assertEqual(result['managed_group'], 'AI-ONLY-3')
        self.assertEqual(actual['proxy-groups'][:3], obj['proxy-groups'])
        audit = engine.audit_candidate(source, result['candidate_path'], 'Exit')
        self.assertEqual(audit['status'], 'static_policy_matches')

    def test_unknown_direct_requires_explicit_preservation(self):
        obj = copy.deepcopy(BASE)
        obj['rules'].insert(0, 'DOMAIN,unknown.example.test,DIRECT')
        source = self.source(obj)
        self.assertEqual(engine.inspect_config(source)['pending_direct_count'], 1)
        with self.assertRaisesRegex(c.SetupError, '^LITE_EXISTING_DIRECT_REVIEW_REQUIRED$'):
            engine.prepare_candidate(source, 'Exit', self.root / 'blocked')
        self.assertFalse((self.root / 'blocked').exists())
        result = engine.prepare_candidate(source, 'Exit', self.root / 'preserved', True)
        actual = c.parse_config(Path(result['candidate_path']).read_bytes(), 'yaml')
        self.assertIn('DOMAIN,unknown.example.test,DIRECT', actual['rules'])
        self.assertEqual(result['private_summary']['direct_review']['entries'][0]['classification'], 'preserved_existing')

    def test_known_direct_classified_without_preserve(self):
        obj = copy.deepcopy(BASE)
        obj['rules'].insert(0, 'DOMAIN-SUFFIX,bilibili.com,DIRECT')
        _, result, actual = self.export(obj)
        self.assertIn('DOMAIN-SUFFIX,bilibili.com,DIRECT', actual['rules'])
        self.assertEqual(result['private_summary']['direct_review']['entries'][0]['classification'], 'known_domestic')

    def test_provider_chain_blocked_and_other_http_declaration_retained(self):
        obj = chained()
        obj['proxy-providers'] = {'Remote': {'type': 'http', 'url': 'https://example.test/synthetic', 'path': './cache/provider.yaml'}}
        obj['proxy-groups'][1]['use'] = ['Remote']
        self.reject_graph(obj, 'CHAIN_EXTERNAL_DEPENDENCY_UNRESOLVED')
        obj['proxy-groups'][1].pop('use')
        obj['rule-providers'] = {'Rules': {'type': 'http', 'behavior': 'domain', 'url': 'https://example.test/rules', 'path': './cache/rules.yaml'}}
        _, result, actual = self.export(obj)
        self.assertEqual(actual['proxy-providers'], obj['proxy-providers'])
        self.assertEqual(actual['rule-providers']['Rules'], obj['rule-providers']['Rules'])
        self.assertTrue(result['same_client_required'])
        self.assertFalse(result['private_summary']['portable'])

    def test_local_resource_blocker_and_no_partial_output(self):
        obj = copy.deepcopy(BASE)
        obj['proxies'][0]['ca-file'] = './private-ca.pem'
        source = self.source(obj)
        inspection = engine.inspect_config(source)
        self.assertFalse(inspection['export_ready'])
        self.assertIn('LOCAL_RESOURCE_PATH_NOT_REBASED', inspection['blockers'])
        with self.assertRaisesRegex(c.SetupError, '^LITE_DEPENDENCIES_UNRESOLVED$'):
            engine.prepare_candidate(source, 'Exit', self.root / 'blocked')
        self.assertFalse((self.root / 'blocked').exists())

    def test_transport_request_paths_are_preserved_without_file_dependency(self):
        obj = copy.deepcopy(BASE)
        obj['proxies'][0].update({'type': 'vless', 'network': 'ws',
                                 'ws-opts': {'path': '/ws?ed=2048', 'headers': {'Host': 'example.test'}},
                                 'http-upgrade-opts': {'path': '/upgrade'},
                                 'xhttp-opts': {'path': '/stream'}})
        _, result, actual = self.export(obj)
        self.assertTrue(result['export_ready'])
        self.assertNotIn('LOCAL_RESOURCE_PATH_NOT_REBASED', result['warnings'])
        self.assertEqual(actual['proxies'], obj['proxies'])

    def test_file_provider_path_remains_a_blocker(self):
        obj = copy.deepcopy(BASE)
        obj['rule-providers'] = {'Local': {'type': 'file', 'behavior': 'domain', 'path': './rules.yaml'}}
        inspection = engine.inspect_config(self.source(obj))
        self.assertFalse(inspection['export_ready'])
        self.assertIn('LOCAL_RESOURCE_PATH_NOT_REBASED', inspection['blockers'])

    def test_source_yaml_roundtrip_and_anchor_refusal(self):
        source = self.root / 'source.yaml'
        source.write_text('# kept source comment\n' + json.dumps(chained()), encoding='utf-8')
        before = source.read_bytes()
        result = engine.prepare_candidate(source, 'Exit', self.root / 'yaml-export')
        self.assertEqual(source.read_bytes(), before)
        self.assertTrue(Path(result['candidate_path']).read_text().startswith('# kept source comment'))
        source.write_text('proxies: &nodes []\nproxy-groups: *nodes\nrules: [MATCH,Foreign]\n', encoding='utf-8')
        with self.assertRaisesRegex(c.SetupError, '^YAML_ANCHORS_UNSUPPORTED$'):
            engine.inspect_config(source)

    def test_static_audit_detects_chain_tamper(self):
        source, result, actual = self.export(chained())
        candidate = Path(result['candidate_path'])
        actual['proxies'][0]['dialer-proxy'] = 'Hop A'
        candidate.write_bytes(c.encode(actual))
        audit = engine.audit_candidate(source, candidate, 'Exit')
        self.assertEqual(audit['status'], 'unexpected_changes')
        self.assertFalse(audit['original_nodes_preserved'])
        self.assertFalse(audit['runtime_verified'])

    def test_legacy_context_remains_strict(self):
        with self.assertRaisesRegex(c.SetupError, '^AI_NODE_CHAIN_REVIEW_REQUIRED$'):
            ai.layout(c, chained(), 'json', 'Exit', 'Unused')
        self.assertFalse(getattr(c, 'allow_validated_dialer_chain', False))

    def test_no_process_or_network_calls_and_output_never_overwritten(self):
        source = self.source()
        output = self.root / 'export'
        with patch.object(c, 'run_fixed', side_effect=AssertionError('No process calls')):
            engine.prepare_candidate(source, 'Exit', output)
        before = (output / 'candidate.yaml').read_bytes()
        with self.assertRaisesRegex(c.SetupError, '^NEW_OUTPUT_DIRECTORY_REQUIRED$'):
            engine.prepare_candidate(source, 'Exit', output)
        self.assertEqual((output / 'candidate.yaml').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
