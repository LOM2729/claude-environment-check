"""Bounded, opt-in probes. Results are evidence for the declared probe path only."""
import datetime as dt
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import struct
import subprocess
import sys
from urllib.parse import urlsplit

MAX_RESPONSE = 32768


def validate_plan(c, value):
    c.require(isinstance(value, dict) and value.get('schema') == 'claude-network-plan/1', 'NETWORK_PLAN_INVALID')
    c.require(value.get('phase', 'service') in ('bootstrap', 'service'), 'NETWORK_PHASE_INVALID')
    checks = value.get('checks')
    c.require(isinstance(checks, list) and 1 <= len(checks) <= 12, 'NETWORK_CHECKS_REQUIRED')
    ids = set()
    for item in checks:
        c.require(isinstance(item, dict), 'NETWORK_CHECK_INVALID')
        name = item.get('id')
        c.require(isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', name) and name not in ids, 'NETWORK_ID_INVALID')
        ids.add(name)
        c.require(type(item.get('required')) is bool, 'NETWORK_REQUIRED_FLAG_INVALID')
        kind = item.get('type')
        c.require(kind in ('https', 'egress', 'dns', 'stun'), 'NETWORK_KIND_INVALID')
        c.require(item.get('family', 'auto') in ('auto', 'ipv4', 'ipv6'), 'NETWORK_FAMILY_INVALID')
        if kind in ('https', 'egress'):
            c.require(isinstance(item.get('url'), str), 'NETWORK_HTTPS_URL_REQUIRED')
            parsed = urlsplit(item['url'])
            c.require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
                      and not parsed.query and not parsed.fragment and parsed.port in (None, 443)
                      and len(item['url']) <= 500 and not any(ord(x) < 33 for x in item['url']), 'NETWORK_HTTPS_URL_REQUIRED')
            host(c, parsed.hostname)
            route = item.get('route')
            c.require(route in ('proxy', 'direct'), 'NETWORK_ROUTE_REQUIRED')
            if route == 'proxy':
                c.require(isinstance(item.get('proxy'), str), 'NETWORK_LOOPBACK_HTTP_PROXY_REQUIRED')
                proxy = urlsplit(item['proxy'])
                c.require(proxy.scheme == 'http' and proxy.hostname in ('127.0.0.1', '::1') and proxy.port
                          and not proxy.username and not proxy.password and proxy.path in ('', '/')
                          and not proxy.query and not proxy.fragment, 'NETWORK_LOOPBACK_HTTP_PROXY_REQUIRED')
                c.require(item.get('family', 'auto') == 'auto', 'NETWORK_PROXY_TARGET_FAMILY_UNKNOWN')
            if kind == 'https':
                statuses = item.get('expected_statuses')
                c.require(isinstance(statuses, list) and statuses and all(type(x) is int and 200 <= x < 300 for x in statuses), 'NETWORK_SUCCESS_STATUS_REQUIRED')
            else:
                c.require(item.get('response_format') in ('ip', 'trace', 'json_ip'), 'NETWORK_EGRESS_FORMAT_INVALID')
        else:
            host(c, item.get('host'))
            if kind == 'stun':
                c.require(type(item.get('port')) is int and 1 <= item['port'] <= 65535, 'NETWORK_PORT_INVALID')
                c.require(item.get('family') in ('ipv4', 'ipv6'), 'NETWORK_STUN_FAMILY_REQUIRED')
        if item.get('expected_ip') is not None:
            try:
                ipaddress.ip_address(item['expected_ip'])
            except (ValueError, TypeError):
                raise c.SetupError('NETWORK_EXPECTED_IP_INVALID') from None
        c.require(set(item) <= {'id', 'type', 'required', 'url', 'route', 'proxy', 'family', 'expected_statuses',
                               'response_format', 'host', 'port', 'expected_ip'}, 'NETWORK_UNKNOWN_FIELD')
    c.require(any(x['required'] for x in checks), 'NETWORK_REQUIRED_CHECK_MISSING')
    if value.get('phase', 'service') == 'bootstrap':
        import ai_routing
        catalog = ai_routing.catalog(c)
        for item in checks:
            name = (urlsplit(item.get('url', '')).hostname if item['type'] in ('https', 'egress') else item['host']).lower().rstrip('.')
            protected = name in catalog['exact_hosts'] or any(name == d or name.endswith('.' + d) for d in catalog['suffixes'])
            c.require(not protected, 'BOOTSTRAP_AI_TARGET_FORBIDDEN')
    return value


