"""Offline contract tests for keepalive candidates and truthful public reporting."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import connection_reuse as cr


class ConnectionReuse(unittest.TestCase):
    def config(self):
        return {'mode': 'rule', 'proxies': [{'name': 'PRIVATE_NODE', 'type': 'trojan',
                'server': 'private.example', 'password': 'PRIVATE_PASSWORD', 'port': 443,
                'smux': {'enabled': False}, 'client-fingerprint': 'firefox'}],
                'proxy-groups': [], 'rules': ['MATCH,DIRECT'], 'dns': {'enable': True}}

    def prepare(self, obj=None, fmt='json', core='mihomo', version='1.19.32', node=None, chrome=False):
        return cr.build(c, self.config() if obj is None else obj, fmt, core=core, version=version,
                        node=node, chrome=chrome)

    def test_only_three_global_fields_change_and_input_is_immutable(self):
        before = self.config()
        snapshot = copy.deepcopy(before)
        for fmt in ('json', 'yaml'):
            candidate, rows = self.prepare(before, fmt)
            self.assertEqual(before, snapshot)
            self.assertEqual(set(candidate) - set(before), set(cr.TIMERS) | {'disable-keep-alive'})
            for key in before:
                self.assertEqual(candidate[key], before[key])
            self.assertIs(candidate['disable-keep-alive'], False)
            self.assertEqual([candidate[k] for k in cr.TIMERS], [15, 15])
            self.assertEqual(self.prepare(candidate, fmt)[0], candidate)
            self.assertEqual(next(r for r in rows if r['id'] == 'connection_tcp_keepalive')['status'], '已完成')

    def test_disabled_and_invalid_timers_are_concrete_candidate_not_runtime_pass(self):
        for value in (None, True, False, 0, -1, '15', 1.5, 2147483648):
            with self.subTest(value=value):
                obj = dict(self.config(), **{'disable-keep-alive': True, 'keep-alive-idle': value})
                rows = cr.audit(c, obj, 'json', core='mihomo', version='1.19.32')
                self.assertEqual(next(r for r in rows if r['id'] == 'connection_tcp_keepalive')['status'], '未完成')
                candidate, _ = self.prepare(obj)
                self.assertEqual(candidate['keep-alive-idle'], 15)
                self.assertIs(candidate['disable-keep-alive'], False)

    def test_preserve_valid_positive_timer_policy(self):
        obj = dict(self.config(), **{'keep-alive-idle': 120, 'keep-alive-interval': 45})
        candidate, _ = self.prepare(obj)
        self.assertEqual(candidate['keep-alive-idle'], 120)
        self.assertEqual(candidate['keep-alive-interval'], 45)

    def test_unknown_legacy_prerelease_and_future_core_are_unchanged(self):
        for core, version in ((None, None), ('clash', '1.19.32'), ('mihomo', None),
                              ('mihomo', '1.18.10'), ('mihomo', '1.19.0-beta'),
                              ('mihomo', '2.0.0'), ('mihomo', 'Meta 1.19.32'), ('mihomo', ''),
                              ('mihomo', True), ('mihomo', 11932)):
            with self.subTest(core=core, version=version):
                obj = self.config()
                candidate, rows = self.prepare(obj, core=core, version=version)
                self.assertEqual(candidate, obj)
                self.assertEqual(rows[0]['status'], '未完成')
        self.assertEqual(self.prepare(core='Mihomo', version='v1.19.0')[1][0]['status'], '已完成')

    def test_shadowrocket_has_no_invented_fields(self):
        obj = c.parse_config(b'[General]\nipv6 = false\n[Proxy]\nnode = http, 192.0.2.1, 8080\n[Rule]\nFINAL,DIRECT\n', 'shadowrocket')
        candidate, rows = self.prepare(obj, 'shadowrocket')
        self.assertEqual(candidate, obj)
        self.assertIsNot(candidate, obj)
        self.assertTrue(all(r['status'] == '未完成' for r in rows))

    def test_no_http_smux_tls_or_runtime_claims_and_no_secrets(self):
        _, rows = self.prepare()
        report = cr.result(rows)
        encoded = json.dumps(report)
        for value in ('PRIVATE_NODE', 'PRIVATE_PASSWORD', 'private.example', 'firefox'):
            self.assertNotIn(value, encoded)
        for key in ('runtime_verified', 'http_reuse_verified', 'system_settings_changed'):
            self.assertIs(report[key], False)
        for key in ('connection_http_reuse', 'connection_tls_fingerprint', 'connection_multiplex_review'):
            self.assertEqual(next(r for r in rows if r['id'] == key)['status'], '未完成')
        for row in rows:
            self.assertTrue({'id', 'title', 'status', 'reason', 'next_step', 'required'} <= set(row))
            self.assertIn(row['status'], ('已完成', '未完成'))
            self.assertFalse(row['required'])

    def test_provider_and_invalid_proxy_shapes_remain_incomplete(self):
        for obj in ({'proxy-providers': {'secret': {'url': 'PRIVATE_PASSWORD'}}},
                    {'proxies': ['PRIVATE_PASSWORD']}, {'proxy-providers': []}):
            candidate, rows = self.prepare(obj)
            self.assertEqual(next(r for r in rows if r['id'] == 'connection_multiplex_review')['status'], '未完成')
            self.assertNotIn('PRIVATE_PASSWORD', json.dumps(rows))

    def test_invalid_top_level_and_format_are_fixed_errors(self):
        with self.assertRaisesRegex(c.SetupError, 'CONNECTION_CONFIG_OBJECT_REQUIRED'):
            cr.build(c, [], 'json')
        with self.assertRaisesRegex(c.SetupError, 'CONNECTION_FORMAT_UNSUPPORTED'):
            cr.build(c, {}, 'xml')
        with self.assertRaisesRegex(c.SetupError, 'CONNECTION_CHROME_BOOLEAN_REQUIRED'):
            self.prepare(chrome='true')

    def test_chrome_changes_only_selected_node_field_preserves_certificate_pin_and_other_nodes(self):
        for fmt in ('json', 'yaml'):
            for protocol in ('vmess', 'vless', 'trojan', 'anytls'):
                with self.subTest(fmt=fmt, protocol=protocol):
                    obj = self.config()
                    obj['proxies'][0].update({'type': protocol, 'tls': True, 'fingerprint': 'PRIVATE_CERT_PIN'})
                    obj['proxies'].append(dict(obj['proxies'][0], name='OTHER_PRIVATE_NODE'))
                    before = copy.deepcopy(obj)
                    candidate, rows = self.prepare(obj, fmt, node='PRIVATE_NODE', chrome=True)
                    expected = copy.deepcopy(before['proxies'])
                    expected[0]['client-fingerprint'] = 'chrome'
                    self.assertEqual(candidate['proxies'], expected)
                    self.assertEqual(obj, before)
                    self.assertEqual(candidate['proxies'][0]['fingerprint'], 'PRIVATE_CERT_PIN')
                    self.assertEqual(next(r for r in rows if r['id'] == 'connection_tls_fingerprint')['status'], '已完成')
                    for secret in ('PRIVATE_CERT_PIN', 'PRIVATE_NODE', 'OTHER_PRIVATE_NODE', 'private.example'):
                        self.assertNotIn(secret, json.dumps(rows))
                    self.assertEqual(self.prepare(candidate, fmt, node='PRIVATE_NODE', chrome=True)[0], candidate)

    def test_chrome_rejects_unknown_core_node_protocol_and_absent_tls_without_node_mutation(self):
        cases = []
        for protocol in ('ss', 'socks5', 'http', 'wireguard', 'hysteria2'):
            obj = self.config(); obj['proxies'][0]['type'] = protocol
            cases.append((obj, 'PRIVATE_NODE', 'mihomo', '1.19.32'))
        for value in (None, False, 'true', 1):
            for protocol in ('vmess', 'vless'):
                obj = self.config(); obj['proxies'][0].update({'type': protocol, 'tls': value})
                cases.append((obj, 'PRIVATE_NODE', 'mihomo', '1.19.32'))
        cases.extend([(self.config(), None, 'mihomo', '1.19.32'),
                      (self.config(), 'missing', 'mihomo', '1.19.32'),
                      (self.config(), 'PRIVATE_NODE', 'clash', '1.19.32'),
                      (self.config(), 'PRIVATE_NODE', 'mihomo', None)])
        duplicate = self.config(); duplicate['proxies'].append(copy.deepcopy(duplicate['proxies'][0]))
        cases.append((duplicate, 'PRIVATE_NODE', 'mihomo', '1.19.32'))
        group = self.config(); group['proxy-groups'].append({'name': 'PRIVATE_NODE', 'type': 'select'})
        cases.append((group, 'PRIVATE_NODE', 'mihomo', '1.19.32'))
        provider = {'proxies': [], 'proxy-providers': {'secret': {'url': 'PRIVATE_URL'}}}
        cases.append((provider, 'PRIVATE_NODE', 'mihomo', '1.19.32'))
        anytls = self.config(); anytls['proxies'][0]['type'] = 'anytls'
        cases.append((anytls, 'PRIVATE_NODE', 'mihomo', '1.19.31'))
        for obj, node, core, version in cases:
            with self.subTest(node=node, core=core, version=version):
                before = copy.deepcopy(obj)
                candidate, rows = self.prepare(obj, core=core, version=version, node=node, chrome=True)
                self.assertEqual(candidate.get('proxies'), before.get('proxies'))
                self.assertEqual(obj, before)
                self.assertEqual(next(r for r in rows if r['id'] == 'connection_tls_fingerprint')['status'], '未完成')

    def test_without_chrome_keeps_existing_node_fingerprint_and_target_selection_is_not_authority(self):
        candidate, _ = self.prepare(node='PRIVATE_NODE')
        self.assertEqual(candidate['proxies'], self.config()['proxies'])
        for protocol in ('trojan', 'vmess', 'vless'):
            obj = self.config(); obj['proxies'][0].update({'type': protocol, 'tls': True})
            candidate, rows = self.prepare(obj, version='1.19.0', node='PRIVATE_NODE', chrome=True)
            self.assertEqual(candidate['proxies'][0]['client-fingerprint'], 'chrome')
            self.assertFalse(cr.result(rows)['runtime_verified'])

    @unittest.skipUnless(os.environ.get('MIHOMO_BINARY'), 'MIHOMO_BINARY not supplied; native offline validation not run')
    def test_native_core_validates_chrome_candidate_without_starting_network(self):
        for protocol in ('vmess', 'vless', 'trojan', 'anytls'):
            with self.subTest(protocol=protocol):
                proxy = {'name': 'offline-only', 'type': protocol, 'server': '192.0.2.1', 'port': 443}
                if protocol in ('vmess', 'vless'):
                    proxy.update({'uuid': '00000000-0000-4000-8000-000000000001', 'tls': True})
                    if protocol == 'vmess':
                        proxy.update({'alterId': 0, 'cipher': 'auto'})
                else:
                    proxy['password'] = 'synthetic-not-a-secret'
                obj = {'mode': 'rule', 'ipv6': False, 'rules': ['MATCH,REJECT'], 'proxies': [proxy]}
                candidate, _ = self.prepare(obj, node='offline-only', chrome=True)
                with tempfile.TemporaryDirectory(prefix='claude-fingerprint-offline-') as folder:
                    path = Path(folder) / 'config.json'
                    path.write_text(json.dumps(candidate), encoding='utf-8')
                    proc = subprocess.run([os.environ['MIHOMO_BINARY'], '-t', '-d', folder, '-f', str(path)],
                                          capture_output=True, text=True, timeout=10)
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == '__main__':
    unittest.main()
