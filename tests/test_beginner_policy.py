"""Synthetic offline inputs only. No actual network configuration or app launch."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import ai_routing as ai
import unified_policy as unified
import contact_checks as contact
import ipv6_scope
import dns_readiness as ready
import readiness_lifecycle as life
from test_ai_routing import BASE, SHADOW


class UnifiedPolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, value=BASE, fmt='json'):
        return unified.build_semantics(c, copy.deepcopy(value), fmt, 'Customer Node', 'AI-ONLY')

    def test_same_proxy_for_ai_foreign_and_preserve_direct_and_denies(self):
        result = self.build()
        self.assertEqual(result['rules'][0], BASE['rules'][0])
        self.assertIn('GEOIP,CN,DIRECT', result['rules'])
        self.assertEqual(result['rules'][-1], 'MATCH,AI-ONLY')
        self.assertEqual(result['proxy-groups'][-1]['proxies'], ['Customer Node'])
        self.assertIn('DOMAIN-SUFFIX,openai.com,AI-ONLY', result['rules'])
        self.assertFalse(result['ipv6']); self.assertFalse(result['dns']['ipv6'])
        self.assertEqual(result['proxies'][0]['ip-version'], 'ipv4')
        self.assertIn(unified.V6_RULE, result['rules'])
        self.assertEqual(result['proxies'][0]['password'], BASE['proxies'][0]['password'])

    def test_all_named_proxy_actions_are_unified_including_rule_sets(self):
        original = copy.deepcopy(BASE)
        original['rules'].insert(-1, 'RULE-SET,foreign-sites,Foreign,no-resolve')
        original['rules'].insert(-1, 'DOMAIN,other.example,Customer Node')
        result = self.build(original)
        self.assertIn('RULE-SET,foreign-sites,AI-ONLY,no-resolve', result['rules'])
        self.assertIn('DOMAIN,other.example,AI-ONLY', result['rules'])

    def test_migration_from_old_managed_ai_rules_and_idempotence(self):
        old, _ = ai.semantic_candidate(c, BASE, 'json', 'Customer Node', 'AI-ONLY', ai.catalog(c))
        result = self.build(old)
        self.assertEqual(result, self.build(result))
        self.assertEqual(result['rules'].count(unified.V6_RULE), 1)
        self.assertEqual(sum(g['name'] == 'AI-ONLY' for g in result['proxy-groups']), 1)

    def test_foreign_direct_requires_explicit_review_and_can_be_proxied(self):
        obj = copy.deepcopy(BASE)
        rule = 'DOMAIN-SUFFIX,bbc.co.uk,DIRECT'
        obj['rules'].insert(-1, rule)
        with self.assertRaisesRegex(c.SetupError, 'UNIFIED_DIRECT_REVIEW_REQUIRED'):
            self.build(obj)
        review = {'schema':'claude-direct-review/1', 'config_semantic_sha256':c.sha(c.encode(obj)),
                  'entries':[{'rule':rule,'decision':'proxy','reason':'本轮已确认属于应走统一代理的国外访问。'}]}
        result = unified.build_semantics(c, obj, 'json', 'Customer Node', 'AI-ONLY', review)
        self.assertIn('DOMAIN-SUFFIX,bbc.co.uk,AI-ONLY', result['rules'])
        self.assertNotIn(rule, result['rules'])
        self.assertEqual(unified.audit(c,c.encode(obj),c.encode(result),'json','Customer Node',direct_review=review)['status'],'static_policy_matches')
        review['entries'][0]['decision'] = 'pending'
        with self.assertRaises(c.SetupError): unified.build_semantics(c,obj,'json','Customer Node','AI-ONLY',review)

    def test_incomplete_shadow_node_has_fixed_error(self):
        obj=c.parse_config(SHADOW.replace('socks5, 192.0.2.10, 1080, password=CUSTOMER_SECRET_NEVER_STDOUT','socks5').encode(),'shadowrocket')
        with self.assertRaisesRegex(c.SetupError,'UNIFIED_NODE_SERVER_REQUIRED'):
            self.build(obj,'shadowrocket')

    def test_ipv6_literal_dns_requires_review(self):
        obj = copy.deepcopy(BASE)
        obj['dns']['nameserver'] = ['https://[2001:db8::1]/dns-query']
        with self.assertRaisesRegex(c.SetupError, 'UNIFIED_IPV6_DNS_REVIEW_REQUIRED'):
            self.build(obj)

    def test_managed_ai_group_can_migrate_to_new_explicit_node(self):
        old, _ = ai.semantic_candidate(c, BASE, 'json', 'Customer Node', 'AI-ONLY', ai.catalog(c))
        old['proxies'].append({'name':'New Node','type':'http','server':'192.0.2.90','port':8080})
        result = unified.build_semantics(c, old, 'json', 'New Node', 'AI-ONLY')
        self.assertEqual(result['proxy-groups'][-1]['proxies'], ['New Node'])
        self.assertEqual(result['rules'][-1], 'MATCH,AI-ONLY')
        self.assertEqual(result['proxies'][0], old['proxies'][0])

    def test_ipv6_literal_node_requires_review(self):
        obj = copy.deepcopy(BASE); obj['proxies'][0]['server'] = '2001:db8::1'
        with self.assertRaisesRegex(c.SetupError, 'UNIFIED_IPV6_NODE_REVIEW_REQUIRED'):
            self.build(obj)

    def test_audit_rejects_ipv4_prefer_direct_fallback_or_gui_ipv6_override(self):
        expected = self.build()
        for key in ('mode', 'ipv6', 'node', 'rules'):
            result = copy.deepcopy(expected)
            if key == 'mode': result['mode'] = 'global'
            elif key == 'ipv6': result['ipv6'] = True
            elif key == 'node': result['proxies'][0]['ip-version'] = 'ipv4-prefer'
            else: result['rules'][-1] = 'MATCH,DIRECT'
            checked = unified.audit(c, c.encode(BASE), c.encode(result), 'json', 'Customer Node')
            self.assertEqual(checked['status'], 'unexpected_policy_or_other_changes')

    def test_yaml_and_shadow_render_and_private_diff(self):
        import yaml
        for fmt in ('yaml', 'shadowrocket'):
            with self.subTest(fmt=fmt):
                raw = ('# header remains\n' + yaml.safe_dump(BASE, sort_keys=False)) if fmt == 'yaml' else SHADOW
                raw = raw.replace('\n', '\r\n').encode()
                source = self.root / ('source.' + ('yaml' if fmt == 'yaml' else 'conf')); source.write_bytes(raw)
                output = self.root / fmt
                result = unified.prepare(c, source, fmt, 'Customer Node', output)
                self.assertTrue(result['unified_proxy_rules']); self.assertEqual(source.read_bytes(), raw)
                candidate = next(output.glob('candidate.*'))
                actual = c.parse_config(candidate.read_bytes(), fmt)
                if fmt == 'yaml':
                    self.assertIn(b'# header remains', candidate.read_bytes())
                    self.assertFalse(actual['dns']['ipv6'])
                else:
                    self.assertIn('ipv6 = false', actual['general'])
                    self.assertEqual(actual['rule'][-1], 'FINAL,AI-ONLY')
                self.assertEqual(unified.audit(c, raw, candidate.read_bytes(), fmt, 'Customer Node')['status'], 'static_policy_matches')
                self.assertTrue((output / 'plan/diff.private.txt').exists())

    def test_unchanged_candidate_does_not_need_reapply(self):
        source = self.root / 'current.json'; source.write_bytes(c.encode(self.build()))
        result = unified.prepare(c, source, 'json', 'Customer Node', self.root / 'same')
        self.assertFalse(result['content_changed'])


class ImplicitContacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.config = self.root / 'config.json'

    def tearDown(self): self.temp.cleanup()

    def scan(self, obj):
        self.config.write_bytes(c.encode(obj)); return contact.scan(c, self.config)

    def test_ai_health_check_blocks_before_activation_and_preserves_input(self):
        obj = copy.deepcopy(BASE)
        obj['proxy-groups'].append({'name': 'Auto', 'type': 'url-test', 'proxies': ['Customer Node'], 'url': 'https://claude.ai/'})
        rows, evidence = self.scan(obj)
        self.assertTrue(any(r['status'] == '未完成' for r in rows))
        self.assertEqual(evidence[0]['category'], 'ai_target')
        self.assertEqual(c.load_json(self.config.read_bytes()), obj)
        self.assertNotIn('Customer Node', json.dumps(rows))

    def test_non_ai_url_is_not_claimed_runtime_proof(self):
        rows, _ = self.scan({'proxy-groups': [{'type': 'url-test', 'url': 'https://www.gstatic.com/generate_204'}]})
        self.assertTrue(all(r['status'] == '已完成' for r in rows))
        self.assertIn('批准', rows[0]['next_step'])

    def test_remote_provider_and_script_need_review_even_when_non_ai(self):
        for obj in ({'proxy-providers': {'remote': {'url': 'https://example.test/sub'}}}, {'script': {'code': 'arbitrary'}}):
            rows, _ = self.scan(obj)
            self.assertTrue(any(r['status'] == '未完成' for r in rows))

    def test_ai_dns_upstream_or_node_address_blocked(self):
        for obj in ({'dns': {'nameserver': ['https://api.openai.com/dns-query']}}, {'proxies': [{'server': 'api.anthropic.com'}]}):
            rows, _ = self.scan(obj)
            self.assertTrue(any(r['status'] == '未完成' for r in rows))

    def test_browser_install_login_actions_need_current_record(self):
        self.config.write_bytes(c.encode(BASE))
        for action in contact.SERVICE_ACTIONS:
            rows, _ = contact.gate(c, action, self.config, 'json', None, 'http://127.0.0.1:7890')
            self.assertEqual(rows[0]['status'], '未完成')

    def test_unknown_shadow_application_options_not_auto_pass(self):
        source = self.root / 'shadow.conf'; source.write_text(SHADOW, encoding='utf-8')
        rows, _ = contact.scan(c, source, 'shadowrocket')
        self.assertTrue(any(r['status'] == '未完成' for r in rows))


class IPv6Readback(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Native adapter reader on Windows CI')
    def test_native_windows_reader_is_executable_without_policy_bypass(self):
        name = c.run_fixed(['powershell.exe','-NoProfile','-NonInteractive','-Command', '[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-NetAdapterBinding -ComponentID ms_tcpip6 | Select-Object -First 1 -ExpandProperty Name'])
        self.assertTrue(name)
        rows, evidence = ipv6_scope.check(c, [name])
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(evidence[0]['observed'], dict)
        self.assertIsInstance(evidence[0]['observed']['enabled'], bool)

    def test_exact_mac_off_not_linklocal_or_missing(self):
        for state, expected in [('Off', '已完成'), ('Automatic', '未完成'), ('Link-local only', '未完成')]:
            with patch.object(ipv6_scope.platform, 'system', return_value='Darwin'), patch.object(c, 'run_fixed', return_value='IPv6: '+state+'\n') as command:
                rows, _ = ipv6_scope.check(c, ['Wi-Fi'])
                self.assertEqual(rows[0]['status'], expected)
                self.assertEqual(command.call_args.args[0], ['/usr/sbin/networksetup', '-getinfo', 'Wi-Fi'])

    def test_windows_binding_disabled_and_exact_target(self):
        for enabled in (True, False):
            raw = json.dumps({'name': 'Wi-Fi', 'enabled': enabled, 'description': 'Synthetic'})
            with patch.object(ipv6_scope.platform, 'system', return_value='Windows'), patch.object(c, 'run_fixed', return_value=raw):
                rows, _ = ipv6_scope.check(c, ['Wi-Fi'])
                self.assertEqual(rows[0]['status'], '未完成' if enabled else '已完成')

    def test_wildcard_scope_is_rejected_without_command(self):
        with patch.object(c, 'run_fixed') as command:
            for name in ('*', 'Wi-*', '?', '-AllBindings'):
                with self.assertRaises(c.SetupError): ipv6_scope.check(c, [name])
            command.assert_not_called()

    def test_old_receipt_and_enabled_ipv6_do_not_unlock(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'current.json'; config.write_text('{}')
            receipt = Path(d) / 'ready.json'
            receipt.write_bytes(c.encode({'schema': 'claude-dns-readiness/1'}))
            self.assertFalse(ready.check(c, receipt, config)[0])
            with patch.object(life, 'native_state', return_value={'dns_identity_sha256': 'a'*64, 'values': {}}), patch.object(ipv6_scope, 'check', return_value=([{'status':'未完成'}], [])):
                with self.assertRaisesRegex(c.SetupError, 'IPV6_SCOPE_NOT_OFF'):
                    ready.record(c, config, None, Path(d)/'new.json', True, True, True, '已做本机测试。', 'http://127.0.0.1:7890', ['Wi-Fi'])



if __name__ == '__main__': unittest.main()