def host(c, value):
    c.require(isinstance(value, str) and 0 < len(value) <= 253 and not any(ord(x) < 33 for x in value), 'NETWORK_HOST_INVALID')
    try:
        ipaddress.ip_address(value)
        return
    except ValueError:
        pass
    c.require(re.fullmatch(r'[A-Za-z0-9.-]+', value) and all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p) for p in value.split('.')), 'NETWORK_HOST_INVALID')


def template(proxy, phase='bootstrap'):
    plan = {'schema': 'claude-network-plan/1', 'phase': phase, 'checks': [
        {'id': 'claude_https', 'type': 'https', 'required': True, 'url': 'https://claude.ai/',
         'route': 'proxy', 'proxy': proxy, 'expected_statuses': [200]},
        {'id': 'openai_https', 'type': 'https', 'required': True, 'url': 'https://chatgpt.com/',
         'route': 'proxy', 'proxy': proxy, 'expected_statuses': [200]},
        {'id': 'proxy_egress', 'type': 'egress', 'required': True,
         'url': 'https://www.cloudflare.com/cdn-cgi/trace', 'route': 'proxy', 'proxy': proxy,
         'response_format': 'trace', 'expected_ip': None},
        {'id': 'system_dns', 'type': 'dns', 'required': False, 'host': 'claude.ai', 'family': 'auto'},
    ]}
    if phase == 'bootstrap':
        plan['checks'] = [plan['checks'][2], {'id': 'diagnostic_dns', 'type': 'dns', 'required': True, 'host': 'example.com', 'family': 'auto'}]
    return plan


def connect_family(address, timeout, family):
    wanted = {'auto': socket.AF_UNSPEC, 'ipv4': socket.AF_INET, 'ipv6': socket.AF_INET6}[family]
    last = None
    for af, kind, proto, _, sockaddr in socket.getaddrinfo(address[0], address[1], wanted, socket.SOCK_STREAM):
        sock = socket.socket(af, kind, proto)
        sock.settimeout(timeout)
        try:
            sock.connect(sockaddr)
            return sock
        except OSError as error:
            last = error
            sock.close()
    raise OSError('connection failed') from last


def parse_stun(data, transaction):
    if len(data) < 20:
        return None
    kind, length, cookie = struct.unpack('!HHI', data[:8])
    if kind != 0x0101 or cookie != 0x2112A442 or data[8:20] != transaction or length % 4 or len(data) != 20 + length:
        return None
    offset = 20
    while offset + 4 <= len(data):
        attr, size = struct.unpack('!HH', data[offset:offset + 4])
        end = offset + 4 + size
        if end > len(data):
            return None
        body = data[offset + 4:end]
        if attr in (0x0020, 0x0001) and len(body) >= 4:
            family = body[1]
            needed = 8 if family == 1 else 20 if family == 2 else 0
            if not needed or len(body) != needed:
                return None
            raw = body[4:]
            if attr == 0x0020:
                mask = struct.pack('!I', cookie) + transaction
                raw = bytes(a ^ b for a, b in zip(raw, mask))
            return str(ipaddress.ip_address(raw))
        offset = end + (-size % 4)
    return None


