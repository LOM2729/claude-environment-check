"""Synthetic state + loopback tests; never collect customer settings or launch apps."""
import contextlib
import copy
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import platform
import select
import socket
import ssl
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c
import ai_routing as ai
import network_checks as net
import readiness_lifecycle as life

NATIVE = {'platform': 'Synthetic', 'values': {'timezone': 'Asia/Singapore', 'languages': ['zh-Hans'], 'https_proxy_enabled': True}, 'dns_identity_sha256': 'a' * 64}
BASE = {'mode': 'rule', 'proxies': [{'name': 'Chosen', 'type': 'http', 'server': '192.0.2.1', 'port': 8080}], 'rules': ['DOMAIN,example.cn,DIRECT', 'MATCH,Chosen']}


class LocalHTTPS(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.server.hits += 1
        status = 302 if self.path == '/redirect' else 403 if self.path == '/challenge' else 200
        self.send_response(status)
        if status == 302:
            self.send_header('Location', 'https://must-not-contact.invalid/')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        self.server.hits += 1
        body = b'ip=203.0.113.9\nloc=XX\n'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LoopbackProxy(BaseHTTPRequestHandler):
    def do_CONNECT(self):
        self.server.hits += 1
        self.server.destinations.append(self.path)
        peer = socket.create_connection(('127.0.0.1', self.server.destination_port), timeout=3)
        self.send_response(200)
        self.end_headers()
        try:
            while True:
                ready, _, _ = select.select([self.connection, peer], [], [], 3)
                if not ready:
                    return
                for source in ready:
                    block = source.recv(65536)
                    if not block:
                        return
                    (peer if source is self.connection else self.connection).sendall(block)
        except OSError:
            pass
        finally:
            peer.close()

    def log_message(self, *args):
        pass


class NetworkValidation(unittest.TestCase):
    def test_no_opt_in_never_probes(self):
        with patch.object(net, 'isolated_probe') as probe:
            with self.assertRaisesRegex(c.SetupError, 'EXPLICIT_NETWORK_OPT_IN'):
                net.run_checks(c, net.template('http://127.0.0.1:7890'), False)
            probe.assert_not_called()

    def test_invalid_plans_rejected_before_probe(self):
        for url in (42, None, 'http://example.com/', 'https://name:secret@example.com/', 'https://example.com/?key=secret',
                    'https://example.com/#secret', 'https://example.com:444/', 'https://example.com/\r\nX:yes'):
            plan = net.template('http://127.0.0.1:7890')
            plan['checks'][0]['url'] = url
            with self.assertRaises(c.SetupError):
                net.validate_plan(c, plan)
        for proxy in (42, None, 'http://example.com:8080', 'socks5://127.0.0.1:7890', 'http://user:secret@127.0.0.1:7890'):
            with self.assertRaises(c.SetupError):
                net.validate_plan(c, net.template(proxy))

    def test_http_auth_and_redirect_not_function_pass(self):
        check = net.template('http://127.0.0.1:7890')['checks'][0]
        for status in (301, 302, 401, 403, 405, 500):
            self.assertEqual(net.row(check, {'outcome': 'response', 'http_status': status})['status'], '未完成')
        self.assertEqual(net.row(check, {'outcome': 'response', 'http_status': 200})['status'], '已完成')

    def test_timeout_and_missing_egress_never_pass(self):
        for kind in ('stun', 'egress'):
            check = {'id': 'test', 'type': kind, 'required': True, 'expected_ip': '203.0.113.9'}
            for observation in ({'outcome': 'timeout'}, {'outcome': 'no_answer'}, {'outcome': 'stun_response', 'ip': '203.0.113.8'}):
                self.assertEqual(net.row(check, observation)['status'], '未完成')
            check['expected_ip'] = None
            self.assertEqual(net.row(check, {'outcome': 'stun_response', 'ip': '203.0.113.9'})['status'], '未完成')

    def test_worker_deadline_is_unknown(self):
        import subprocess
        with patch.object(net.subprocess, 'run', side_effect=subprocess.TimeoutExpired('worker', 9)):
            self.assertEqual(net.isolated_probe({'id': 'test'})['outcome'], 'timeout')

    def test_stun_transaction_family_and_length(self):
        transaction = b'a' * 12
        for family, address in ((1, b'\xcb\x00\x71\x09'), (2, bytes.fromhex('20010db8000000000000000000000001'))):
            mask = struct.pack('!I', 0x2112A442) + transaction
            body = bytes([0, family, 0, 1]) + bytes(a ^ b for a, b in zip(address, mask))
            attr = struct.pack('!HH', 0x20, len(body)) + body
            packet = struct.pack('!HHI', 0x101, len(attr), 0x2112A442) + transaction + attr
            self.assertIsNotNone(net.parse_stun(packet, transaction))
            self.assertIsNone(net.parse_stun(packet, b'b' * 12))
            self.assertIsNone(net.parse_stun(packet[:-1], transaction))
            self.assertIsNone(net.parse_stun(packet + b'junk', transaction))

    def test_native_udp_worker_against_loopback_stun(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
            server.bind(('127.0.0.1', 0)); server.settimeout(5)
            def respond():
                request, addr = server.recvfrom(100)
                body = b'\x00\x01\x00\x01' + bytes(a ^ b for a, b in zip(b'\xcb\x00\x71\x09', bytes.fromhex('2112a442')))
                server.sendto(struct.pack('!HHI', 0x101, 12, 0x2112A442) + request[8:20] + struct.pack('!HH', 0x20, 8) + body, addr)
            thread = threading.Thread(target=respond, daemon=True); thread.start()
            result = net.isolated_probe({'type': 'stun', 'host': '127.0.0.1', 'port': server.getsockname()[1], 'family': 'ipv4'})
            thread.join(5)
        self.assertEqual(result, {'outcome': 'stun_response', 'ip': '203.0.113.9'})

    def test_native_ipv6_stun_worker_loopback(self):
        if not socket.has_ipv6:
            self.skipTest('IPv6 unavailable on this runner')
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as server:
            try:
                server.bind(('::1', 0))
            except OSError:
                self.skipTest('IPv6 loopback unavailable on this runner')
            server.settimeout(5)
            def respond():
                request, addr = server.recvfrom(100)
                transaction = request[8:20]
                address = bytes.fromhex('20010db8000000000000000000000001')
                mask = bytes.fromhex('2112a442') + transaction
                body = b'\x00\x02\x00\x01' + bytes(a ^ b for a, b in zip(address, mask))
                server.sendto(struct.pack('!HHI', 0x101, 24, 0x2112A442) + transaction + struct.pack('!HH', 0x20, 20) + body, addr)
            thread = threading.Thread(target=respond, daemon=True); thread.start()
            result = net.isolated_probe({'type': 'stun', 'host': '::1', 'port': server.getsockname()[1], 'family': 'ipv6'})
            thread.join(5)
        self.assertEqual(result, {'outcome': 'stun_response', 'ip': '2001:db8::1'})

    def test_system_dns_worker_loopback_only(self):
        result = net.isolated_probe({'type': 'dns', 'host': 'localhost', 'family': 'ipv4'})
        self.assertEqual(result['outcome'], 'resolved')
        self.assertIn('127.0.0.1', result['addresses'])


class HTTPSLoopback(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), LocalHTTPS)
        self.server.hits = 0
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(ROOT / 'tests/fixtures/loopback-cert.pem', ROOT / 'tests/fixtures/loopback-key.pem')
        self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
        self.proxy = ThreadingHTTPServer(('127.0.0.1', 0), LoopbackProxy)
        self.proxy.hits = 0; self.proxy.destinations = []; self.proxy.destination_port = self.server.server_port
        for server in (self.server, self.proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.environment = patch.dict(os.environ, {'SSL_CERT_FILE': str(ROOT / 'tests/fixtures/loopback-cert.pem')})
        self.environment.start()
        self.check = {'id': 'loopback', 'type': 'https', 'required': True, 'url': 'https://localhost/',
                      'route': 'proxy', 'proxy': f'http://127.0.0.1:{self.proxy.server_port}', 'expected_statuses': [200]}

    def tearDown(self):
        self.environment.stop()
        for server in (self.proxy, self.server):
            server.shutdown(); server.server_close()

    def trusted_probe(self):
        original_run = net.subprocess.run
        bootstrap = "import ssl,runpy,sys; factory=ssl.create_default_context; ssl.create_default_context=lambda:factory(cafile=" + repr(str(ROOT / 'tests/fixtures/loopback-cert.pem')) + "); sys.argv=[" + repr(str(ROOT / 'src/network_checks.py')) + ",'--worker']; runpy.run_path(sys.argv[0],run_name='__main__')"
        def run_worker(argv, **kwargs):
            return original_run([sys.executable, '-c', bootstrap], **kwargs)
        with patch.object(net.subprocess, 'run', side_effect=run_worker):
            return net.isolated_probe(self.check)

    def test_tls_through_explicit_proxy_and_no_redirect(self):
        result = self.trusted_probe()
        self.assertEqual(result['http_status'], 200)
        self.assertTrue(result['tls_verified'])
        self.assertEqual(self.proxy.destinations, ['localhost:443'])
        self.check['url'] = 'https://localhost/redirect'
        result = self.trusted_probe()
        self.assertEqual(result['http_status'], 302)
        self.assertEqual(self.server.hits, 2)
        self.assertEqual(net.row(self.check, result)['status'], '未完成')

    def test_egress_private_capture_and_comparison(self):
        self.check.update(type='egress', response_format='trace', expected_ip='203.0.113.9')
        self.check.pop('expected_statuses')
        result = self.trusted_probe()
        self.assertEqual(result['ip'], '203.0.113.9')
        row = net.row(self.check, result)
        self.assertEqual(row['status'], '已完成')
        self.assertNotIn('203.0.113.9', json.dumps(row))

    def test_dead_proxy_fails_without_direct_fallback(self):
        self.proxy.shutdown(); self.proxy.server_close()
        result = net.isolated_probe(self.check)
        self.assertIn(result['outcome'], ('network_error', 'timeout'))
        self.assertEqual(self.server.hits, 0)

    def test_untrusted_certificate_is_not_accepted(self):
        with patch.dict(os.environ, {'SSL_CERT_FILE': str(ROOT / 'tests/fixtures/nonexistent.pem')}):
            result = net.isolated_probe(self.check)
        self.assertEqual(result['outcome'], 'tls_error')


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original = self.root / 'before.json'; self.original.write_bytes(c.encode(BASE))
        candidate, _ = ai.semantic_candidate(c, BASE, 'json', 'Chosen', 'AI-ONLY', ai.catalog(c))
        self.current = self.root / 'active.json'; self.current.write_bytes(c.encode(candidate))
        self.executable = self.root / ('client.exe' if platform.system() == 'Windows' else 'client')
        magic = b'MZxx' if platform.system() == 'Windows' else b'\xcf\xfa\xed\xfe'
        self.executable.write_bytes(magic + b'synthetic-never-execute')
        self.baseline = self.root / 'baseline'
        self.native = patch.object(life, 'native_state', return_value=copy.deepcopy(NATIVE)); self.native.start()
        life.create_baseline(c, self.current, 'json', self.original, 'Chosen', 'AI-ONLY', self.executable, None, self.baseline)

    def tearDown(self):
        self.native.stop(); self.temp.cleanup()

    def checks(self):
        return life.recheck(c, self.baseline, self.current, self.executable)[0]

    def plan(self):
        plan = net.template('http://127.0.0.1:7890')
        plan['checks'][2]['expected_ip'] = '203.0.113.9'
        return plan

    def successful_network(self, context, plan, allow):
        return [net.row(x, {'outcome': 'response', 'http_status': 200, 'ip': '203.0.113.9'} if x['type'] != 'dns' else {'outcome': 'timeout'}) for x in plan['checks']], []

    @unittest.skipUnless(platform.system() == 'Darwin', 'Mac bundle entry on Mac CI')
    def test_mac_bundle_entry_and_metadata_changes(self):
        import plistlib
        app = self.root / 'Example.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        (app / 'Contents/MacOS/Example').write_bytes(b'\xcf\xfa\xed\xfe' + b'test-not-executed')
        info = app / 'Contents/Info.plist'
        info.write_bytes(plistlib.dumps({'CFBundleExecutable': 'Example', 'CFBundleVersion': '1'}))
        first = life.client_identity(c, app)
        info.write_bytes(plistlib.dumps({'CFBundleExecutable': 'Example', 'CFBundleVersion': '2'}))
        self.assertNotEqual(first, life.client_identity(c, app))
        info.write_bytes(plistlib.dumps({'CFBundleExecutable': '../other'}))
        with self.assertRaises(c.SetupError): life.client_identity(c, app)

    @unittest.skipUnless(platform.system() == 'Windows', 'Windows DNS reader on Windows CI')
    def test_windows_dns_identity_native_reader(self):
        raw = c.run_fixed(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(ROOT / 'src/collect_dns_identity.ps1')])
        self.assertIsNotNone(raw)
        data = c.load_json(raw.encode('utf-8'))
        self.assertIsInstance(data, list)
        for row in data:
            self.assertEqual(set(row), {'interface', 'family', 'servers'})
            self.assertIsInstance(row['servers'], list)

    def test_baseline_recheck_and_no_writes(self):
        before = self.current.read_bytes()
        self.assertTrue(all(r['status'] == '已完成' for r in self.checks()))
        self.assertEqual(self.current.read_bytes(), before)

    def test_config_drift_is_reported_not_restored(self):
        data = c.load_json(self.current.read_bytes()); data['dns'] = {'enable': False}
        self.current.write_bytes(c.encode(data))
        rows = self.checks()
        self.assertEqual(rows[0]['status'], '未完成')
        self.assertEqual(rows[1]['status'], '未完成')
        self.assertEqual(c.load_json(self.current.read_bytes())['dns'], {'enable': False})

    def test_missing_current_config_reports_incomplete(self):
        self.current.unlink()
        rows = self.checks()
        self.assertEqual(rows[0]['status'], '未完成')
        self.assertEqual(rows[1]['status'], '未完成')
        self.assertEqual(next(r for r in rows if r['id'] == 'client_drift')['status'], '已完成')
        with patch.object(net, 'run_checks') as network:
            result = life.startup(c, self.baseline, self.current, self.executable, None, self.plan(), True, False, self.root / 'missing')
            self.assertFalse(result['required_checks_completed']); network.assert_not_called()
        self.assertTrue((self.root / 'missing/report.html').exists())

    def test_browser_ignores_unrelated_counts_but_detects_doh_change(self):
        browser = self.root / 'Preferences'
        browser.write_text(json.dumps({'intl': {'accept_languages': 'en-US'}, 'dns_over_https': {'mode': 'secure', 'templates': 'https://example.test/dns-query'}, 'unrelated': 1}))
        baseline = self.root / 'browser-baseline'
        life.create_baseline(c, self.current, 'json', self.original, 'Chosen', 'AI-ONLY', self.executable, browser, baseline)
        data = json.loads(browser.read_text(encoding='utf-8')); data['unrelated'] = 2; browser.write_text(json.dumps(data))
        rows, _ = life.recheck(c, baseline, self.current, self.executable, browser)
        self.assertEqual(rows[-1]['status'], '已完成')
        data['dns_over_https']['templates'] = 'https://changed.test/dns-query'; browser.write_text(json.dumps(data))
        rows, _ = life.recheck(c, baseline, self.current, self.executable, browser)
        self.assertEqual(rows[-1]['status'], '未完成')

    def test_unrelated_https_cannot_replace_ai_startup_check(self):
        plan = self.plan()
        for check in plan['checks']:
            if check['type'] == 'https': check['url'] = 'https://example.com/'
        with patch.object(net, 'run_checks') as network:
            result = life.startup(c, self.baseline, self.current, self.executable, None, plan, True, False, self.root / 'unrelated')
            self.assertFalse(result['required_checks_completed']); network.assert_not_called()

    def test_existing_output_prevents_probes_and_launch(self):
        out = self.root / 'existing'; out.mkdir()
        with patch.object(net, 'run_checks') as network, patch.object(life.subprocess, 'Popen') as spawn:
            with self.assertRaises(c.SetupError):
                life.startup(c, self.baseline, self.current, self.executable, None, self.plan(), True, False, out)
            network.assert_not_called(); spawn.assert_not_called()

    def test_client_update_requires_review(self):
        self.executable.write_bytes(self.executable.read_bytes() + b'updated')
        self.assertEqual(next(r for r in self.checks() if r['id'] == 'client_drift')['status'], '未完成')

    def test_dns_same_count_changed_identity_detected(self):
        native = copy.deepcopy(NATIVE); native['dns_identity_sha256'] = 'b' * 64
        with patch.object(life, 'native_state', return_value=native):
            self.assertEqual(next(r for r in self.checks() if r['id'] == 'dns_drift')['status'], '未完成')

    def test_unknown_dns_never_passes(self):
        native = copy.deepcopy(NATIVE); native['dns_identity_sha256'] = None
        with patch.object(life, 'native_state', return_value=native):
            self.assertEqual(next(r for r in self.checks() if r['id'] == 'dns_drift')['status'], '未完成')

    def test_baseline_integrity_and_machine_binding(self):
        with patch.object(life, 'machine_id', return_value='different'):
            with self.assertRaisesRegex(c.SetupError, 'BASELINE_MACHINE_MISMATCH'):
                self.checks()
        (self.baseline / 'config.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(c.SetupError, 'BASELINE_SNAPSHOT_MISMATCH'):
            self.checks()

    def test_preflight_failed_drift_never_probes_or_launches(self):
        self.current.write_bytes(self.current.read_bytes() + b' ')
        with patch.object(net, 'run_checks') as network, patch.object(life.subprocess, 'Popen') as spawn:
            life.startup(c, self.baseline, self.current, self.executable, None, self.plan(), True, False, self.root / 'out')
            network.assert_not_called(); spawn.assert_not_called()

    def test_old_network_report_is_not_a_plan_or_launch_authority(self):
        with self.assertRaises(c.SetupError):
            net.validate_plan(c, {'schema': 'claude-readiness-run/1', 'required_checks_completed': True})

    def test_preflight_requires_confirmed_egress_and_same_proxy(self):
        for change in ('missing_ip', 'direct'):
            plan = self.plan()
            if change == 'missing_ip': plan['checks'][2]['expected_ip'] = None
            else: plan['checks'][0]['route'] = 'direct'
            with patch.object(net, 'run_checks') as network:
                result = life.startup(c, self.baseline, self.current, self.executable, None, plan, True, False, self.root / change)
                self.assertFalse(result['required_checks_completed']); network.assert_not_called()

    def test_preflight_runs_fresh_network_each_time(self):
        with patch.object(net, 'run_checks', side_effect=self.successful_network) as network:
            for name in ('first', 'second'):
                result = life.startup(c, self.baseline, self.current, self.executable, None, self.plan(), True, False, self.root / name)
                self.assertTrue(result['required_checks_completed'])
            self.assertEqual(network.call_count, 2)
        report = json.loads((self.root / 'first/report.json').read_bytes())
        self.assertTrue(any(r['status'] == '未完成' and not r['required'] for r in report['rows']))

    def test_launch_rechecks_after_network_and_blocks_concurrent_change(self):
        def change(context, plan, allow):
            self.current.write_bytes(self.current.read_bytes() + b' ')
            return self.successful_network(context, plan, allow)
        with patch.object(life.platform, 'system', return_value='Darwin'), patch.object(life, 'machine_id', return_value=c.load_json((self.baseline / 'baseline.json').read_bytes())['machine_id']), patch.object(life, 'client_identity', return_value=c.load_json((self.baseline / 'baseline.json').read_bytes())['client']), patch.object(net, 'run_checks', side_effect=change) as network, patch.object(life.subprocess, 'Popen') as spawn:
            result = life.startup(c, self.baseline, self.current, self.executable, None, self.plan(), True, True, self.root / 'out')
            self.assertFalse(result['launch_requested']); spawn.assert_not_called(); network.assert_called_once()

    @unittest.skipUnless(platform.system() in ('Windows', 'Darwin'), 'Native launch selection is tested on Mac and Windows CI')
    def test_successful_launch_uses_explicit_cli_path_no_shell_and_no_false_runtime_pass(self):
        with patch.object(net, 'run_checks', side_effect=self.successful_network), patch.object(life.subprocess, 'Popen') as spawn:
            result = life.startup(c, self.baseline, self.current, self.executable, None, self.plan(), True, True, self.root / 'out')
            self.assertTrue(result['launch_requested'])
            self.assertEqual(spawn.call_args.args[0], [str(self.executable)])
            self.assertIs(spawn.call_args.kwargs['shell'], False)
            self.assertFalse(result['runtime_adoption_verified'])

    def test_report_is_offline_redacted_and_binary_status(self):
        private = [{'ip': '203.0.113.9', 'secret': 'PRIVATE_TEST_VALUE'}]
        out = self.root / 'report'
        life.save_report(c, out, 'recheck', self.checks(), private=private)
        text = (out / 'report.html').read_text(encoding='utf-8')
        self.assertNotIn('PRIVATE_TEST_VALUE', text); self.assertNotIn('203.0.113.9', text)
        self.assertIn('检查时间', text); self.assertIn('启动必需', text); self.assertIn('已完成 5 项', text)
        self.assertNotIn('<script', text); self.assertNotIn('https://', text)
        data = c.load_json((out / 'report.json').read_bytes())
        self.assertLessEqual({x['status'] for x in data['rows']}, {'已完成', '未完成'})
        self.assertIn('PRIVATE_TEST_VALUE', (out / 'evidence.private.json').read_text(encoding='utf-8'))

    def test_cli_network_without_opt_in_is_fixed_error_and_no_calls(self):
        plan = self.root / 'plan.json'; plan.write_bytes(c.encode(self.plan()))
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(net, 'isolated_probe') as probe, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = c.main(['network-check', '--plan', str(plan), '--out', str(self.root / 'out')])
        self.assertEqual(code, 1); probe.assert_not_called()
        self.assertNotIn(str(plan), stderr.getvalue())
        self.assertFalse((self.root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
