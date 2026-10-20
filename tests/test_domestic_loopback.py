"""Real Mihomo routing checks; every destination and upstream stays on loopback."""
import http.client
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
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
from test_mihomo_loopback import LocalHTTP, LocalProxy


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
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        udp_target = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_target.bind(('127.0.0.1', 0))
        udp_target.settimeout(.8)
        proc = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                hosts = ('bilibili.com', 'baidu.com', 'api.openai.com', 'unknown.test')
                base = {
                    'mixed-port': port, 'bind-address': '127.0.0.1', 'allow-lan': False,
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

                    for host in ('bilibili.com', 'baidu.com'):
                        self.assertEqual(request(host), 200, host)
                    self.assertEqual(proxy.hits, 0, 'Domestic TCP unexpectedly used proxy')
                    self.assertEqual(target.hits, 2)
                    for host in ('api.openai.com', 'unknown.test'):
                        self.assertEqual(request(host), 200, host)
                    self.assertEqual(proxy.hits, 2)
                    self.assertEqual(target.hits, 4)

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
                    for host in ('api.openai.com', 'unknown.test'):
                        self.assertNotEqual(request(host), 200, host)
                    self.assertEqual(target.hits, 4, 'Stopped proxy fell back to direct')
                    self.assertEqual(request('baidu.com'), 200)
                    self.assertEqual(target.hits, 5, 'Domestic direct must remain available')
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
            for server in (target, proxy):
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
