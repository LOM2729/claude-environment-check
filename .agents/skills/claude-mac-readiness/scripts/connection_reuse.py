"""Offline TCP keepalive candidates; never infer HTTP reuse or change node protocols.

Mihomo fields verified in its v1.19.0 source and current general documentation.
The supported floor below is our verified floor, not a claim about introduction.
"""
import copy
import re

SOURCE = 'https://wiki.metacubex.one/config/general/#tcp-keep-alive'
VERIFIED_SOURCE = 'https://github.com/MetaCubeX/mihomo/blob/v1.19.0/config/config.go'
TLS_SOURCE = 'https://wiki.metacubex.one/config/proxies/tls/#client-fingerprint'
VERIFIED_FLOOR = (1, 19, 0)
TIMERS = ('keep-alive-idle', 'keep-alive-interval')
DEFAULT_SECONDS = 15


def _row(key, title, done, reason, next_step, required=False):
    return {'id': key, 'title': title, 'status': '已完成' if done else '未完成',
            'required': required, 'reason': reason, 'next_step': next_step}


def _supported(core, version, fmt):
    # A Clash-branded GUI does not identify its actual embedded core.
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', version) if isinstance(version, str) else None
    return (fmt in ('json', 'yaml') and isinstance(core, str) and core.lower() == 'mihomo'
            and bool(match) and VERIFIED_FLOOR <= tuple(map(int, match.groups())) < (2, 0, 0))


def _seconds(value):
    # bool is an int in Python, but not a valid timer; bound to native signed int32.
    return type(value) is int and 0 < value <= 2147483647


def _tls_target(obj, fmt, core, version, node):
    """Return the sole supported local node index, without exposing its identity."""
    if not _supported(core, version, fmt):
        return None, '实际核心、版本或配置格式不在已核实的 Mihomo 支持范围。'
    if not isinstance(node, str) or not node or any(ord(ch) < 32 for ch in node):
        return None, '未明确选择唯一的本地具体节点。'
    proxies, groups = obj.get('proxies', []), obj.get('proxy-groups', [])
    if (not isinstance(proxies, list) or not all(isinstance(p, dict) for p in proxies)
            or not isinstance(groups, list) or not all(isinstance(p, dict) for p in groups)):
        return None, '节点或分组结构未知，不能安全定位单一节点。'
    matches = [i for i, proxy in enumerate(proxies) if proxy.get('name') == node]
    if len(matches) != 1 or any(group.get('name') == node for group in groups):
        return None, '选定名称未唯一对应本地节点，或与分组重名；远程 provider 节点不自动改写。'
    selected = proxies[matches[0]]
    protocol = selected.get('type')
    supported = protocol in ('vmess', 'vless') and selected.get('tls') is True
    supported = supported or protocol == 'trojan'
    if protocol == 'anytls':
        version_tuple = tuple(map(int, version.removeprefix('v').split('.')))
        supported = version_tuple >= (1, 19, 32)
    if not supported:
        return None, '选中节点协议或 TLS 状态未满足已核实条件；不会为适配指纹启用 TLS 或改变协议。'
    return matches[0], None


def _proxy_review(obj, fmt, core, version, node, chrome):
    if fmt == 'shadowrocket':
        return [_row('connection_transport_review', '节点多路复用与 TLS 设置', False,
                     '小火箭节点协议、TLS 指纹和多路复用需结合实际客户端版本核对；未改写节点。',
                     '由 Codex 读取客户端版本及节点协议，核对官方可用项；不要照搬 Mihomo 字段。')]
    proxies = obj.get('proxies', [])
    providers = obj.get('proxy-providers', {})
    valid = (isinstance(proxies, list) and all(isinstance(p, dict) for p in proxies)
             and isinstance(providers, dict))
    # Do not include names, endpoints, headers or credentials in public rows.
    mux = sum(any(k in p for k in ('smux', 'mux', 'multiplex', 'xhttp-opts', 'grpc-opts'))
              for p in proxies) if valid else 0
    fingerprint = sum(any(k in p for k in ('client-fingerprint', 'fingerprint', 'tls', 'reality-opts'))
                      for p in proxies) if valid else 0
    rows = [_row('connection_multiplex_review', '节点多路复用配置审查', valid and not mux and not providers,
                 ('未发现显式 SMUX/MUX/传输复用配置；保持节点协议不变。' if valid and not mux and not providers
                  else '存在传输复用配置、远程节点集合或结构未知；离线配置不能证明服务端兼容。'),
                 '保留现有节点；不为连接复用自动开启 SMUX 或修改服务端。' if valid and not mux and not providers
                 else '核对实际选中节点、协议及服务端支持，保留既有兼容配置，不擅自开启多路复用。')]
    if chrome:
        index, reason = _tls_target(obj, fmt, core, version, node)
        done = index is not None and obj['proxies'][index].get('client-fingerprint') == 'chrome'
        rows.append(_row('connection_tls_fingerprint', '所选节点 Chrome TLS 指纹离线配置', done,
                        ('所选支持协议的本地节点已设 client-fingerprint: chrome；仅证明离线字段。' if done
                         else reason or '所选节点尚未设置 client-fingerprint: chrome。') +
                        '外层代理 TLS 与 Claude 的端到端 TLS 不同，不能据此声称业务等同 Chrome。',
                        '将私有差异纳入批准方案，备份、核心校验、导入后读回；证书指纹 fingerprint、SMUX 和其他节点保持不变。'))
    else:
        rows.append(_row('connection_tls_fingerprint', 'TLS 指纹适配审查', False,
                     ('发现显式 TLS/指纹字段；未修改或输出具体节点内容。' if fingerprint
                      else '未确认实际节点协议与 TLS 指纹能力。') +
                     '外层代理 TLS 与 Claude 的端到端 TLS 是不同连接，设置外层 chrome 不证明业务等同 Chrome。',
                         '按实际节点协议和核心版本核对 client-fingerprint 支持；本工具不统一覆盖指纹、不启用 MITM。'))
    return rows


