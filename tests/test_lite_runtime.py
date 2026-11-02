import copy
import io
import json
from pathlib import Path
import socket
import sys
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lite import runtime_probe as probe


SOURCE = {'external-controller': '127.0.0.1:9090', 'secret': 'PRIVATE_TOKEN',
          'proxies': [{'name': 'node-one', 'type': 'ss'}, {'name': 'node-two', 'type': 'socks5'}],
          'proxy-groups': [{'name': 'outer', 'type': 'select', 'proxies': ['inner']},
                           {'name': 'inner', 'type': 'select', 'proxies': ['node-one', 'node-two']}],
          'rules': ['DOMAIN,example.com,DIRECT', 'MATCH,outer']}
PROXIES = {'proxies': {'outer': {'type': 'Selector', 'now': 'inner', 'all': ['inner']},
                       'inner': {'type': 'Selector', 'now': 'node-two', 'all': ['node-one', 'node-two']},
                       'node-one': {'type': 'Shadowsocks'}, 'node-two': {'type': 'Socks5'}}}


class Response(io.BytesIO):
    def __init__(self, data, url, status=200):
        super().__init__(data)
        self.url, self.status = url, status

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status


class FakeOpener:
    def __init__(self, proxies=None, version=None):
        self.calls = []
        self.proxies = copy.deepcopy(PROXIES if proxies is None else proxies)
        self.version = {'version': 'v1.19.0'} if version is None else version
        self.responses = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        value = self.version if request.full_url.endswith('/version') else self.proxies
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        response = Response(data, request.full_url)
        self.responses.append(response)
        return response


