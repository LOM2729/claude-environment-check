"""Real Mihomo routing checks; every destination and upstream stays on loopback."""
import http.client
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ai_routing as ai
import claude_setup as c
from test_mihomo_loopback import LocalHTTP, LocalProxy, available_mixed_port, stop_core


def receive_exact(connection, size):
    result = b''
    while len(result) < size:
        chunk = connection.recv(size - len(result))
        if not chunk:
            raise EOFError('SOCKS control closed unexpectedly')
        result += chunk
    return result


@unittest.skipUnless(os.environ.get('MIHOMO_BINARY'), 'MIHOMO_BINARY not supplied; real-core test not run')
class DomesticLoopback(unittest.TestCase):
    def test_video_udp_exception_domestic_tcp_and_proxy_failure(self):
        import domestic_policy as domestic

        binary = os.environ['MIHOMO_BINARY']
        target = ThreadingHTTPServer(('127.0.0.1', 0), LocalHTTP)
        target.hits = 0
        proxy = ThreadingHTTPServer(('127.0.0.1', 0), LocalProxy)
        proxy.hits = 0
        proxy.target_port = target.server_port
        for server in (target, proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        with socket.socket() as controller_reservation:
            controller_reservation.bind(('127.0.0.1', 0))
            controller_port = controller_reservation.getsockname()[1]
            port = available_mixed_port()
        udp_target = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_target.bind(('127.0.0.1', 0))
        udp_target.settimeout(.8)
        proc = None
        try:
            with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
                folder = Path(directory)
                hosts = ('bilibili.com', 'baidu.com', 'api.anthropic.com', 'api.openai.com', 'unknown.test')
                base = {
                    'mixed-port': port, 'bind-address': '127.0.0.1', 'allow-lan': False,
                    'external-controller': f'127.0.0.1:{controller_port}',
                    'mode': 'rule', 'log-level': 'info', 'ipv6': False,
                    'dns': {'enable': False}, 'tun': {'enable': False},
                    'hosts': {host: '127.0.0.1' for host in hosts},
                    'proxies': [{'name': 'Chosen', 'type': 'http', 'server': '127.0.0.1',
                                 'port': proxy.server_port, 'udp': False}],
                    'proxy-groups': [{'name': 'Foreign', 'type': 'select', 'proxies': ['Chosen']}],
                    'rules': ['IP-CIDR,192.168.0.0/16,DIRECT,no-resolve', 'MATCH,Foreign'],
                }
                candidate = domestic.build_semantics(c, base, 'json', 'Chosen', ai.GROUP)
                config = folder / 'test.json'
                config.write_bytes(c.encode(candidate))
                check = subprocess.run([binary, '-t', '-d', directory, '-f', str(config)],
                                       capture_output=True, timeout=20)
                self.assertEqual(check.returncode, 0, check.stdout.decode(errors='replace') + check.stderr.decode(errors='replace'))
                with (folder / 'core.log').open('wb') as log:
                    proc = subprocess.Popen([binary, '-d', directory, '-f', str(config)], stdout=log, stderr=log)
                    cleanup.callback(stop_core, proc)

                    def diagnostics():
                        return (f'core_exit={proc.poll()}, direct_hits={target.hits}, proxy_hits={proxy.hits}\n' +
                                (folder / 'core.log').read_text(errors='replace'))

                    until = time.monotonic() + 10
                    provider_state = None
                    while True:
                        connection = http.client.HTTPConnection('127.0.0.1', controller_port, timeout=.5)
                        try:
                            # The mixed listener opens before inline providers initialize.
                            # Wait on provider readiness, never retry a failed routing request.
                            connection.request('GET', '/providers/rules')
                            response = connection.getresponse()
                            providers = json.loads(response.read(8 * 1024 * 1024)).get('providers') or {}
                            provider_state = {name: (providers.get(name) or {}).get('ruleCount', 0)
                                              for name in (domestic.VIDEO, domestic.CN)}
                            if response.status == 200 and all(
                                    count > 0 for count in provider_state.values()):
                                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                                    break
                        except (OSError, http.client.HTTPException, ValueError) as error:
                            provider_state = {'readiness_error': repr(error)}
                        finally:
                            connection.close()
                        if time.monotonic() > until or proc.poll() is not None:
                            self.fail('Loopback core/providers did not become ready: ' +
                                      repr(provider_state) + '\n' + diagnostics())
                        time.sleep(.05)

                    def request(host):
                        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
                        try:
                            connection.request('GET', f'http://{host}:{target.server_port}/', headers={'Connection': 'close'})
                            response = connection.getresponse()
                            response.read()
                            return response.status
                        except (OSError, http.client.HTTPException):
                            return None
                        finally:
                            connection.close()

                    for host in ('bilibili.com', 'baidu.com'):
                        status = request(host)
                        self.assertEqual(status, 200, host + '\n' + diagnostics() if status != 200 else host)
                    self.assertEqual(proxy.hits, 0, 'Domestic TCP unexpectedly used proxy')
                    self.assertEqual(target.hits, 2)
                    for host in ('api.anthropic.com', 'api.openai.com', 'unknown.test'):
                        status = request(host)
                        self.assertEqual(status, 200, host + '\n' + diagnostics() if status != 200 else host)
                    self.assertEqual(proxy.hits, 3, 'Claude, OpenAI and ordinary foreign must share the chosen proxy')
                    self.assertEqual(target.hits, 5)

                    with socket.create_connection(('127.0.0.1', port), timeout=3) as control:
                        control.sendall(b'\x05\x01\x00')
                        self.assertEqual(receive_exact(control, 2), b'\x05\x00')
                        control.sendall(b'\x05\x03\x00\x01' + socket.inet_aton('127.0.0.1') + b'\x00\x00')
                        header = receive_exact(control, 4)
                        self.assertEqual(header, b'\x05\x00\x00\x01')
                        reply = receive_exact(control, 6)
                        relay_port = struct.unpack('!H', reply[4:])[0]
                        # New source tuple for each flow avoids core UDP NAT-route reuse.
                        for host in hosts:
                            with self.subTest(udp_host=host), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                                sender.settimeout(2)
                                raw = host.encode()
                                payload = b'udp-' + raw
                                sender.sendto(b'\x00\x00\x00\x03' + bytes([len(raw)]) + raw +
                                              struct.pack('!H', udp_target.getsockname()[1]) + payload,
                                              ('127.0.0.1', relay_port))
                                if host == 'bilibili.com':
                                    received, source = udp_target.recvfrom(1024)
                                    self.assertEqual(received, payload)
                                    udp_target.sendto(received, source)
                                    self.assertTrue(sender.recv(2048).endswith(payload), 'Video UDP reply failed')
                                else:
                                    with self.assertRaises(socket.timeout, msg=host + ' UDP bypassed rejection'):
                                        udp_target.recvfrom(1024)

                    proxy.shutdown()
                    proxy.server_close()
                    for host in ('api.anthropic.com', 'api.openai.com', 'unknown.test'):
                        self.assertNotEqual(request(host), 200, host)
                    self.assertEqual(target.hits, 5, 'Stopped proxy fell back to direct')
                    self.assertEqual(request('baidu.com'), 200)
                    self.assertEqual(target.hits, 6, 'Domestic direct must remain available')
                    proc.terminate()
                    proc.wait(timeout=5)
                    proc = None
                log_text = (folder / 'core.log').read_text()
                # Check the real core's selected chains, not just generated rule text.
                # Both groups must terminate at the exact same loopback proxy node.
                for host, group in (('api.anthropic.com', ai.GROUP + '-Claude'),
                                    ('api.openai.com', ai.GROUP), ('unknown.test', ai.GROUP)):
                    with self.subTest(route_host=host):
                        self.assertRegex(log_text, re.escape(host) + r':\d+[^\n]*using ' +
                                         re.escape(group + '[Chosen]'), log_text)
                self.assertIn('REJECT', log_text)
        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)
            udp_target.close()
            for server in (target, proxy):
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
