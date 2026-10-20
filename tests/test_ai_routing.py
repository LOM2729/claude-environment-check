"""Synthetic offline inputs only; no customer-machine collection or network calls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c
import ai_routing as ai

SECRET = 'CUSTOMER_SECRET_NEVER_STDOUT'
BASE = {
    'mode': 'rule',
    'proxies': [{'name': 'Customer Node', 'type': 'socks5', 'server': '192.0.2.10',
                 'port': 1080, 'password': SECRET, 'udp': False}],
    'proxy-groups': [{'name': 'Foreign', 'type': 'select', 'proxies': ['Customer Node']}],
    'dns': {'enable': True, 'ipv6': False, 'nameserver': ['https://example.test/dns-query']},
    'rules': ['DOMAIN,blocked.test,REJECT', 'GEOIP,CN,DIRECT', 'MATCH,Foreign'],
}
SHADOW = '''# customer comments
[General]
ipv6 = false
udp-policy-not-supported-behaviour = DIRECT
[Proxy]
Customer Node = socks5, 192.0.2.10, 1080, password=CUSTOMER_SECRET_NEVER_STDOUT
[Proxy Group]
Foreign = select, Customer Node
[Rule]
DOMAIN,blocked.test,REJECT
GEOIP,CN,DIRECT
FINAL,Foreign
'''


class AIRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = ai.catalog(c)

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, data=None, fmt='json'):
        if data is None:
            data = c.encode(BASE)
        if isinstance(data, str):
            data = data.encode()
        source = self.root / ('original.' + {'json': 'json', 'yaml': 'yaml', 'shadowrocket': 'conf'}[fmt])
        source.write_bytes(data)
        out = self.root / 'candidate'
        result = ai.prepare(c, source, fmt, 'Customer Node', out)
        self.assertEqual(source.read_bytes(), data)
        candidate = out / ('candidate.' + source.suffix[1:])
        return source, candidate, result

    def rejected(self, obj, code, node='Customer Node'):
        with self.assertRaisesRegex(c.SetupError, '^' + code + '$'):
            ai.semantic_candidate(c, obj, 'json', node, ai.GROUP, self.data)

    def test_json_private_plan_and_exact_preservation(self):
        source, candidate, result = self.prepare()
        actual = c.parse_config(candidate.read_bytes(), 'json')
        self.assertEqual(actual['rules'][0], BASE['rules'][0])
        self.assertEqual(actual['rules'][-2:], BASE['rules'][-2:])
        self.assertEqual(actual['proxy-groups'][:-1], BASE['proxy-groups'])
        for key in ('proxies', 'dns', 'mode'):
            self.assertEqual(actual[key], BASE[key])
        self.assertEqual(actual['proxy-groups'][-1], ai.expected_group('Customer Node', 'AI-ONLY'))
        self.assertEqual(result['added_rule_count'], 3 * result['domain_count'])
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertFalse(result['runtime_verified'])
        plan = candidate.parent / 'plan'
        self.assertEqual((plan / 'original.bin').read_bytes(), source.read_bytes())
        self.assertEqual(c.verify_readback(plan, candidate, True)['status'], 'candidate_bytes_match')

    def test_each_domain_udp_deny_precedes_proxy_then_guard(self):
        rules = ai.guarded_rules(self.data, 'yaml', 'AI-ONLY')
        for i in range(0, len(rules), 3):
            self.assertIn('(NETWORK,udp)', rules[i])
            self.assertTrue(rules[i].endswith(',REJECT'))
            self.assertTrue(rules[i + 1].endswith(',AI-ONLY'))
            self.assertTrue(rules[i + 2].endswith(',REJECT'))
        self.assertNotIn('DIRECT', '\n'.join(rules))

    def test_shared_hosts_not_shared_provider_suffixes(self):
        self.assertNotIn('cloudflare.com', self.data['suffixes'])
        self.assertIn('challenges.cloudflare.com', self.data['exact_hosts'])
        self.assertNotIn('workos.com', self.data['suffixes'])
        self.assertIn('chatgpt.com', self.data['suffixes'])
        self.assertIn('claude.ai', self.data['suffixes'])

    def test_yaml_comments_crlf_and_bom(self):
        import yaml
        text = '# customer original\n' + yaml.safe_dump(BASE, sort_keys=False, allow_unicode=True)
        data = b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode()
        source, candidate, _ = self.prepare(data, 'yaml')
        after = candidate.read_bytes()
        self.assertTrue(after.startswith(b'\xef\xbb\xbf# customer original\r\n'))
        self.assertNotIn(b'\n', after.replace(b'\r\n', b''))
        self.assertEqual(ai.audit(c, data, after, 'yaml', 'Customer Node')['status'], 'static_policy_matches')

    def test_yaml_nested_indentation_and_trailing_group(self):
        import yaml
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'] = obj.pop('proxy-groups')
        text = yaml.safe_dump(obj, sort_keys=False)
        # Convert indentless root sequences to conventional two-space indentation.
        lines = text.splitlines()
        inside = False
        for i, line in enumerate(lines):
            if line and not line.startswith((' ', '-')):
                inside = line in ('proxies:', 'proxy-groups:', 'rules:')
            elif inside:
                lines[i] = '  ' + line
        _, candidate, _ = self.prepare('\n'.join(lines), 'yaml')
        self.assertEqual(c.parse_config(candidate.read_bytes(), 'yaml')['proxy-groups'][-1]['name'], 'AI-ONLY')

    def test_yaml_empty_group_list(self):
        import yaml
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'] = []
        obj['rules'][-1] = 'MATCH,Customer Node'
        _, candidate, _ = self.prepare(yaml.safe_dump(obj, sort_keys=False), 'yaml')
        self.assertEqual(len(c.parse_config(candidate.read_bytes(), 'yaml')['proxy-groups']), 1)

    def test_yaml_missing_group_list(self):
        import yaml
        obj = copy.deepcopy(BASE)
        del obj['proxy-groups']
        obj['rules'][-1] = 'MATCH,Customer Node'
        _, candidate, _ = self.prepare(yaml.safe_dump(obj, sort_keys=False), 'yaml')
        self.assertEqual(len(c.parse_config(candidate.read_bytes(), 'yaml')['proxy-groups']), 1)

    def test_shadowrocket_protocol_and_preserve_global_udp(self):
        _, candidate, _ = self.prepare(SHADOW, 'shadowrocket')
        text = candidate.read_text()
        self.assertIn('(PROTOCOL,UDP)),REJECT-NO-DROP', text)
        self.assertNotIn('NETWORK,udp', text)
        self.assertIn('udp-policy-not-supported-behaviour = DIRECT', text)
        self.assertIn('# customer comments', text)
        self.assertEqual(c.config_summary(candidate.read_bytes(), 'shadowrocket')['unknown_references'], 0)

    def test_shadowrocket_group_at_eof_without_newline(self):
        text = SHADOW.replace('[Proxy Group]\nForeign = select, Customer Node\n', '')
        text += '[Proxy Group]\nForeign = select, Customer Node'
        self.prepare(text, 'shadowrocket')

    def test_shadowrocket_missing_group(self):
        text = SHADOW.replace('[Proxy Group]\nForeign = select, Customer Node\n', '').replace('FINAL,Foreign', 'FINAL,Customer Node')
        self.prepare(text, 'shadowrocket')

    def test_direct_node_disallowed(self):
        self.rejected(BASE, 'AI_PROXY_NODE_REQUIRED', 'DIRECT')

    def test_group_as_node_disallowed(self):
        self.rejected(BASE, 'AI_CONCRETE_NODE_NOT_FOUND', 'Foreign')

    def test_external_provider_node_requires_review(self):
        obj = copy.deepcopy(BASE)
        obj['proxies'] = []
        obj['proxy-providers'] = {'remote': {'type': 'http', 'url': 'https://example.test'}}
        self.rejected(obj, 'AI_CONCRETE_NODE_NOT_FOUND')

    def test_direct_transport_and_chain_disallowed(self):
        for field, value, code in [('type', 'direct', 'AI_NODE_TRANSPORT_REVIEW_REQUIRED'),
                                   ('dialer-proxy', 'DIRECT', 'AI_NODE_CHAIN_REVIEW_REQUIRED')]:
            obj = copy.deepcopy(BASE)
            obj['proxies'][0][field] = value
            self.rejected(obj, code)

    def test_global_mode_disallowed(self):
        obj = copy.deepcopy(BASE)
        obj['mode'] = 'global'
        self.rejected(obj, 'AI_RULE_MODE_REQUIRED')

    def test_missing_domestic_rules_disallowed(self):
        obj = copy.deepcopy(BASE)
        obj['rules'] = ['MATCH,Foreign']
        self.rejected(obj, 'AI_BASE_DIRECT_RULES_REQUIRED')

    def test_direct_or_unresolved_final_disallowed(self):
        for target, code in [('DIRECT', 'AI_BASE_PROXY_FALLBACK_REQUIRED'),
                             ('Missing', 'AI_BASE_FALLBACK_UNRESOLVED')]:
            obj = copy.deepcopy(BASE)
            obj['rules'][-1] = 'MATCH,' + target
            self.rejected(obj, code)

    def test_later_deny_not_silently_bypassed(self):
        obj = copy.deepcopy(BASE)
        obj['rules'].insert(-1, 'DOMAIN-SUFFIX,openai.com,REJECT')
        self.rejected(obj, 'AI_LATER_REJECT_REVIEW_REQUIRED')

    def test_no_resolve_reject_keeps_priority(self):
        obj = copy.deepcopy(BASE)
        obj['rules'][0] = 'IP-CIDR,192.0.2.0/24,REJECT,no-resolve'
        result, at = ai.semantic_candidate(c, obj, 'json', 'Customer Node', ai.GROUP, self.data)
        self.assertEqual(at, 1)
        self.assertEqual(result['rules'][0], obj['rules'][0])

    def test_recursive_deny_group_keeps_priority(self):
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'] += [{'name': 'Deny', 'type': 'select', 'proxies': ['REJECT']},
                                {'name': 'Deny Outer', 'type': 'select', 'proxies': ['Deny']}]
        obj['rules'][0] = 'DOMAIN-SUFFIX,claude.ai,Deny Outer'
        result, at = ai.semantic_candidate(c, obj, 'json', 'Customer Node', ai.GROUP, self.data)
        self.assertEqual(at, 1)
        self.assertEqual(result['rules'][0], obj['rules'][0])

    def test_mixed_deny_groups_require_review(self):
        for options in ({'proxies': ['REJECT', 'Customer Node']},
                        {'proxies': ['REJECT'], 'use': ['provider']}):
            obj = copy.deepcopy(BASE)
            obj['proxy-groups'].append(dict(name='Deny', type='select', **options))
            self.rejected(obj, 'AI_MIXED_DENY_GROUP_REVIEW_REQUIRED')

    def test_reject_prefix_is_not_a_builtin_deny(self):
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'].append({'name': 'REJECT-options', 'type': 'select', 'proxies': ['DIRECT', 'Customer Node']})
        obj['rules'].insert(1, 'DOMAIN-SUFFIX,claude.ai,REJECT-options')
        actual, at = ai.semantic_candidate(c, obj, 'json', 'Customer Node', ai.GROUP, self.data)
        self.assertEqual(at, 1)
        self.assertGreater(actual['rules'].index(obj['rules'][1]), 1 + len(ai.guarded_rules(self.data, 'json', ai.GROUP)) - 1)

    def test_deny_group_cycle_requires_review(self):
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'] += [{'name': 'A', 'proxies': ['B']}, {'name': 'B', 'proxies': ['A']}]
        self.rejected(obj, 'AI_GROUP_CYCLE_REVIEW_REQUIRED')

    def test_colliding_group_not_overwritten(self):
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'].append(ai.expected_group('Customer Node', 'AI-ONLY'))
        self.rejected(obj, 'AI_GROUP_ALREADY_EXISTS')

    def test_script_cannot_override_rule_mode(self):
        obj = copy.deepcopy(BASE)
        obj['script'] = {}
        self.rejected(obj, 'AI_SCRIPT_REVIEW_REQUIRED')

    def test_audit_detects_dns_rules_or_group_tampering(self):
        expected, _ = ai.semantic_candidate(c, BASE, 'json', 'Customer Node', ai.GROUP, self.data)
        for change in ('dns', 'rules', 'group'):
            obj = copy.deepcopy(expected)
            if change == 'dns':
                obj['dns']['ipv6'] = True
            elif change == 'rules':
                obj['rules'].insert(0, 'DOMAIN-SUFFIX,openai.com,DIRECT')
            else:
                obj['proxy-groups'][-1]['proxies'].append('DIRECT')
            result = ai.audit(c, c.encode(BASE), c.encode(obj), 'json', 'Customer Node')
            self.assertEqual(result['status'], 'unexpected_policy_or_other_changes')
            self.assertFalse(result['runtime_verified'])

    def test_cli_sanitized_output_and_mismatch_exit(self):
        source = self.root / 'source.json'
        source.write_bytes(c.encode(BASE))
        out = self.root / 'new'
        base_cmd = [sys.executable, str(ROOT / 'src/claude_setup.py')]
        run = subprocess.run(base_cmd + ['ai-route', '--config', str(source), '--node', 'Customer Node', '--out', str(out)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn(SECRET, run.stdout + run.stderr)
        self.assertNotIn('Customer Node', run.stdout + run.stderr)
        candidate = out / 'candidate.json'
        obj = c.load_json(candidate.read_bytes())
        obj['rules'].insert(0, 'MATCH,DIRECT')
        candidate.write_bytes(c.encode(obj))
        run = subprocess.run(base_cmd + ['ai-audit', '--baseline', str(source), '--config', str(candidate), '--node', 'Customer Node'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertNotIn(SECRET, run.stdout + run.stderr)

    def test_baseline_change_during_plan_is_not_reported_success(self):
        source = self.root / 'source.json'
        source.write_bytes(c.encode(BASE))
        real_plan = c.prepare_plan
        def concurrent_change(*args):
            changed = copy.deepcopy(BASE)
            changed['dns']['ipv6'] = True
            source.write_bytes(c.encode(changed))
            return real_plan(*args)
        with patch.object(c, 'prepare_plan', side_effect=concurrent_change):
            with self.assertRaisesRegex(c.SetupError, 'AI_PLAN_INCOMPLETE_REVIEW_OUTPUT'):
                ai.prepare(c, source, 'json', 'Customer Node', self.root / 'out')
        self.assertFalse((self.root / 'out/ai-audit.json').exists())

    def test_source_is_not_replaced_when_output_exists(self):
        source = self.root / 'source.json'
        source.write_bytes(c.encode(BASE))
        with self.assertRaises(c.SetupError):
            ai.prepare(c, source, 'json', 'Customer Node', self.root)
        self.assertEqual(source.read_bytes(), c.encode(BASE))


if __name__ == '__main__':
    unittest.main()