def audit(c, obj, fmt, *, core=None, version=None, node=None, chrome=False):
    """Return public, schema-compatible rows; only inspect the supplied object."""
    c.require(isinstance(obj, dict), 'CONNECTION_CONFIG_OBJECT_REQUIRED')
    c.require(fmt in ('json', 'yaml', 'shadowrocket'), 'CONNECTION_FORMAT_UNSUPPORTED')
    c.require(type(chrome) is bool, 'CONNECTION_CHROME_BOOLEAN_REQUIRED')
    supported = _supported(core, version, fmt)
    rows = [_row('connection_core_support', 'TCP 保活字段支持', supported,
                 '已提供受支持范围内的 Mihomo 版本；仍须本机核心校验和配置读回。' if supported
                 else ('未核实小火箭存在等价全局保活字段，保持原配置。' if fmt == 'shadowrocket'
                       else '实际核心或版本未知、过旧或不在已核实范围，不能按客户端名称猜支持。'),
                 '使用实际核心对候选做离线配置校验，导入后读回；需要重启时由客户手动操作。' if supported
                 else '由 Codex 获取实际核心版本；Mihomo 本工具已核实的支持下限为 1.19.0（不是首次引入版本）。')]
    disabled = obj.get('disable-keep-alive')
    timers_ok = all(_seconds(obj.get(k)) for k in TIMERS)
    done = supported and disabled is False and timers_ok
    if done:
        reason = ('离线文件已显式启用 TCP 保活；idle=' + str(obj[TIMERS[0]]) +
                  ' 秒，interval=' + str(obj[TIMERS[1]]) + ' 秒。尚未证明活动核心已采用。')
    elif not supported:
        reason = '字段适配尚未核实；本项未判定完成。'
    else:
        reason = 'TCP 保活未显式启用，或计时字段缺失/不是有效的正整数；未把默认行为当成已读回。'
    rows.append(_row('connection_tcp_keepalive', 'TCP 保活离线配置', done, reason,
                     '导入批准的候选后读回活动配置；不以 TCP 保活代替 HTTP 连接复用验证。' if done
                     else '在核心适配确认后准备候选与差异，经批准备份、导入并读回。'))
    rows.extend(_proxy_review(obj, fmt, core, version, node, chrome))
    rows.append(_row('connection_http_reuse', 'Claude HTTP 连接复用实际采用', False,
                     '本工具仅离线检查 TCP 保活。TCP 保活、HTTP 连接池复用和代理 SMUX 是不同机制；未发送业务请求。',
                     'DNS/代理前置检查完成后，在已批准的真实客户端会话核对长连接和重连原因；不频繁重启、不做循环请求压测。'))
    return rows


def build(c, obj, fmt, *, core=None, version=None, node=None, chrome=False):
    """Prepare an in-memory candidate only. Existing positive timers are preserved.

    Unknown and Shadowrocket configurations return an unchanged deep copy.
    The caller must render, diff, back up, get approval and use normal import/readback.
    """
    audit(c, obj, fmt, core=core, version=version, node=node, chrome=chrome)
    candidate = copy.deepcopy(obj)
    if _supported(core, version, fmt):
        candidate['disable-keep-alive'] = False
        for key in TIMERS:
            if not _seconds(candidate.get(key)):
                candidate[key] = DEFAULT_SECONDS
    if chrome:
        index, _ = _tls_target(candidate, fmt, core, version, node)
        if index is not None:
            candidate['proxies'][index]['client-fingerprint'] = 'chrome'
    return candidate, audit(c, candidate, fmt, core=core, version=version, node=node, chrome=chrome)


def result(rows):
    """Public JSON summary; no node identities or credentials are included."""
    return {'schema': 'claude-connection-reuse/1', 'rows': rows,
            'completed': sum(row['status'] == '已完成' for row in rows),
            'incomplete': sum(row['status'] == '未完成' for row in rows),
            'runtime_verified': False, 'http_reuse_verified': False,
            'system_settings_changed': False, 'sources': [SOURCE, VERIFIED_SOURCE, TLS_SOURCE]}
