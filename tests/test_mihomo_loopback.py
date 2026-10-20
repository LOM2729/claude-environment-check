"""Optional real-core test. All endpoints, proxy, hosts and traffic stay on loopback.

Set MIHOMO_BINARY to a publisher-verified local binary. Never downloads dependencies,
touches system proxy/TUN or sends requests to real AI services.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import select
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
import unified_policy as unified
import claude_setup as c


class LocalHTTP(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.hits += 1
        payload = b'loopback-ok'
        self.send_response(200)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class LocalProxy(BaseHTTPRequestHandler):
    def do_CONNECT(self):
        self.server.hits += 1
        # Never resolve the request hostname; the sole destination is our loopback test server.
        remote = socket.create_connection(('127.0.0.1', self.server.target_port), timeout=3)
        self.send_response(200)
        self.end_headers()
        try:
            endpoints = [self.connection, remote]
            while True:
                ready, _, _ = select.select(endpoints, [], [], 3)
                if not ready:
                    break
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (remote if source is self.connection else self.connection).sendall(data)
        finally:
            remote.close()

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get('MIHOMO_BINARY'), 'MIHOMO_BINARY not supplied; real-core test not run')
class MihomoLoopback(unittest.TestCase):
    def test_designated_proxy_and_failure_never_reaches_direct_target(self):
        binary = os.environ['MIHOMO_BINARY']
        target = ThreadingHTTPServer(('127.0.0.1', 0), LocalHTTP)
        target.hits = 0
        proxy = ThreadingHTTPServer(('127.0.0.1', 0), LocalProxy)
        proxy.hits = 0
        proxy.target_port = target.server_port
        for server in (target, proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        reservation = socket.socket()
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
        reservation.close()
        udp_target = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_target.bind(('127.0.0.1', 0))
        udp_target.settimeout(1)
        proc = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                base = {
                    'mixed-port': port, 'bind-address': '127.0.0.1', 'allow-lan': False,
                    'mode': 'rule', 'log-level': 'info', 'ipv6': False,
                    'dns': {'enable': False}, 'tun': {'enable': False},
                    'hosts': {'api.openai.com': '127.0.0.1', 'api.anthropic.com': '127.0.0.1',
                              'ordinary.test': '127.0.0.1', 'ordinary-foreign.test': '127.0.0.1'},
                    'proxies': [{'name': 'Chosen', 'type': 'http', 'server': '127.0.0.1',
                                 'port': proxy.server_port}],
                    'proxy-groups': [{'name': 'Foreign', 'type': 'select', 'proxies': ['Chosen']}],
                    'rules': ['DOMAIN,ordinary.test,DIRECT', 'MATCH,Foreign'],
                }
                review = {'schema':'claude-direct-review/1', 'config_semantic_sha256':c.sha(c.encode(base)), 'entries':[{'rule':'DOMAIN,ordinary.test,DIRECT','decision':'keep','reason':'Synthetic loopback direct control.'}]}
                candidate = unified.build_semantics(c, base, 'json', 'Chosen', ai.GROUP, review)
                config = folder / 'test.json'
                config.write_bytes(c.encode(candidate))
                check = subprocess.run([binary, '-t', '-d', directory, '-f', str(config)],
                                       capture_output=True, timeout=20)
                self.assertEqual(check.returncode, 0, check.stdout.decode(errors='replace') + check.stderr.decode(errors='replace'))
                with (folder / 'core.log').open('wb') as log:
                    proc = subprocess.Popen([binary, '-d', directory, '-f', str(config)], stdout=log, stderr=log)
                    until = time.monotonic() + 10
                    while True:
                        try:
                            with socket.create_connection(('127.0.0.1', port), timeout=.2):
                                break
                        except OSError:
                            if time.monotonic() > until or proc.poll() is not None:
                                self.fail('Loopback core did not start: ' + (folder / 'core.log').read_text())
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

                    for host in ('api.openai.com', 'api.anthropic.com', 'ordinary-foreign.test'):
                        self.assertEqual(request(host), 200)
                    self.assertEqual(proxy.hits, 3)
                    self.assertEqual(target.hits, 3)
                    self.assertEqual(request('ordinary.test'), 200)
                    self.assertEqual(proxy.hits, 3)
                    self.assertEqual(target.hits, 4)

                    # SOCKS5 UDP association; direct control proves the UDP test actually works.
                    with socket.create_connection(('127.0.0.1', port), timeout=3) as control:
                        control.sendall(b'\x05\x01\x00')
                        self.assertEqual(control.recv(2), b'\x05\x00')
                        control.sendall(b'\x05\x03\x00\x01' + socket.inet_aton('127.0.0.1') + b'\x00\x00')
                        reply = control.recv(32)
                        self.assertEqual(reply[:4], b'\x05\x00\x00\x01')
                        relay_port = struct.unpack('!H', reply[8:10])[0]
                        def send_udp(host):
                            # Fresh source tuple per simulated application flow. Reusing the same
                            # source/destination can reuse a core NAT session and its earlier route.
                            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                                raw = host.encode()
                                sender.sendto(b'\x00\x00\x00\x03' + bytes([len(raw)]) + raw +
                                              struct.pack('!H', udp_target.getsockname()[1]) + b'test-udp',
                                              ('127.0.0.1', relay_port))
                                if host == 'ordinary.test':
                                    self.assertEqual(udp_target.recv(100), b'test-udp')
                                else:
                                    with self.assertRaises(socket.timeout):
                                        udp_target.recv(100)
                        for host in ('ordinary.test', 'api.openai.com', 'api.anthropic.com'):
                            send_udp(host)

                    proxy.shutdown()
                    proxy.server_close()
                    for host in ('api.openai.com', 'api.anthropic.com', 'ordinary-foreign.test'):
                        self.assertNotEqual(request(host), 200)
                    self.assertEqual(target.hits, 4, 'Proxy failure reached direct target')
                    self.assertEqual(request('ordinary.test'), 200)
                    self.assertEqual(target.hits, 5)
                    proc.terminate()
                    proc.wait(timeout=5)
                    proc = None
                log_text = (folder / 'core.log').read_text()
                self.assertIn('AI-ONLY', log_text)
                self.assertIn('REJECT', log_text)
        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)
            udp_target.close()
            target.shutdown()
            target.server_close()
            proxy.shutdown()
            proxy.server_close()


if __name__ == '__main__':
    unittest.main()