def probe(item):
    """Called in an isolated short-lived worker; no retries, redirects, credentials or env proxy."""
    kind = item['type']
    family = item.get('family', 'auto')
    if kind in ('https', 'egress'):
        url = urlsplit(item['url'])
        if item['route'] == 'proxy':
            proxy = urlsplit(item['proxy'])
            connection = http.client.HTTPSConnection(proxy.hostname, proxy.port, timeout=4, context=ssl.create_default_context())
            connection.set_tunnel(url.hostname, 443)
        else:
            connection = http.client.HTTPSConnection(url.hostname, 443, timeout=4, context=ssl.create_default_context())
            connection._create_connection = lambda addr, timeout, *args: connect_family(addr, timeout, family)
        try:
            connection.request('HEAD' if kind == 'https' else 'GET', url.path or '/', headers={'User-Agent': 'Claude-Environment-Check/0.6', 'Connection': 'close'})
            response = connection.getresponse()
            result = {'outcome': 'response', 'http_status': response.status, 'tls_verified': True}
            if kind == 'egress' and response.status == 200:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    return {'outcome': 'response_too_large'}
                text = raw.decode('utf-8').strip()
                fmt = item['response_format']
                value = text if fmt == 'ip' else json.loads(text).get('ip') if fmt == 'json_ip' else dict(line.split('=', 1) for line in text.splitlines() if '=' in line).get('ip')
                result['ip'] = str(ipaddress.ip_address(value))
            return result
        finally:
            connection.close()
    wanted = {'auto': socket.AF_UNSPEC, 'ipv4': socket.AF_INET, 'ipv6': socket.AF_INET6}[family]
    if kind == 'dns':
        addresses = {str(ipaddress.ip_address(row[4][0])) for row in socket.getaddrinfo(item['host'], 443, wanted, socket.SOCK_STREAM)}
        return {'outcome': 'resolved', 'addresses': sorted(addresses)} if addresses else {'outcome': 'no_answer'}
    addresses = socket.getaddrinfo(item['host'], item['port'], wanted, socket.SOCK_DGRAM)
    if not addresses:
        return {'outcome': 'no_answer'}
    af, socktype, proto, _, sockaddr = addresses[0]
    transaction = os.urandom(12)
    with socket.socket(af, socktype, proto) as sock:
        sock.settimeout(3)
        sock.connect(sockaddr)
        sock.send(struct.pack('!HHI', 1, 0, 0x2112A442) + transaction)
        answer = parse_stun(sock.recv(2048), transaction)
    return {'outcome': 'stun_response', 'ip': answer} if answer else {'outcome': 'invalid_stun_response'}


def isolated_probe(item):
    try:
        run = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'],
                             input=json.dumps(item), capture_output=True, text=True, timeout=9,
                             env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        if run.returncode or len(run.stdout) > 65536:
            return {'outcome': 'worker_failed'}
        value = json.loads(run.stdout)
        return value if isinstance(value, dict) else {'outcome': 'worker_failed'}
    except subprocess.TimeoutExpired:
        return {'outcome': 'timeout'}
    except (OSError, ValueError):
        return {'outcome': 'worker_failed'}


