"""Offline checks for implicit service contact before proxy activation or UI actions."""
from urllib.parse import urlsplit
import re

import ai_routing
import dns_readiness
import readiness_lifecycle as life

SERVICE_ACTIONS = {'browser-start', 'browser-restart', 'client-install', 'client-update',
                   'client-start', 'client-login', 'cli-diagnostic', 'service-page'}


def protected(c, value):
    data = ai_routing.catalog(c)
    host = value.lower().rstrip('.')
    return host in data['exact_hosts'] or any(host == suffix or host.endswith('.' + suffix) for suffix in data['suffixes'])


def scan(c, config, fmt='auto'):
    fmt = c.config_format(config, fmt)
    data = c.parse_config(c.read_bytes(config), fmt)
    rows, evidence = [], []
    number = 0
    def add(kind, value=None, unknown=False):
        nonlocal number
        number += 1
        flagged = unknown
        category = 'unknown' if unknown else 'non_ai_target'
        if value is not None:
            parsed = urlsplit(value if '://' in str(value) else 'https://' + str(value))
            hostname = parsed.hostname
            invalid_host = not hostname or any(ch in hostname for ch in ('%', ' ', '{', '}', '<', '>'))
            flagged = invalid_host or parsed.scheme not in ('http', 'https', 'tls', 'tcp', 'udp', 'quic', 'h3') or protected(c, hostname)
            category = 'ai_target' if hostname and protected(c, hostname) else 'unknown' if flagged else 'non_ai_target'
        rows.append(life.item('implicit_' + str(number), kind, not flagged,
            '发现 AI 服务目标或无法静态确认的自动行为，暂不能在初始化阶段启用。' if flagged else '已识别为非 AI 目标；仍需纳入明确的初始化联网范围。',
            '先审阅本地私有明细，准备并批准临时离线或非 AI 初始化方案；不要静默改客户地址。' if flagged else '确认该目标及数据流已在本轮批准范围，并核对客户端附加检测。'))
        evidence.append({'index': number, 'kind': kind, 'category': category, 'value': value})
    if fmt == 'shadowrocket':
        for section, lines in data.items():
            if section in ('script', 'url rewrite', 'map local', 'mitm') and lines:
                add('小火箭脚本或扩展行为', unknown=True)
            for line in lines:
                if re.search(r'(?i)\b(?:url|health|test|update|include|subscription)\b', line):
                    urls = re.findall(r'(?:https?|tls|quic)://[^\s,]+', line)
                    if urls:
                        for url in urls: add('小火箭外部资源或自动检测', url)
                    else: add('小火箭自动行为待确认', unknown=True)
        add('小火箭应用级测速/订阅/自动启动状态需现场核对', unknown=True)
    else:
        for index, group in enumerate(data.get('proxy-groups', [])):
            if not isinstance(group, dict):
                add('策略组格式未知', unknown=True); continue
            if group.get('type') in ('url-test', 'fallback', 'load-balance') or 'url' in group:
                add('策略组自动测速', group.get('url'), unknown=not bool(group.get('url')))
        for section in ('proxy-providers', 'rule-providers'):
            providers = data.get(section, {})
            if not isinstance(providers, dict):
                add('外部资源格式未知', unknown=True); continue
            for provider in providers.values():
                if not isinstance(provider, dict):
                    add('外部资源格式未知', unknown=True); continue
                if (section == 'rule-providers' and provider.get('type') == 'inline'
                        and provider.get('behavior') == 'domain'
                        and set(provider) == {'type', 'behavior', 'payload'}
                        and isinstance(provider.get('payload'), list)
                        and all(isinstance(s, str) and re.fullmatch(r'(?:\+\.)?[a-z0-9_-]+(?:\.[a-z0-9_-]+)*', s) for s in provider['payload'])):
                    # Domain patterns are data; this bounded inline provider cannot download or run code.
                    continue
                if provider.get('url'): add('订阅或规则资源下载', provider['url'])
                # Remote/cached content is a separate input and may contain new hosts/options.
                add('未读取的 provider 内容需物化并审阅', unknown=True)
                health = provider.get('health-check')
                if isinstance(health, dict) and health.get('enable') is not False:
                    add('Provider 健康检查', health.get('url'), unknown=not bool(health.get('url')))
        for key in ('script', 'scripts', 'sub-rules', 'tunnels', 'listeners', 'sniffer'):
            if data.get(key): add('扩展行为需要人工核对', unknown=True)
        for key in ('external-ui-url', 'geox-url'):
            value = data.get(key)
            if isinstance(value, str): add('核心附加下载', value)
            elif isinstance(value, dict):
                for url in value.values(): add('核心附加下载', url)
        for proxy in data.get('proxies', []):
            if isinstance(proxy, dict) and proxy.get('server') and protected(c, str(proxy['server']).strip('[]')):
                add('代理节点地址属于 AI 域名', str(proxy['server']))
        dns = data.get('dns', {})
        def dns_targets(value):
            if isinstance(value, dict):
                for child in value.values(): dns_targets(child)
            elif isinstance(value, list):
                for child in value: dns_targets(child)
            elif isinstance(value, str):
                # Nameserver schemes and literal resolver values only, not domain policy keys.
                if value not in ('system', 'dhcp'):
                    add('DNS 上游或引导解析目标', value.split('#', 1)[0])
        if isinstance(dns, dict):
            for key in ('default-nameserver', 'proxy-server-nameserver', 'nameserver', 'fallback', 'nameserver-policy', 'direct-nameserver'):
                if key in dns: dns_targets(dns[key])
    if not rows:
        rows.append(life.item('implicit_none', '配置文件隐含请求检查', True, '该文件中未发现已支持字段里的隐含请求。', '仍需核对应用级 AI 检测、订阅刷新和已运行会话；静态扫描不证明运行时没有其他请求。'))
    return rows, evidence


def gate(c, action, config, fmt, readiness, proxy, browser=None):
    if action == 'proxy-load':
        rows, evidence = scan(c, config, fmt)
        return rows, evidence
    c.require(action in SERVICE_ACTIONS, 'ACTION_NOT_SUPPORTED')
    dns_readiness.proxy_identity(c, proxy)
    ready, code = dns_readiness.check(c, readiness, config, browser, proxy)
    return [life.item('service_action_gate', '服务动作前置核验', ready,
        '本轮核验记录仍有效且绑定当前网络和代理入口。' if ready else '未满足当前 DNS/代理核验条件，不能执行该安装、登录、打开或重启动作。',
        '仅执行本次已批准动作；浏览器恢复旧标签和安装器自动启动同样计入。' if ready else '先完成网络配置、非 AI 路径核验和本轮记录；独立本机项目继续。')], [{'action': action, 'check': code}]
