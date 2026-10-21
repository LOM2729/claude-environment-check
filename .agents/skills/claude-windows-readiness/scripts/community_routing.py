"""Explicit community-expanded policy, using only bundled and hash-checked snapshots.

This routing scope is a user-selected policy, not proof of service ownership,
mandatory telemetry, or account safety. NTP UDP remains blocked by policy.
"""
import hashlib
import ipaddress
import json
from functools import lru_cache
from pathlib import Path
import re

EXACT = ('anthropic.com.cdn.cloudflare.net', 'servd-anthropic-website.b-cdn.net',
         'anthropic.auth0.com', 'anthropic-com.ghost.io', 'cdn.usefathom.com')
SHARED = ('sentry.io', 'statsigapi.net', 'intercom.io', 'intercomcdn.com')
KEYWORDS = ('datadog', 'sentry', 'sift')


@lru_cache(maxsize=1)
def snapshot():
    data = json.loads(Path(__file__).with_name('community_snapshot.json').read_text(encoding='utf-8'))
    if data.get('schema') != 'claude-community-snapshot/1':
        raise ValueError('Unsupported community snapshot')
    for source in list(data['files'].values()) + [data['asn']]:
        if hashlib.sha256(source['text'].encode()).hexdigest() != source['sha256']:
            raise ValueError('Community snapshot checksum mismatch')
    return data


def expand(data, category, stack=()):
    if category in stack:
        raise ValueError('Recursive community include')
    result = []
    for raw in data['files'][category]['text'].splitlines():
        value = raw.split('#', 1)[0].strip()
        if not value:
            continue
        value = value.split()[0]  # Preserve membership; @cn is an attribute, not a filter.
        if value.startswith('include:'):
            result.extend(expand(data, value.split(':', 1)[1], stack + (category,)))
            continue
        kind, host = ('DOMAIN', value[5:]) if value.startswith('full:') else ('DOMAIN-SUFFIX', value)
        if not re.fullmatch(r'[a-z0-9_-]+(?:\.[a-z0-9_-]+)+', host):
            raise ValueError('Unsupported community domain syntax')
        result.append((kind, host))
    return list(dict.fromkeys(result))


def matches():
    data = snapshot()
    domains = expand(data, 'anthropic')
    domains += [('DOMAIN', host) for host in EXACT]
    domains += [('DOMAIN-SUFFIX', host) for host in SHARED]
    domains += [('DOMAIN-KEYWORD', host) for host in KEYWORDS]
    domains += expand(data, 'category-ntp')
    # Expand ASN data offline. Never emit IP-ASN/GEOSITE, which may trigger a
    # first-run database fetch. The snapshot represents its recorded time only.
    prefixes = ['160.79.104.0/21']
    for entry in json.loads(data['asn']['text'])['data']['prefixes']:
        network = ipaddress.ip_network(entry['prefix'])
        if network.version == 4:
            prefixes.append(str(network))
    domains += [('IP-CIDR', value) for value in prefixes]
    return list(dict.fromkeys(domains))


def guarded_rules(fmt, group):
    protocol = 'PROTOCOL,UDP' if fmt == 'shadowrocket' else 'NETWORK,udp'
    reject = 'REJECT-NO-DROP' if fmt == 'shadowrocket' else 'REJECT'
    rules = []
    for kind, value in matches():
        match = kind + ',' + value
        # no-resolve must be an option on the atomic IP rule, including inside
        # the logical UDP rule. Never let an IP fallback initiate DNS resolution.
        option = ',no-resolve' if kind == 'IP-CIDR' else ''
        rules.extend((f'AND,(({match}{option}),({protocol})),{reject}',
                      f'{match},{group}{option}', f'{match},REJECT{option}'))
    return rules


def deny_overlap(kind, host):
    """Conservative conflict review against newly protected domain space."""
    host = host.lower().rstrip('.')
    for protected_kind, value in matches():
        if protected_kind == 'IP-CIDR':
            continue
        if protected_kind == 'DOMAIN-KEYWORD':
            if value in host or (kind == 'DOMAIN-SUFFIX' and host in value):
                return True
        elif host == value or value.endswith('.' + host) or (
                protected_kind == 'DOMAIN-SUFFIX' and host.endswith('.' + value)):
            return True
    return False


def audit_scope():
    data = snapshot()
    asn = json.loads(data['asn']['text'])['data']
    return {'revision': data['revision'], 'geosite_commit': data['geosite_commit'],
            'expanded_matches': len(matches()), 'asn': '399358',
            'asn_snapshot_end': asn['query_endtime'],
            'asn_live_coverage_verified': False, 'ntp_udp': 'rejected',
            'asn_snapshot_limit': 'RIPEstat observed announcements at the recorded time; low-visibility routes may be omitted and future changes are not covered.',
            'ipv6': 'disabled_and_rejected', 'shared_scope': 'explicit_community_expansion',
            'requires_runtime_database_download': False}


def coverage(c, obj, fmt, node, group, summary=None):
    """Per-target static checks for customer reports, never runtime claims."""
    from readiness_lifecycle import item
    import ai_routing as ai
    valid_layout = True
    try:
        ai.layout(c, obj, fmt, node, group, permit_group=True)
    except (c.SetupError, KeyError, TypeError, ValueError, AttributeError):
        valid_layout = False
    if summary is not None:
        valid_layout = valid_layout and isinstance(summary, dict) and all(
            summary.get(key) == 0 for key in
            ('duplicate_names', 'cyclic_groups', 'rules_after_catchall', 'unknown_references'))
    key = 'rule' if fmt == 'shadowrocket' else 'rules'
    expected = guarded_rules(fmt, group + '-Claude')
    rules = obj.get(key, [])
    if not isinstance(rules, list):
        rules = []
    groups = obj.get('proxy group' if fmt == 'shadowrocket' else 'proxy-groups', [])
    if not valid_layout:
        binding = False
    elif fmt == 'shadowrocket':
        binding = all([entry.replace(' ', '') for entry in groups
                       if entry.split('=', 1)[0].strip() == name] ==
                      [(name + '=select,' + node).replace(' ', '')]
                      for name in (group, group + '-Claude'))
    else:
        binding = all([entry for entry in groups if isinstance(entry, dict) and entry.get('name') == name]
                      == [ai.expected_group(node, name)] for name in (group, group + '-Claude'))
    prefix = rules[:len(expected)] == expected
    rows = []
    for index, (kind, value) in enumerate(matches()):
        found = valid_layout and binding and prefix and rules[index * 3:index * 3 + 3] == expected[index * 3:index * 3 + 3]
        rows.append(item('community_route_' + str(index), '配置文件保护：' + kind + ' ' + value, found,
                         '已核对置顶 TCP 指定组、UDP 拒绝和失败拒绝；这是文件静态核对，未证明客户端已加载或流量已通过。' if found else
                         ('配置结构、运行模式或本地具体节点无效，不能确认此目标已受保护。' if not valid_layout else
                          '缺少完整置顶规则或指定节点绑定；尚未达到教程扩展策略。'),
                         '导入后按启动门禁核对活动配置和实际连接链；需要重启时由客户手动操作。'))
    rows.append(item('community_runtime', '教程扩展规则实际流量验收', False,
                     '本命令只读配置文件，不能证明客户机实际网络路径；ASN 快照也不等于实时公告。',
                     '经授权在 DNS/代理就绪后进行主动验证；IPv6 保持关闭，NTP UDP 仍拒绝，不宣称 NTP 代理。'))
    return rows