def row(item, observation):
    kind = item['type']
    outcome = observation.get('outcome')
    complete = False
    comparison = 'unavailable'
    reason = '探测未取得有效结果；超时或无响应不能证明流量已阻断。'
    action = '检查探测目标、解析、代理或网络后重测；保留未完成。'
    reason = {'timeout': '探测超时；无响应不能证明 UDP 被阻断或没有泄漏。',
              'network_error': '连接或解析失败，未取得有效网络证据。',
              'tls_error': 'TLS 证书或握手校验失败，未继续请求；不能关闭验证来通过。',
              'invalid_stun_response': 'STUN 响应的事务、长度或地址格式不符，不能作为出口证据。',
              'invalid_response': '响应格式不符，无法读取有效证据。',
              'response_too_large': '响应超过读取上限，已停止处理。',
              'worker_failed': '探测子进程未正常完成，不能据此认定网络安全。'}.get(outcome, reason)
    if kind == 'https' and outcome == 'response':
        complete = observation.get('http_status') in item['expected_statuses']
        reason = '指定探测路径的 TLS 与 HTTP 响应符合预期；不代表登录、模型请求或其他进程路径。' if complete else 'TLS 已建立，但 HTTP 状态不符合预期；可能需要实际浏览器处理登录、跳转或挑战。'
        if not complete:
            reason += ' HTTP 状态：' + str(observation.get('http_status')) + '。'
        action = '继续验证实际客户端功能。' if complete else '在实际客户端核对响应，不能将重定向、401 或 403 自动记为功能通过。'
    elif kind == 'dns' and outcome == 'resolved':
        complete = bool(observation.get('addresses'))
        reason = '系统解析器取得地址；仅证明解析有结果，不证明 DNS 上游出口或代理规则。'
        action = '结合核心日志或目标机流量核实 DNS 查询路径。'
    elif kind in ('stun', 'egress') and observation.get('ip'):
        expected = item.get('expected_ip')
        complete = expected is not None and ipaddress.ip_address(expected) == ipaddress.ip_address(observation['ip'])
        comparison = 'matched' if complete else 'mismatch' if expected is not None else 'no_reference'
        reason = '该探测目标的出口与已确认地址一致；不代表其他域名、出站组、应用或地址族。' if complete else '已取得出口，但尚无已确认的预期地址，或与预期不符。'
        action = '保留本次证据，并按约定范围验证其他路径。' if complete else '在本地私有证据中核对出口和指定节点；确认目标后再检测，不自动接受新出口。'
    result = {'id': item['id'], 'title': {'https': 'HTTPS 可达性', 'egress': '出口一致性', 'dns': '系统 DNS 解析', 'stun': '原生 UDP / STUN 出口'}[kind] + ' · ' + item['id'],
            'status': '已完成' if complete else '未完成', 'required': item['required'], 'reason': reason, 'next_step': action,
            'probe_type': kind,
            'probe_path': item.get('route', 'native_udp' if kind == 'stun' else 'system_resolver'),
            'outcome': outcome if outcome in {'response','resolved','stun_response','timeout','network_error','tls_error','invalid_response','invalid_stun_response','no_answer','worker_failed','response_too_large'} else 'invalid_response'}
    if kind in ('egress', 'stun'):
        result['egress_comparison'] = comparison
    return result


def run_checks(c, plan, allow_network, readiness=None, config=None, browser=None):
    c.require(allow_network, 'EXPLICIT_NETWORK_OPT_IN_REQUIRED')
    validate_plan(c, plan)
    import dns_readiness
    service = plan.get('phase', 'service') == 'service'
    proxy_checks = [x for x in plan['checks'] if x['type'] in ('https', 'egress')]
    proxies = {tuple(dns_readiness.proxy_identity(c, x['proxy'])) for x in proxy_checks if x.get('route') == 'proxy'}
    scope_error = service and (any(x.get('route') != 'proxy' for x in proxy_checks) or len(proxies) > 1)
    proxy = next((x.get('proxy') for x in proxy_checks if x.get('route') == 'proxy'), None)
    rows, private = [], []
    for index, item in enumerate(plan['checks']):
        if service:
            ready, code = (False, 'DNS_READY_PROXY_SCOPE_CHANGED') if scope_error else dns_readiness.check(c, readiness, config, browser, proxy)
            if not ready:
                rows.append({'id': 'dns_readiness_gate', 'title': 'DNS 与代理前置核验', 'status': '未完成', 'required': True,
                             'reason': '尚无当前有效的 DNS/代理读回和路径核验记录，或网络设置已变化。本轮剩余服务请求未发送。',
                             'next_step': '先配置、读回并以非 AI 目标核验 DNS/代理路径，记录真实证据后重试。', 'outcome': code})
                for pending in plan['checks'][index:]:
                    rows.append({'id': pending['id'], 'title': '待前置核验 · ' + pending['id'], 'status': '未完成',
                                 'required': pending['required'], 'reason': '前置核验未满足，未发送该请求。',
                                 'next_step': '先完成 DNS/代理核验，再执行服务阶段。', 'outcome': 'not_sent'})
                break
        result = isolated_probe(item)
        rows.append(row(item, result))
        private.append({'id': item['id'], 'observation': result})
    return rows, private


if __name__ == '__main__':
    if sys.argv[1:] != ['--worker']:
        sys.exit(1)
    try:
        result = probe(json.loads(sys.stdin.read(65536)))
    except ssl.SSLError:
        result = {'outcome': 'tls_error'}
    except (socket.timeout, TimeoutError):
        result = {'outcome': 'timeout'}
    except OSError:
        result = {'outcome': 'network_error'}
    except Exception:
        result = {'outcome': 'invalid_response'}
    print(json.dumps(result))
