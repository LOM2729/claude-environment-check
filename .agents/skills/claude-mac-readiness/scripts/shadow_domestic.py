"""Shadowrocket native offline domain expansion, never changes active app state."""
from functools import lru_cache
import re

import ai_routing as ai
import claude_group
import community_routing as community
import unified_policy as unified

UDP_RULE = 'AND,((PROTOCOL,UDP),(PROTOCOL,UDP)),REJECT-NO-DROP'
V6_RULE = 'IP-CIDR,::/0,REJECT,no-resolve'


@lru_cache(maxsize=1)
def native_blocks():
    from domestic_policy import snapshot, VIDEO, CN
    def convert(values):
        return ['DOMAIN-SUFFIX,' + s[2:] + ',DIRECT' if s.startswith('+.') else
                'DOMAIN,' + s + ',DIRECT' for s in values]
    source = snapshot()
    return convert(source[VIDEO]['payload']), convert(source[CN]['payload'])


def managed_span(c, original):
    rules = original.get('rule', [])
    if UDP_RULE not in rules:
        return None
    c.require(rules.count(UDP_RULE) == 1, 'SHADOW_DOMESTIC_DUPLICATE_GUARD')
    video, cn = native_blocks()
    at = rules.index(UDP_RULE)
    start, end = at - len(video), at + 1 + len(cn)
    if not any(r.startswith('AND,((DOMAIN') for r in rules) and len(rules) < len(cn):
        # An existing standalone global UDP deny is an input rule, not our marker.
        return None
    c.require(start >= 0 and rules[start:at] == video and rules[at + 1:end] == cn,
              'SHADOW_DOMESTIC_MANAGED_BLOCK_CHANGED')
    return start, end


def build(c, original, node, group, direct_review=None):
    from domestic_policy import snapshot
    unknown, decisions = unified.direct_decisions(c, original, 'shadowrocket', direct_review)
    c.require(not unknown or bool(decisions), 'UNIFIED_DIRECT_REVIEW_REQUIRED')
    hosts = [s.removeprefix('+.') for p in snapshot().values() for s in p['payload']]
    for rule, decision in decisions.items():
        if decision == 'proxy':
            parts = rule.split(',')
            c.require(parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX') and len(parts) == 3,
                      'DOMESTIC_PROXY_EXCEPTION_REVIEW_REQUIRED')
            host = parts[1].lower().rstrip('.')
            c.require(not any(host == h or host.endswith('.' + h) or
                              (parts[0] == 'DOMAIN-SUFFIX' and h.endswith('.' + host)) for h in hosts),
                      'DOMESTIC_PROXY_EXCEPTION_CONFLICT')
    base = claude_group.normalize(c, original, 'shadowrocket', node, group, ai.catalog(c))
    span = managed_span(c, base)
    if span:
        start, end = span
        base['rule'] = base['rule'][:start] + base['rule'][end:]
        base['rule'] = [r for r in base['rule'] if r != V6_RULE]
    # Bare PROTOCOL is not emitted. Recognize old bare UDP rejects only to replace
    # them with a native logical rule; don't silently relocate arbitrary conditions.
    base['rule'] = [r for r in base.get('rule', []) if r != UDP_RULE and r.replace(' ', '').lower() not in
                    ('protocol,udp,reject', 'protocol,udp,reject-drop', 'protocol,udp,reject-no-drop')]
    remaining, _ = unified.direct_decisions(c, base, 'shadowrocket')
    review = None
    if remaining:
        review = {'schema': 'claude-direct-review/1', 'config_semantic_sha256': c.sha(c.encode(base)),
                  'entries': [{'rule': r, 'decision': decisions[r], 'reason': 'Retained explicit baseline decision.'} for r in dict.fromkeys(remaining)]}
    result = unified.build_semantics(c, base, 'shadowrocket', node, group, review)
    guards = ai.guarded_rules(ai.catalog(c), 'shadowrocket', group)
    rules = result['rule']
    at = next(i for i in range(len(rules)) if rules[i:i + len(guards)] == guards)
    leading = [r for r in rules[:at] if r != unified.V6_RULE]
    data = ai.catalog(c)
    protected = data['suffixes'] + data['exact_hosts']
    for rule in leading:
        parts = rule.split(',')
        c.require(parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX') and len(parts) == 3
                  and not any(h == parts[1] or h.endswith('.' + parts[1]) or parts[1].endswith('.' + h) for h in protected),
                  'DOMESTIC_EXISTING_DENY_REVIEW_REQUIRED')
        c.require(not community.deny_overlap(parts[0], parts[1]), 'DOMESTIC_EXISTING_DENY_REVIEW_REQUIRED')
    tail = [r for r in rules[at + len(guards):] if r != unified.V6_RULE]
    video, cn = native_blocks()
    result['rule'] = guards + [V6_RULE] + leading + video + [UDP_RULE] + cn + tail
    # Supported native spelling from the vendor-shipped default.conf. Preserve all
    # unrelated DNS and app settings; reject ambiguous alternate spellings.
    general = result.setdefault('general', [])
    c.require(not any(re.match(r'^\s*udp-policy-not-supported-behavior\s*=', x, re.I) for x in general),
              'SHADOW_UDP_SETTING_SPELLING_REVIEW_REQUIRED')
    result['general'] = [x for x in general if not re.match(r'^\s*udp-policy-not-supported-behaviour\s*=', x, re.I)]
    result['general'].append('udp-policy-not-supported-behaviour = REJECT')
    return claude_group.add(c, result, 'shadowrocket', node, group, data)
