import copy
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import domestic_policy as d
import ai_routing as ai
import unified_policy as u
import contact_checks
from test_ai_routing import BASE


class DomesticPolicy(unittest.TestCase):
    def build(self, base=None, **kwargs):
        return d.build_semantics(c, copy.deepcopy(BASE if base is None else base), 'json', 'Customer Node', 'AI-ONLY', **kwargs)

    def test_order_and_no_global_udp_enable(self):
        original = copy.deepcopy(BASE)
        original['rules'].insert(0, 'NETWORK,udp,REJECT')
        result = self.build(original)
        rules = result['rules']
        guards = ai.guarded_rules(ai.catalog(c), 'json', 'AI-ONLY')
        self.assertEqual(rules[:len(guards)], guards)
        self.assertLess(rules.index(d.VIDEO_RULE), rules.index(d.UDP_RULE))
        self.assertLess(rules.index(d.UDP_RULE), rules.index(d.CN_RULE))
        self.assertLess(rules.index(d.CN_RULE), rules.index('GEOIP,CN,DIRECT'))
        self.assertEqual(rules.count(d.UDP_RULE), 1)
        self.assertFalse(result['proxies'][0]['udp'])
        self.assertTrue(result['proxy-groups'][-1]['disable-udp'])
        self.assertFalse(result['ipv6'])

    def test_upgrade_and_idempotence(self):
        old = u.build_semantics(c, BASE, 'json', 'Customer Node', ai.GROUP)
        result = self.build(old)
        self.assertEqual(result, self.build(result))
        self.assertEqual(u.direct_decisions(c, result, 'json')[0], [])

    def test_tampered_provider_or_missing_guard_blocks(self):
        for mutation in ('provider', 'guard'):
            obj = self.build()
            if mutation == 'provider': obj['rule-providers'][d.VIDEO]['payload'].append('+.openai.com')
            else: obj['rules'].remove(d.UDP_RULE)
            with self.assertRaises(c.SetupError): self.build(obj)

    def test_prior_ai_deny_is_not_silently_overridden(self):
        obj = copy.deepcopy(BASE)
        obj['rules'].insert(0, 'DOMAIN-SUFFIX,openai.com,REJECT')
        with self.assertRaisesRegex(c.SetupError, 'EXISTING_DENY_REVIEW'): self.build(obj)

    def test_audit_detects_broad_udp_bypass(self):
        result = self.build()
        result['rules'].insert(0, 'NETWORK,udp,DIRECT')
        self.assertEqual(d.audit(c,c.encode(BASE),c.encode(result),'json','Customer Node')['status'], 'unexpected_policy_or_other_changes')

    def test_foreign_direct_decision_preserved(self):
        obj=copy.deepcopy(BASE); rule='DOMAIN,customer.test,DIRECT';obj['rules'].insert(-1,rule)
        review={'schema':'claude-direct-review/1','config_semantic_sha256':c.sha(c.encode(obj)),
                'entries':[{'rule':rule,'decision':'proxy','reason':'Customer requested proxy.'}]}
        result=self.build(obj,direct_review=review)
        self.assertIn('DOMAIN,customer.test,AI-ONLY',result['rules'])

    def test_package_candidate_readback_and_inline_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'source.json';p.write_bytes(c.encode(BASE))
            d.prepare(c,p,'json','Customer Node',root/'out')
            candidate=root/'out/candidate.json'
            self.assertEqual(d.audit(c,p.read_bytes(),c.read_bytes(candidate),'json','Customer Node')['status'],'static_policy_matches')
            rows,_=contact_checks.scan(c,candidate,'json')
            self.assertTrue(all(row['status']=='已完成' for row in rows))
            rows,_=d.udp_check(c,candidate,'json')
            self.assertTrue(any(row['status']=='未完成' for row in rows))

    def test_shadowrocket_requires_separate_adaptation(self):
        with self.assertRaisesRegex(c.SetupError,'REQUIRES_MIHOMO'):
            d.build_semantics(c,{},'shadowrocket','Node',ai.GROUP)

    def test_explicit_domestic_proxy_decision_cannot_be_overridden(self):
        obj=copy.deepcopy(BASE);rule='DOMAIN,baidu.com,DIRECT';obj['rules'].insert(-1,rule)
        review={'schema':'claude-direct-review/1','config_semantic_sha256':c.sha(c.encode(obj)),
                'entries':[{'rule':rule,'decision':'proxy','reason':'Customer explicitly needs proxy.'}]}
        with self.assertRaisesRegex(c.SetupError,'DOMESTIC_PROXY_EXCEPTION_CONFLICT'):
            self.build(obj,direct_review=review)

    def test_yaml_candidate_contains_actual_snapshot_and_roundtrips(self):
        import yaml
        text=yaml.safe_dump(BASE,allow_unicode=True)
        expected=self.build()
        rendered=u.render_yaml(c,text,expected)
        self.assertEqual(c.parse_config(rendered.encode(),'yaml'),expected)

    def test_domestic_provider_does_not_download(self):
        providers=self.build()['rule-providers']
        for key in (d.VIDEO,d.CN):
            self.assertEqual(set(providers[key]),{'type','behavior','payload'})
        self.assertIn('+.bilibili.com',providers[d.VIDEO]['payload'])
        self.assertNotIn('+.alicdn.com',providers[d.VIDEO]['payload'])
        self.assertIn('+.baidu.com',providers[d.CN]['payload'])
