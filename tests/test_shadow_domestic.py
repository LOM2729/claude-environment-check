"""Synthetic offline Shadowrocket candidates; no native client or network validation."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import ai_routing as ai
import claude_group
import claude_setup as c
import domestic_policy as d
import unified_policy as u
from test_ai_routing import BASE, SHADOW, SECRET

UDP = 'AND,((PROTOCOL,UDP),(PROTOCOL,UDP)),REJECT-NO-DROP'
V6 = 'IP-CIDR,::/0,REJECT,no-resolve'


def native_domains(payload):
    return [('DOMAIN-SUFFIX,' + value[2:] if value.startswith('+.') else 'DOMAIN,' + value) + ',DIRECT'
            for value in payload]


class ShadowDomestic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = c.parse_config(SHADOW.encode(), 'shadowrocket')

    def build(self, original=None, **kwargs):
        return d.build_semantics(c, copy.deepcopy(self.original if original is None else original),
                                 'shadowrocket', 'Customer Node', ai.GROUP, **kwargs)

    def test_full_snapshot_order_and_original_tail(self):
        result = self.build()
        guards = claude_group.guarded_rules(ai.catalog(c), 'shadowrocket', ai.GROUP)
        video = native_domains(d.snapshot()[d.VIDEO]['payload'])
        domestic = native_domains(d.snapshot()[d.CN]['payload'])
        expected = guards + [V6, 'DOMAIN,blocked.test,REJECT'] + video + [UDP] + domestic
        expected += ['GEOIP,CN,DIRECT', 'FINAL,AI-ONLY']
        self.assertEqual(result['rule'], expected)
        self.assertEqual(result['rule'].count(UDP), 1)

    def test_no_mihomo_specific_syntax_or_runtime_claim(self):
        result = self.build()
        self.assertEqual(result['proxy'], self.original['proxy'])
        self.assertIn('AI-ONLY = select, Customer Node', result['proxy group'])
        self.assertIn('ipv6 = false', result['general'])
        self.assertIn('udp-policy-not-supported-behaviour = REJECT', result['general'])
        self.assertNotIn('rule-providers', result)
        for rule in result['rule']:
            self.assertFalse(rule.startswith(('NETWORK,', 'IP-CIDR6,', 'RULE-SET,')), rule)
            self.assertNotIn('(NETWORK,', rule)

    def test_video_and_domestic_semantics_match_clash_snapshot(self):
        shadow = self.build()['rule']
        clash = d.build_semantics(c, BASE, 'json', 'Customer Node', ai.GROUP)
        for key, samples in ((d.VIDEO, ('+.bilibili.com', '+.acgvideo.com')),
                             (d.CN, ('+.baidu.com',))):
            for domain in samples:
                self.assertIn(domain, clash['rule-providers'][key]['payload'])
                translated = native_domains([domain])[0]
                self.assertIn(translated, shadow)
                if key == d.VIDEO:
                    self.assertLess(shadow.index(translated), shadow.index(UDP))
                else:
                    self.assertGreater(shadow.index(translated), shadow.index(UDP))
        self.assertNotIn('DOMAIN-SUFFIX,alicdn.com,DIRECT',
                         shadow[:shadow.index(UDP)])

    def test_old_unified_migrates_and_is_idempotent(self):
        old = u.build_semantics(c, self.original, 'shadowrocket', 'Customer Node', ai.GROUP)
        updated = self.build(old)
        self.assertEqual(updated, self.build(updated))
        self.assertEqual(updated['rule'].count(V6), 1)
        self.assertNotIn(u.V6_RULE, updated['rule'])

    def test_managed_domains_do_not_generate_mass_customer_review(self):
        result = self.build()
        unknown, _ = u.direct_decisions(c, result, 'shadowrocket')
        self.assertEqual(unknown, [])
        result['rule'].insert(-1, 'DOMAIN,customer-private.test,DIRECT')
        unknown, _ = u.direct_decisions(c, result, 'shadowrocket')
        self.assertEqual(unknown, ['DOMAIN,customer-private.test,DIRECT'])

    def test_existing_unconditional_udp_block_relocated(self):
        for old_guard in (UDP, 'PROTOCOL,UDP,REJECT'):
            with self.subTest(old_guard=old_guard):
                original = copy.deepcopy(self.original)
                original['rule'].insert(0, old_guard)
                result = self.build(original)['rule']
                self.assertEqual(result.count(UDP), 1)
                self.assertNotIn('PROTOCOL,UDP,REJECT', result)
                self.assertLess(result.index('DOMAIN-SUFFIX,bilibili.com,DIRECT'), result.index(UDP))

    def test_tampered_managed_rules_are_not_silently_trusted(self):
        for mutation in ('remove_udp', 'change_video', 'change_ai'):
            with self.subTest(mutation=mutation):
                result = self.build()
                if mutation == 'remove_udp':
                    result['rule'].remove(UDP)
                elif mutation == 'change_video':
                    index = result['rule'].index('DOMAIN-SUFFIX,bilibili.com,DIRECT')
                    result['rule'][index] = 'DOMAIN-SUFFIX,openai.com,DIRECT'
                else:
                    result['rule'][0] = result['rule'][0].replace('REJECT-NO-DROP', 'DIRECT')
                with self.assertRaises(c.SetupError):
                    self.build(result)

    def test_existing_ai_deny_requires_review(self):
        original = copy.deepcopy(self.original)
        original['rule'].insert(0, 'DOMAIN-SUFFIX,openai.com,REJECT')
        with self.assertRaises(c.SetupError):
            self.build(original)

    def test_unsupported_node_ipv6_rejected(self):
        original = copy.deepcopy(self.original)
        original['proxy'] = [x.replace('192.0.2.10', '[2001:db8::1]') for x in original['proxy']]
        with self.assertRaises(c.SetupError):
            self.build(original)

    def test_explicit_domestic_proxy_exception_not_overridden(self):
        original = copy.deepcopy(self.original)
        rule = 'DOMAIN,baidu.com,DIRECT'
        original['rule'].insert(-1, rule)
        review = {'schema': 'claude-direct-review/1', 'config_semantic_sha256': c.sha(c.encode(original)),
                  'entries': [{'rule': rule, 'decision': 'proxy', 'reason': 'Explicit customer policy.'}]}
        with self.assertRaisesRegex(c.SetupError, 'DOMESTIC_PROXY_EXCEPTION_CONFLICT'):
            self.build(original, direct_review=review)

    def test_cli_conf_candidate_comments_and_tampered_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.conf'
            source.write_text(SHADOW, encoding='utf-8')
            output = root / 'prepared'
            run = subprocess.run([sys.executable, str(ROOT / 'src/claude_setup.py'), 'ai-route',
                                  '--config', str(source), '--node', 'Customer Node', '--out', str(output)],
                                 capture_output=True, text=True, timeout=90)
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            self.assertNotIn(SECRET, run.stdout + run.stderr)
            self.assertFalse(json.loads(run.stdout)['runtime_verified'])
            candidate = output / 'candidate.conf'
            data = candidate.read_bytes()
            self.assertTrue(data.startswith(source.read_bytes().splitlines(keepends=True)[0]))
            self.assertEqual(source.read_text(encoding='utf-8'), SHADOW)
            self.assertEqual(d.audit(c, source.read_bytes(), data, 'shadowrocket', 'Customer Node')['status'],
                             'static_policy_matches')
            self.assertEqual(c.verify_readback(output / 'plan', candidate, True)['status'], 'candidate_bytes_match')
            tampered = data.replace(UDP.encode(), b'AND,((PROTOCOL,UDP),(PROTOCOL,UDP)),DIRECT')
            self.assertNotEqual(data, tampered)
            self.assertEqual(d.audit(c, source.read_bytes(), tampered, 'shadowrocket', 'Customer Node')['status'],
                             'unexpected_policy_or_other_changes')

    def test_udp_inventory_retains_host_validation_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'candidate.conf'
            path.write_text(u.render_shadow(c, SHADOW, self.build()), encoding='utf-8')
            rows, hits = d.udp_check(c, path, 'shadowrocket')
            self.assertTrue(any('PROTOCOL,UDP' in str(hit) for hit in hits))
            self.assertTrue(any(row['status'] == '未完成' for row in rows))


if __name__ == '__main__':
    unittest.main()
