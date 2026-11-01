"""Synthetic offline DIRECT classification; never use customer configuration."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import domestic_policy
import unified_policy as unified


class DirectClassification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'baseline.json'

    def template(self, rules, **options):
        original = {'rules': rules}
        self.source.write_bytes(c.encode(original))
        return original, unified.direct_template(c, self.source, 'json', **options)

    def classify(self, rule):
        return unified.classify_direct_rule(rule)['classification']

    def test_default_template_is_unchanged_and_deduplicated(self):
        rule = 'DOMAIN,unknown.example,DIRECT'
        original, review = self.template([rule, rule, 'GEOIP,CN,DIRECT', 'IP-CIDR,10.0.0.0/8,DIRECT'])
        self.assertEqual(review, {
            'schema': 'claude-direct-review/1', 'config_semantic_sha256': c.sha(c.encode(original)),
            'entries': [{'rule': rule, 'decision': 'pending', 'reason': ''}],
        })

    def test_exact_and_suffix_semantics_are_not_broadened(self):
        index = (frozenset({'only.exact.example'}), frozenset({'suffix.example'}))
        with patch.object(unified, '_domestic_domain_index', return_value=index):
            for rule in ('DOMAIN,only.exact.example,DIRECT', 'DOMAIN,suffix.example,DIRECT',
                         'DOMAIN,child.suffix.example,DIRECT', 'DOMAIN-SUFFIX,child.suffix.example,DIRECT',
                         'DOMAIN-SUFFIX,SUFFIX.EXAMPLE.,DIRECT'):
                with self.subTest(rule=rule):
                    self.assertEqual(self.classify(rule), 'known_domestic')
            for rule in ('DOMAIN-SUFFIX,only.exact.example,DIRECT',
                         'DOMAIN,child.only.exact.example,DIRECT', 'DOMAIN-SUFFIX,example,DIRECT',
                         'DOMAIN,evilsuffix.example,DIRECT', 'DOMAIN,suffix.example.evil,DIRECT',
                         'DOMAIN-KEYWORD,suffix.example,DIRECT', 'DOMAIN,*.suffix.example,DIRECT',
                         'DOMAIN,suffix.example,DIRECT,unexpected', 'DOMAIN,suffix.example,Proxy'):
                with self.subTest(rule=rule):
                    self.assertEqual(self.classify(rule), 'pending_review')

    def test_bundled_snapshot_is_checked_and_index_preserves_exact_entries(self):
        unified._domestic_domain_index.cache_clear()
        self.addCleanup(unified._domestic_domain_index.cache_clear)
        with patch.object(domestic_policy, 'snapshot', wraps=domestic_policy.snapshot) as snapshot:
            exact, suffixes = unified._domestic_domain_index()
            self.assertEqual(self.classify('DOMAIN,child.baidu.com,DIRECT'), 'known_domestic')
            self.assertEqual(self.classify('DOMAIN-SUFFIX,bilibili.com,DIRECT'), 'known_domestic')
            self.assertIn('ykimg.alicdn.com', exact)
            self.assertNotIn('ykimg.alicdn.com', suffixes)
            self.assertEqual(snapshot.call_count, 1)

    def test_local_namespaces_and_whole_local_networks_only(self):
        for rule in ('DOMAIN,localhost,DIRECT', 'DOMAIN,printer.local,DIRECT',
                     'DOMAIN-SUFFIX,LOCALHOST,DIRECT', 'DOMAIN-SUFFIX,local,DIRECT',
                     'IP-CIDR,192.168.1.9/24,DIRECT,no-resolve', 'IP-CIDR,127.0.0.0/8,DIRECT',
                     'IP-CIDR,169.254.1.0/24,DIRECT', 'IP-CIDR6,::1/128,DIRECT',
                     'IP-CIDR6,fd12::/48,DIRECT', 'IP-CIDR6,fe80::/10,DIRECT,no-resolve'):
            with self.subTest(rule=rule):
                self.assertEqual(self.classify(rule), 'reserved_local')
        for rule in ('DOMAIN,localhost.example,DIRECT', 'DOMAIN,local.example,DIRECT',
                     'IP-CIDR,192.168.0.0/15,DIRECT', 'IP-CIDR,192.0.2.0/24,DIRECT',
                     'IP-CIDR,0.0.0.0/0,DIRECT', 'IP-CIDR6,::/0,DIRECT',
                     'IP-CIDR6,2001:db8::/32,DIRECT', 'IP-CIDR6,2606:4700::/32,DIRECT',
                     'IP-CIDR6,::ffff:192.168.0.0/112,DIRECT', 'IP-CIDR6,fe00::/8,DIRECT',
                     'IP-CIDR6,192.168.0.0/16,DIRECT', 'IP-CIDR6,fd12::/48,DIRECT,unexpected'):
            with self.subTest(rule=rule):
                self.assertEqual(self.classify(rule), 'pending_review')

    def test_unknown_stays_pending_and_reasons_are_sanitized(self):
        rules = ['DOMAIN,baidu.com,DIRECT', 'IP-CIDR6,fd12::/48,DIRECT',
                 'DOMAIN,private-customer.example,DIRECT', 'DOMAIN-KEYWORD,customer,DIRECT']
        original, review = self.template(rules, classify_known=True)
        self.assertEqual([entry['decision'] for entry in review['entries']], ['keep', 'keep', 'pending', 'pending'])
        self.assertEqual(review['summary'], {'entry_count': 4, 'known_domestic': 1,
                                             'reserved_local': 1, 'pending_review': 2, 'preserved_existing': 0})
        self.assertFalse(review['intent']['action_approved'])
        self.assertFalse(review['intent']['runtime_verified'])
        for entry in review['entries']:
            self.assertEqual(c.safe_review_text(entry['reason']), entry['reason'])
            self.assertNotIn(entry['rule'].split(',')[1], entry['reason'])
        with self.assertRaisesRegex(c.SetupError, 'DIRECT_REVIEW_INCOMPLETE'):
            unified.direct_decisions(c, original, 'json', review)

    def test_explicit_preservation_is_intent_and_consumable_baseline_bound_review(self):
        rules = ['DOMAIN,baidu.com,DIRECT', 'DOMAIN,customer.example,DIRECT']
        for classify_known in (False, True):
            with self.subTest(classify_known=classify_known):
                original, review = self.template(rules, classify_known=classify_known, preserve_existing=True)
                self.assertTrue(review['intent']['preserve_existing'])
                self.assertFalse(review['intent']['runtime_verified'])
                self.assertFalse(review['intent']['action_approved'])
                self.assertEqual(review['summary']['preserved_existing'], 1 if classify_known else 2)
                self.assertEqual(review['summary']['pending_review'], 0)
                preserved = review['entries'][-1]
                self.assertEqual(preserved['classification'], 'preserved_existing')
                self.assertIn('baseline DIRECT intent', preserved['reason'])
                self.assertIn('not verified', preserved['reason'])
                self.assertEqual(unified.direct_decisions(c, original, 'json', review)[1], dict.fromkeys(rules, 'keep'))
                changed = copy.deepcopy(original)
                changed['unrelated-baseline-setting'] = True
                with self.assertRaisesRegex(c.SetupError, 'DIRECT_REVIEW_BASELINE_MISMATCH'):
                    unified.direct_decisions(c, changed, 'json', review)

    def test_opt_in_review_is_offline_and_does_not_mutate_input_or_files(self):
        original = {'rules': ['DOMAIN,baidu.com,DIRECT', 'DOMAIN,customer.example,DIRECT']}
        before = copy.deepcopy(original)
        raw = c.encode(original)
        self.source.write_bytes(raw)
        files_before = sorted(Path(self.temp.name).iterdir())
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), \
                patch('socket.getaddrinfo', side_effect=AssertionError('DNS forbidden')), \
                patch('subprocess.run', side_effect=AssertionError('process forbidden')), \
                patch.object(c, 'write_new', side_effect=AssertionError('write forbidden')), \
                patch.object(Path, 'write_bytes', side_effect=AssertionError('write forbidden')), \
                patch.object(Path, 'write_text', side_effect=AssertionError('write forbidden')):
            review = unified.direct_template(c, self.source, 'json', classify_known=True, preserve_existing=True)
            unified.direct_decisions(c, original, 'json', review)
        self.assertEqual(original, before)
        self.assertEqual(self.source.read_bytes(), raw)
        self.assertEqual(sorted(Path(self.temp.name).iterdir()), files_before)


if __name__ == '__main__':
    unittest.main()
