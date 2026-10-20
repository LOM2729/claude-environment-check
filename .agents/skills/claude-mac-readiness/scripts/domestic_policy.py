"""Offline pinned domestic rules and a narrow video UDP exception. No live writes."""
import copy
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

import ai_routing as ai
import unified_policy as unified

POLICY = 'domestic-v4'
VIDEO = 'KIT-CN-VIDEO'
CN = 'KIT-CN-DOMAINS'
VIDEO_RULE = 'RULE-SET,' + VIDEO + ',DIRECT'
CN_RULE = 'RULE-SET,' + CN + ',DIRECT'
UDP_RULE = 'NETWORK,udp,REJECT'


@lru_cache(maxsize=1)
def snapshot():
    root = Path(__file__).parent
    meta = json.loads((root / 'domestic_sources.json').read_text(encoding='utf-8'))
    result = {}
    for key, filename in ((VIDEO, 'domestic_video.list'), (CN, 'domestic_cn.list')):
        data = (root / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != meta['files'][filename]['sha256']:
            raise ValueError('Domestic snapshot checksum mismatch')
        lines = data.decode('utf-8').splitlines()
        if not lines or any(not re.fullmatch(r'(?:\+\.)?[a-z0-9_-]+(?:\.[a-z0-9_-]+)*', s) for s in lines):
            raise ValueError('Unsupported domestic domain pattern')
        result[key] = {'type': 'inline', 'behavior': 'domain', 'payload': lines}
    return result


def managed_rule(obj, rule):
    key = {VIDEO_RULE: VIDEO, CN_RULE: CN}.get(rule)
    return bool(key and obj.get('rule-providers', {}).get(key) == snapshot()[key])


def build_semantics(c, original, fmt, node, group, direct_review=None):
    if fmt == 'shadowrocket':
        import shadow_domestic
        return shadow_domestic.build(c, original, node, group, direct_review)
    c.require(fmt in ('json', 'yaml'), 'DOMESTIC_REQUIRES_MIHOMO_JSON_OR_YAML')
    unknown, decisions = unified.direct_decisions(c, original, fmt, direct_review)
    c.require(not unknown or bool(decisions), 'UNIFIED_DIRECT_REVIEW_REQUIRED')
    domestic_hosts = [s.removeprefix('+.') for provider in snapshot().values() for s in provider['payload']]
    for rule, decision in decisions.items():
        if decision == 'proxy':
            parts = rule.split(',')
            c.require(parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX') and len(parts) == 3,
                      'DOMESTIC_PROXY_EXCEPTION_REVIEW_REQUIRED')
            host = parts[1].lower().rstrip('.')
            c.require(not any(host == h or host.endswith('.' + h) or
                              (parts[0] == 'DOMAIN-SUFFIX' and h.endswith('.' + host)) for h in domestic_hosts),
                      'DOMESTIC_PROXY_EXCEPTION_CONFLICT')
    base = copy.deepcopy(original)
    providers = base.setdefault('rule-providers', {})
    c.require(isinstance(providers, dict), 'DOMESTIC_PROVIDERS_INVALID')
    managed = any(k in providers for k in (VIDEO, CN))
    if managed:
        c.require(all(providers.get(k) == snapshot()[k] for k in (VIDEO, CN)), 'DOMESTIC_MANAGED_PROVIDER_CHANGED')
        for rule in (VIDEO_RULE, CN_RULE):
            c.require(base['rules'].count(rule) == 1, 'DOMESTIC_MANAGED_RULE_CHANGED')
        c.require(UDP_RULE in base['rules'], 'DOMESTIC_UDP_GUARD_MISSING')
        base['rules'] = [r for r in base['rules'] if r not in (VIDEO_RULE, CN_RULE, UDP_RULE)]
        for key in (VIDEO, CN): del providers[key]
    # Only exact unconditional UDP rejects can be relocated automatically.
    # More complex rejects remain subject to the existing structural review.
    base['rules'] = [r for r in base.get('rules', []) if r.replace(' ', '').lower() not in
                     ('network,udp,reject', 'network,udp,reject-drop', 'network,udp,reject-no-drop')]
    review = None
    remaining, _ = unified.direct_decisions(c, base, fmt)
    if remaining:
        review = {'schema': 'claude-direct-review/1', 'config_semantic_sha256': c.sha(c.encode(base)),
                  'entries': [{'rule': r, 'decision': decisions[r], 'reason': 'Retained explicit baseline decision.'} for r in dict.fromkeys(remaining)]}
    result = unified.build_semantics(c, base, fmt, node, group, review)
    guards = ai.guarded_rules(ai.catalog(c), fmt, group)
    rules = result['rules']
    at = next(i for i in range(len(rules)) if rules[i:i + len(guards)] == guards)
    leading = [r for r in rules[:at] if r != unified.V6_RULE]
    # Do not override a customer deny that might cover an AI hostname.
    catalog = ai.catalog(c)
    hosts = catalog['suffixes'] + catalog['exact_hosts']
    for rule in leading:
        parts = rule.split(',')
        c.require(parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX') and len(parts) == 3
                  and not any(h == parts[1] or h.endswith('.' + parts[1]) or parts[1].endswith('.' + h) for h in hosts),
                  'DOMESTIC_EXISTING_DENY_REVIEW_REQUIRED')
    tail = [r for r in rules[at + len(guards):] if r != unified.V6_RULE]
    result['rules'] = guards + [unified.V6_RULE] + leading + [VIDEO_RULE, UDP_RULE, CN_RULE] + tail
    result['rule-providers'].update(copy.deepcopy(snapshot()))
    return result


def audit(c, baseline, candidate, fmt, node, group=ai.GROUP, direct_review=None):
    expected = build_semantics(c, c.parse_config(baseline, fmt), fmt, node, group, direct_review)
    match = expected == c.parse_config(candidate, fmt)
    return {'schema': 'claude-setup-ai-audit/1', 'policy': POLICY,
            'status': 'static_policy_matches' if match else 'unexpected_policy_or_other_changes',
            'domestic_video_udp_order': match, 'unified_proxy_rules': match,
            'runtime_verified': False, 'system_udp_verified': False, 'application_loaded': 'not_verified'}


def prepare(c, current, fmt, node, output, group=ai.GROUP, direct_review=None):
    baseline = c.read_bytes(current)
    fmt = c.config_format(current, fmt)
    expected = build_semantics(c, c.parse_config(baseline, fmt), fmt, node, group, direct_review)
    if fmt == 'json':
        candidate = c.encode(expected)
    else:
        render = unified.render_shadow if fmt == 'shadowrocket' else unified.render_yaml
        candidate = render(c, c.decode(baseline), expected).encode()
    c.require(len(candidate) <= c.MAX_FILE, 'INPUT_TOO_LARGE')
    review = audit(c, baseline, candidate, fmt, node, group, direct_review)
    c.new_dir(output)
    folder = Path(output)
    path = folder / ('candidate.' + ('conf' if fmt == 'shadowrocket' else fmt))
    c.write_new(path, candidate)
    if candidate != baseline:
        c.prepare_plan(current, path, fmt, folder / 'plan')
        c.require(c.read_bytes(folder / 'plan/original.bin') == baseline, 'UNIFIED_BASELINE_CHANGED')
    c.write_new(folder / 'ai-audit.json', c.encode(review))
    return {'status': 'ai_candidate_prepared', 'policy': POLICY, 'content_changed': candidate != baseline,
            'apply_supported': False, 'runtime_verified': False}


def udp_check(c, config, fmt):
    from readiness_lifecycle import item
    data = c.parse_config(c.read_bytes(config), c.config_format(config, fmt))
    hits = []
    def walk(value, path='config'):
        if isinstance(value, dict):
            for key, child in value.items():
                if 'udp' in key.lower(): hits.append({'path': path + '.' + key, 'value': child})
                walk(child, path + '.' + key)
        elif isinstance(value, list):
            for i, child in enumerate(value): walk(child, path + '[' + str(i) + ']')
        elif isinstance(value, str) and re.search(r'(?i)\budp\b', value):
            hits.append({'path': path, 'value': value})
    walk(data)
    rows = [item('udp_config_inventory', 'UDP 配置位置盘点', True,
                 '已读取文件内 UDP 字段和规则；详细值仅存本机私有记录。', '区分节点/组限制、路由拦截与应用全局开关，核对真正活动配置。'),
            item('udp_host_scope', '系统与应用全局 UDP 限制', False,
                 '配置文件不能证明系统防火墙、客户端开关、浏览器或 TUN 接管状态。',
                 'Mac 核对网络过滤器/PF与客户端；Windows 核对有效防火墙策略与客户端。仅调整已确认冲突的具体规则，不关闭整个防火墙。'),
            item('udp_video_runtime', '视频 UDP 与其余 UDP 实际路径', False,
                 '尚未在客户机验证视频/CDN命中与其余 UDP 拦截。',
                 '核对 TUN/透明接管和 DNS 劫持；经批准测试视频 UDP、普通国内/未知/AI UDP 与 TCP，不能把可播放等同 UDP 已通过。')]
    return rows, hits