class RuntimeProbeTests(unittest.TestCase):
    def source(self, **kwargs):
        obj = copy.deepcopy(SOURCE)
        obj.update(kwargs)
        return obj

    def test_nested_current_selection_is_read_only_and_terminal_is_from_source(self):
        opener = FakeOpener()
        source = self.source()
        before = copy.deepcopy(source)
        with patch.object(socket, 'socket', side_effect=AssertionError('unexpected network')):
            result = probe.inspect_selection(source, opener)
        self.assertEqual(result['selected_node'], 'node-two')
        self.assertEqual(result['selection_origin'], 'runtime')
        self.assertTrue(result['available'])
        self.assertIsNone(result['warning'])
        self.assertEqual(result['selections'], {'outer': 'inner', 'inner': 'node-two'})
        self.assertEqual(source, before)
        self.assertTrue(all(response.closed for response in opener.responses))
        self.assertEqual([call[0].full_url for call in opener.calls],
                         ['http://127.0.0.1:9090/version', 'http://127.0.0.1:9090/proxies'])
        for request, timeout in opener.calls:
            self.assertEqual(request.method, 'GET')
            self.assertIsNone(request.data)
            self.assertEqual(request.get_header('Authorization'), 'Bearer PRIVATE_TOKEN')
            self.assertLessEqual(timeout, 2)
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(result))

    def test_explicit_wildcard_is_mapped_to_loopback(self):
        opener = FakeOpener()
        self.assertTrue(probe.inspect_selection(self.source(**{'external-controller': '0.0.0.0:7890'}), opener)['available'])
        self.assertTrue(all(call[0].full_url.startswith('http://127.0.0.1:7890/') for call in opener.calls))

    def test_ipv6_literal_loopback_is_supported(self):
        opener = FakeOpener()
        result = probe.inspect_selection(self.source(**{'external-controller': '[::1]:9090'}), opener)
        self.assertTrue(result['available'])
        self.assertEqual(opener.calls[0][0].full_url, 'http://[::1]:9090/version')

    def test_remote_names_urls_invalid_ports_and_unspecified_ipv6_rejected_before_request(self):
        for value in ('localhost:9090', '192.0.2.1:9090', 'example.com:9090',
                      'http://127.0.0.1:9090', '127.0.0.1:0', '127.0.0.1:65536',
                      '[::]:9090', '127.0.0.1:9090/path', '127.0.0.1:9090\n',
                      'user@127.0.0.1:9090', '[::ffff:127.0.0.1]:9090', None):
            with self.subTest(value=value):
                opener = FakeOpener()
                result = probe.inspect_selection(self.source(**{'external-controller': value}), opener)
                self.assertFalse(result['available'])
                self.assertEqual(opener.calls, [])
                self.assertEqual(result['warning'], 'RUNTIME_CONTROLLER_REJECTED')

    def test_bad_secret_rejected_without_echo_or_requests(self):
        for secret in ('PRIVATE\r\nX-Injected: yes', 'bad\x00', 'bad\tvalue', 'nonascii秘密', None, 123):
            opener = FakeOpener()
            result = probe.inspect_selection(self.source(secret=secret), opener)
            self.assertEqual(result['warning'], 'RUNTIME_SECRET_INVALID')
            self.assertEqual(opener.calls, [])

    def test_absent_secret_does_not_add_authorization(self):
        opener = FakeOpener()
        obj = self.source()
        del obj['secret']
        self.assertTrue(probe.inspect_selection(obj, opener)['available'])
        self.assertTrue(all(call[0].get_header('Authorization') is None for call in opener.calls))

    def test_direct_source_node_fallback_needs_no_controller(self):
        source = self.source(rules=['MATCH,node-one'])
        del source['external-controller']
        opener = FakeOpener()
        result = probe.inspect_selection(source, opener)
        self.assertEqual(result['selected_node'], 'node-one')
        self.assertEqual(result['selection_origin'], 'config-fallback')
        self.assertFalse(result['available'])
        self.assertEqual(opener.calls, [])

    def test_ambiguous_final_rule_duplicate_definition_and_missing_node_do_not_autoselect(self):
        cases = [self.source(rules=['MATCH,outer', 'FINAL,inner']),
                 self.source(rules=['MATCH,DIRECT']), self.source(rules=[]),
                 self.source(proxies=[{'name': 'node-one', 'type': 'ss'}] * 2)]
        for obj in cases:
            opener = FakeOpener()
            result = probe.inspect_selection(obj, opener)
            self.assertIsNone(result['selected_node'])
            self.assertEqual(result['warning'], 'RUNTIME_SELECTION_UNRESOLVED')
            self.assertEqual(opener.calls, [])

    def test_does_not_guess_first_member_without_now(self):
        payload = copy.deepcopy(PROXIES)
        del payload['proxies']['inner']['now']
        result = probe.inspect_selection(self.source(), FakeOpener(payload))
        self.assertTrue(result['available'])
        self.assertIsNone(result['selected_node'])
        self.assertEqual(result['warning'], 'RUNTIME_SELECTION_UNRESOLVED')

    def test_runtime_only_provider_node_is_not_a_source_node(self):
        payload = copy.deepcopy(PROXIES)
        payload['proxies']['inner'].update(now='api-node', all=['api-node'])
        payload['proxies']['api-node'] = {'type': 'Socks5'}
        result = probe.inspect_selection(self.source(), FakeOpener(payload))
        self.assertIsNone(result['selected_node'])
        self.assertEqual(result['warning'], 'RUNTIME_SELECTION_UNRESOLVED')

    def test_selector_disguised_as_terminal_does_not_autoselect(self):
        payload = copy.deepcopy(PROXIES)
        payload['proxies']['node-two'] = {'type': 'Selector', 'all': ['node-one']}
        result = probe.inspect_selection(self.source(), FakeOpener(payload))
        self.assertIsNone(result['selected_node'])
        self.assertEqual(result['warning'], 'RUNTIME_SELECTION_UNRESOLVED')
        source = self.source(proxies=[{'name': 'not-node', 'type': 'select'}], rules=['MATCH,not-node'])
        opener = FakeOpener()
        self.assertIsNone(probe.inspect_selection(source, opener)['selected_node'])
        self.assertEqual(opener.calls, [])

    def test_cycles_and_long_chains_are_bounded(self):
        payload = copy.deepcopy(PROXIES)
        payload['proxies']['inner'].update(now='outer', all=['outer'])
        self.assertIsNone(probe.inspect_selection(self.source(), FakeOpener(payload))['selected_node'])
        source = self.source()
        source['rules'] = ['MATCH,g0']
        source['proxy-groups'] = [{'name': f'g{i}', 'type': 'select'} for i in range(65)]
        payload = {'proxies': {f'g{i}': {'type': 'Selector', 'now': f'g{i+1}', 'all': [f'g{i+1}']}
                               for i in range(64)}}
        payload['proxies'].update({'g64': {'type': 'Selector', 'now': 'node-one', 'all': ['node-one']},
                                   'node-one': {'type': 'Shadowsocks'}})
        self.assertIsNone(probe.inspect_selection(source, FakeOpener(payload))['selected_node'])

    def test_invalid_response_schema_json_duplicate_keys_and_size_are_fixed_warnings(self):
        payloads = [b'PRIVATE_BROKEN_RESPONSE', b'{"proxies":{},"proxies":{}}',
                    b'{"proxies": NaN}', {'proxies': []}, {'proxies': {'x': {}}},
                    {'proxies': {'x': {'type': 'Selector', 'now': 'a', 'all': ['b']}}},
                    b'x' * (probe.MAX_RESPONSE_BYTES + 1)]
        for payload in payloads:
            with self.subTest(kind=type(payload).__name__):
                result = probe.inspect_selection(self.source(), FakeOpener(payload))
                self.assertFalse(result['available'])
                self.assertIsNone(result['selected_node'])
                self.assertEqual(result['warning'], 'RUNTIME_RESPONSE_INVALID')
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_invalid_version_stops_before_proxies_request(self):
        opener = FakeOpener(version={'secret': 'NEVER_ECHO'})
        result = probe.inspect_selection(self.source(), opener)
        self.assertEqual(result['warning'], 'RUNTIME_RESPONSE_INVALID')
        self.assertEqual(len(opener.calls), 1)

    def test_default_opener_disables_environment_proxy_and_redirects(self):
        fake = FakeOpener()
        with patch.object(urllib.request, 'build_opener', return_value=fake) as build:
            result = probe.inspect_selection(self.source())
        self.assertTrue(result['available'])
        proxy_handler, redirects = build.call_args.args
        self.assertIsInstance(proxy_handler, urllib.request.ProxyHandler)
        self.assertEqual(proxy_handler.proxies, {})
        self.assertIsInstance(redirects, probe._NoRedirect)
        with self.assertRaises(probe._Invalid):
            redirects.redirect_request(None, None, 302, 'redirect', {}, 'http://example.com/secret')

    def test_final_response_url_cannot_redirect_even_with_injected_opener(self):
        class Redirected(FakeOpener):
            def open(self, request, timeout):
                return Response(b'{}', 'http://example.com/secret')
        result = probe.inspect_selection(self.source(), Redirected())
        self.assertEqual(result['warning'], 'RUNTIME_RESPONSE_INVALID')

    def test_network_errors_do_not_echo_the_exception(self):
        class Unavailable:
            def open(self, request, timeout):
                raise urllib.error.URLError('PRIVATE_TOKEN_URL_AND_RESPONSE')
        output = io.StringIO()
        with patch('sys.stdout', output), patch('sys.stderr', output):
            result = probe.inspect_selection(self.source(), Unavailable())
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(result['warning'], 'RUNTIME_PROBE_UNAVAILABLE')
        self.assertNotIn('PRIVATE', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
