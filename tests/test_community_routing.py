"""Community scope, upgrade compatibility and fail-closed regression tests."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ai_routing as ai
import claude_group as cg
import claude_setup as c
import community_routing as community
import domestic_policy as d
from test_ai_routing import BASE, SHADOW


class CommunityRouting(unittest.TestCase):
    def original(self, fmt):
        return c.parse_config(SHADOW.encode(), fmt) if fmt == 'shadowrocket' else copy.deepcopy(BASE)

    def test_full_scope_offline_and_no_dynamic_database_rules(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
            pairs = community.matches()
            for pair in [('DOMAIN-SUFFIX', 'clau.de'), ('DOMAIN-SUFFIX', 'claudemcpclient.com'),
                         ('DOMAIN-SUFFIX', 'intercom.io'), ('DOMAIN-SUFFIX', 'sentry.io'),
                         ('DOMAIN-SUFFIX', 'statsigapi.net'), ('DOMAIN-KEYWORD', 'sift'),
                         ('DOMAIN-KEYWORD', 'sentry'), ('DOMAIN-KEYWORD', 'datadog'),
                         ('DOMAIN', 'anthropic.auth0.com'), ('DOMAIN', 'cdn.usefathom.com'),
                         ('DOMAIN', 'time.apple.com'), ('DOMAIN', 'time.windows.com'),
                         ('DOMAIN', 'ntp.aliyun.com'), ('DOMAIN-SUFFIX', 'ntp.nict.jp'),
                         ('IP-CIDR', '160.79.104.0/21'), ('IP-CIDR', '160.79.104.0/23')]:
                self.assertIn(pair, pairs)
            self.assertGreater(len(pairs), 100)
            for fmt in ('json', 'shadowrocket'):
                result = d.build_semantics(c, self.original(fmt), fmt, 'Customer Node', ai.GROUP)
                rules = result['rule' if fmt == 'shadowrocket' else 'rules']
                block = community.guarded_rules(fmt, 'AI-ONLY-Claude')
                self.assertEqual(rules[:len(block)], block)
                self.assertFalse(any(r.startswith(('GEOSITE', 'IP-ASN')) for r in rules))
                self.assertFalse(any('2607:6bc0' in r for r in rules))
                self.assertEqual(len(block), len(pairs) * 3)
                self.assertTrue(all(community.coverage(c, result, fmt, 'Customer Node', ai.GROUP)[i]['status'] == '已完成'
                                    for i in range(len(pairs))))

    def test_exact_previous_v010_upgrade_and_idempotence(self):
        for fmt in ('json', 'shadowrocket'):
            original = self.original(fmt)
            with patch.object(cg, 'guarded_rules', cg.legacy_guarded_rules):
                old = d.build_semantics(c, original, fmt, 'Customer Node', 'Chosen AI')
            new = d.build_semantics(c, old, fmt, 'Customer Node', 'Chosen AI')
            self.assertEqual(new, d.build_semantics(c, original, fmt, 'Customer Node', 'Chosen AI'))
            self.assertEqual(new, d.build_semantics(c, new, fmt, 'Customer Node', 'Chosen AI'))

    def test_each_partial_extension_or_binding_mutation_is_rejected(self):
        for fmt in ('json', 'shadowrocket'):
            result = d.build_semantics(c, self.original(fmt), fmt, 'Customer Node', ai.GROUP)
            key = 'rule' if fmt == 'shadowrocket' else 'rules'
            for index in (0, 1, 2, len(community.guarded_rules(fmt, 'AI-ONLY-Claude')) - 1):
                for action in ('remove', 'direct'):
                    broken = copy.deepcopy(result)
                    if action == 'remove':
                        del broken[key][index]
                    else:
                        broken[key][index] = 'DOMAIN,unrelated.test,DIRECT'
                    with self.assertRaises(c.SetupError):
                        d.build_semantics(c, broken, fmt, 'Customer Node', ai.GROUP)

    def test_enterprise_shared_keyword_and_ntp_denies_require_review(self):
        for fmt in ('json', 'shadowrocket'):
            for value in ('sentry.io', 'customer-sift.example', 'time.apple.com', 'clau.de'):
                original = self.original(fmt)
                original['rule' if fmt == 'shadowrocket' else 'rules'].insert(0, 'DOMAIN,' + value + ',REJECT')
                with self.assertRaisesRegex(c.SetupError, 'DOMESTIC_EXISTING_DENY_REVIEW_REQUIRED'):
                    d.build_semantics(c, original, fmt, 'Customer Node', ai.GROUP)

    def test_pinned_raw_checksums_and_asn_time_are_recorded(self):
        data = community.snapshot()
        for source in list(data['files'].values()) + [data['asn']]:
            self.assertEqual(hashlib.sha256(source['text'].encode()).hexdigest(), source['sha256'])
        scope = community.audit_scope()
        self.assertFalse(scope['asn_live_coverage_verified'])
        self.assertFalse(scope['requires_runtime_database_download'])
        self.assertEqual(scope['ntp_udp'], 'rejected')
        self.assertTrue(scope['asn_snapshot_end'])

    def test_coverage_rejects_ambiguous_duplicate_selector_bindings(self):
        for fmt in ('json', 'shadowrocket'):
            result = d.build_semantics(c, self.original(fmt), fmt, 'Customer Node', ai.GROUP)
            key = 'proxy group' if fmt == 'shadowrocket' else 'proxy-groups'
            result[key].append('AI-ONLY-Claude = select, DIRECT' if fmt == 'shadowrocket' else
                               {'name': 'AI-ONLY-Claude', 'type': 'select', 'proxies': ['DIRECT']})
            rows = community.coverage(c, result, fmt, 'Customer Node', ai.GROUP)
            self.assertTrue(all(row['status'] == '未完成' for row in rows))

    def test_coverage_requires_concrete_local_node_rule_mode_and_no_chain(self):
        for fmt in ('json', 'shadowrocket'):
            for mutation in ('missing_node', 'chain', 'direct_mode'):
                if fmt == 'shadowrocket' and mutation == 'direct_mode':
                    continue  # Native Shadowrocket mode is an external application state.
                with self.subTest(fmt=fmt, mutation=mutation):
                    result = d.build_semantics(c, self.original(fmt), fmt, 'Customer Node', ai.GROUP)
                    if mutation == 'missing_node':
                        result['proxy' if fmt == 'shadowrocket' else 'proxies'] = []
                    elif mutation == 'direct_mode':
                        result['mode'] = 'direct'
                    elif fmt == 'shadowrocket':
                        result['proxy'][0] += ', underlying-proxy=Foreign'
                    else:
                        result['proxies'][0]['dialer-proxy'] = 'Foreign'
                    rows = community.coverage(c, result, fmt, 'Customer Node', ai.GROUP)
                    self.assertTrue(all(row['status'] == '未完成' for row in rows))
                    self.assertIn('结构', rows[0]['reason'])

    def test_coverage_respects_whole_config_summary_failures(self):
        from unified_policy import render_shadow
        for fmt in ('json', 'shadowrocket'):
            for mutation in ('unknown_reference', 'early_catchall', 'cycle', 'duplicate'):
                with self.subTest(fmt=fmt, mutation=mutation):
                    result = d.build_semantics(c, self.original(fmt), fmt, 'Customer Node', ai.GROUP)
                    key = 'rule' if fmt == 'shadowrocket' else 'rules'
                    groupkey = 'proxy group' if fmt == 'shadowrocket' else 'proxy-groups'
                    if mutation == 'unknown_reference':
                        result[key].insert(-1, 'DOMAIN,unrelated.test,Missing Node')
                    elif mutation == 'early_catchall':
                        result[key].insert(-1, ('FINAL' if fmt == 'shadowrocket' else 'MATCH') + ',AI-ONLY')
                    elif fmt == 'shadowrocket':
                        result[groupkey].append('Extra = select, Extra' if mutation == 'cycle' else result[groupkey][0])
                    else:
                        result[groupkey].append({'name': 'Extra', 'type': 'select', 'proxies': ['Extra']}
                                                if mutation == 'cycle' else copy.deepcopy(result[groupkey][0]))
                    raw = render_shadow(c, SHADOW, result).encode() if fmt == 'shadowrocket' else c.encode(result)
                    summary = c.config_summary(raw, fmt)
                    rows = community.coverage(c, result, fmt, 'Customer Node', ai.GROUP, summary=summary)
                    self.assertTrue(all(row['status'] == '未完成' for row in rows))


if __name__ == '__main__':
    unittest.main()
