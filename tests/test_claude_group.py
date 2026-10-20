"""Offline generated policy assertions, with no application or network changes."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ai_routing as ai
import claude_group as cg
import claude_setup as c
import domestic_policy as d
import unified_policy as u
from test_ai_routing import BASE, SHADOW


class ClaudeGroup(unittest.TestCase):
    formats = ('json', 'shadowrocket')

    def original(self, fmt):
        return c.parse_config(SHADOW.encode(), fmt) if fmt == 'shadowrocket' else copy.deepcopy(BASE)

    def build(self, original, fmt, node='Customer Node', group=ai.GROUP, review=None):
        return d.build_semantics(c, original, fmt, node, group, review)

    def test_first_party_only_and_guards_stay_first(self):
        for fmt in self.formats:
            with self.subTest(fmt=fmt):
                original = self.original(fmt)
                result = self.build(original, fmt)
                rules = result['rule' if fmt == 'shadowrocket' else 'rules']
                guards = cg.guarded_rules(ai.catalog(c), fmt, ai.GROUP)
                self.assertEqual(rules[:len(guards)], guards)
                for host in cg.SUFFIXES:
                    self.assertIn('DOMAIN-SUFFIX,' + host + ',AI-ONLY-Claude', rules)
                    self.assertIn('DOMAIN-SUFFIX,' + host + ',REJECT', rules)
                    udp = 'PROTOCOL,UDP' if fmt == 'shadowrocket' else 'NETWORK,udp'
                    reject = 'REJECT-NO-DROP' if fmt == 'shadowrocket' else 'REJECT'
                    self.assertIn('AND,((DOMAIN-SUFFIX,' + host + '),(' + udp + ')),' + reject, rules)
                self.assertIn('DOMAIN-SUFFIX,openai.com,AI-ONLY', rules)
                self.assertIn('DOMAIN,challenges.cloudflare.com,AI-ONLY', rules)
                self.assertEqual(rules[-1], ('FINAL' if fmt == 'shadowrocket' else 'MATCH') + ',AI-ONLY')
                if fmt == 'shadowrocket':
                    self.assertIn('AI-ONLY = select, Customer Node', result['proxy group'])
                    self.assertIn('AI-ONLY-Claude = select, Customer Node', result['proxy group'])
                else:
                    self.assertIn(ai.expected_group('Customer Node', 'AI-ONLY'), result['proxy-groups'])
                    self.assertIn(ai.expected_group('Customer Node', 'AI-ONLY-Claude'), result['proxy-groups'])
                self.assertEqual(original, self.original(fmt))

    def test_upgrade_previous_domestic_block_and_semantic_idempotence(self):
        for fmt in self.formats:
            with self.subTest(fmt=fmt):
                result = self.build(self.original(fmt), fmt)
                old = cg.normalize(c, result, fmt, 'Customer Node', ai.GROUP, ai.catalog(c))
                self.assertEqual(self.build(old, fmt), result)
                self.assertEqual(self.build(result, fmt), result)

    def test_explicit_node_switch_updates_both_groups(self):
        for fmt in self.formats:
            with self.subTest(fmt=fmt):
                original = self.original(fmt)
                if fmt == 'shadowrocket':
                    original['proxy'].append('Other Node = socks5, 192.0.2.11, 1080')
                else:
                    original['proxies'].append({'name': 'Other Node', 'type': 'socks5', 'server': '192.0.2.11', 'port': 1080})
                before = self.build(original, fmt)
                after = self.build(before, fmt, node='Other Node')
                if fmt == 'shadowrocket':
                    self.assertIn('AI-ONLY = select, Other Node', after['proxy group'])
                    self.assertIn('AI-ONLY-Claude = select, Other Node', after['proxy group'])
                else:
                    for group in (ai.GROUP, cg.name(ai.GROUP)):
                        self.assertIn(ai.expected_group('Other Node', group), after['proxy-groups'])
                self.assertEqual(self.build(after, fmt, node='Other Node'), after)

    def test_partial_or_tampered_managed_block_fails(self):
        for fmt in self.formats:
            for mutation in ('missing_rule', 'modified_udp', 'reordered', 'different_node', 'fallback', 'extra_reference', 'duplicate'):
                with self.subTest(fmt=fmt, mutation=mutation):
                    result = self.build(self.original(fmt), fmt)
                    key = 'rule' if fmt == 'shadowrocket' else 'rules'
                    groupkey = 'proxy group' if fmt == 'shadowrocket' else 'proxy-groups'
                    if mutation == 'missing_rule':
                        del result[key][1]
                    elif mutation == 'modified_udp':
                        result[key][0] = result[key][0].rsplit(',', 1)[0] + ',DIRECT'
                    elif mutation == 'reordered':
                        result[key].insert(0, result[key].pop())
                    elif mutation == 'extra_reference':
                        result[key].insert(-1, 'DOMAIN,customer.test,AI-ONLY-Claude')
                    elif mutation == 'duplicate':
                        result[groupkey].append(copy.deepcopy(result[groupkey][-1]))
                    elif fmt == 'shadowrocket':
                        result[groupkey][-1] = 'AI-ONLY-Claude = select, ' + ('Foreign' if mutation == 'different_node' else 'Customer Node, DIRECT')
                    else:
                        result[groupkey][-1]['proxies'] = ['Foreign'] if mutation == 'different_node' else ['Customer Node', 'DIRECT']
                    with self.assertRaises(c.SetupError):
                        self.build(result, fmt)

    def test_unrelated_derived_group_or_node_collision_is_not_overwritten(self):
        for fmt in self.formats:
            for collision in ('group', 'node'):
                with self.subTest(fmt=fmt, collision=collision):
                    original = self.original(fmt)
                    if fmt == 'shadowrocket':
                        key = 'proxy group' if collision == 'group' else 'proxy'
                        original[key].append('AI-ONLY-Claude = ' + ('select, Customer Node' if collision == 'group' else 'socks5, 192.0.2.11, 1080'))
                    else:
                        key = 'proxy-groups' if collision == 'group' else 'proxies'
                        original[key].append(ai.expected_group('Customer Node', 'AI-ONLY-Claude') if collision == 'group' else
                                             {'name': 'AI-ONLY-Claude', 'type': 'socks5', 'server': '192.0.2.11', 'port': 1080})
                    before = copy.deepcopy(original)
                    with self.assertRaises(c.SetupError):
                        self.build(original, fmt)
                    self.assertEqual(original, before)

    def test_custom_group_and_invalid_or_overlong_derived_labels(self):
        for fmt in self.formats:
            with self.subTest(fmt=fmt):
                result = self.build(self.original(fmt), fmt, group='Customer AI')
                self.assertIn('DOMAIN-SUFFIX,claude.ai,Customer AI-Claude', result['rule' if fmt == 'shadowrocket' else 'rules'])
                self.assertEqual(self.build(result, fmt, group='Customer AI'), result)
                for group in ('x' * 155, 'bad,group'):
                    with self.assertRaises(c.SetupError):
                        self.build(self.original(fmt), fmt, group=group)
                with self.assertRaises(c.SetupError):
                    self.build(self.original(fmt), fmt, node='AI-ONLY-Claude')

    def test_original_review_hash_and_exact_candidate_audit(self):
        for fmt in self.formats:
            with self.subTest(fmt=fmt):
                baseline = self.build(self.original(fmt), fmt)
                key = 'rule' if fmt == 'shadowrocket' else 'rules'
                rule = 'DOMAIN,customer.test,DIRECT'
                baseline[key].insert(-1, rule)
                review = {'schema': 'claude-direct-review/1', 'config_semantic_sha256': c.sha(c.encode(baseline)),
                          'entries': [{'rule': rule, 'decision': 'proxy', 'reason': 'Explicit customer policy.'}]}
                candidate = self.build(baseline, fmt, review=review)
                self.assertIn('DOMAIN,customer.test,AI-ONLY', candidate[key])
                render = lambda obj: u.render_shadow(c, SHADOW, obj).encode() if fmt == 'shadowrocket' else c.encode(obj)
                self.assertEqual(d.audit(c, render(baseline), render(candidate), fmt, 'Customer Node', direct_review=review)['status'],
                                 'static_policy_matches')
                candidate[key][1] = 'DOMAIN-SUFFIX,claude.ai,AI-ONLY'
                self.assertEqual(d.audit(c, render(baseline), render(candidate), fmt, 'Customer Node', direct_review=review)['status'],
                                 'unexpected_policy_or_other_changes')
                review['config_semantic_sha256'] = '0' * 64
                with self.assertRaisesRegex(c.SetupError, 'DIRECT_REVIEW_BASELINE_MISMATCH'):
                    self.build(baseline, fmt, review=review)

    def test_legacy_unified_policy_keeps_single_group(self):
        for fmt in self.formats:
            with self.subTest(fmt=fmt):
                result = u.build_semantics(c, self.original(fmt), fmt, 'Customer Node', ai.GROUP)
                self.assertNotIn('Claude', str(result))

    def test_shadow_equivalent_selector_spacing_is_recognized(self):
        fmt = 'shadowrocket'
        result = self.build(self.original(fmt), fmt)
        baseline = copy.deepcopy(result)
        baseline['proxy group'] = [x.replace(' = select, ', '=SELECT,') if x.startswith('AI-ONLY') else x
                                   for x in baseline['proxy group']]
        self.assertEqual(self.build(baseline, fmt), result)


if __name__ == '__main__':
    unittest.main()
