"""Offline unified proxy/IPv4 candidates. Never loads a core or writes live settings."""
import copy
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import ai_routing as ai

POLICY = 'unified-v4'
V6_RULE = 'IP-CIDR6,::/0,REJECT,no-resolve'


def normalize(c, original, fmt, node, group, catalog):
    """Remove only a precisely recognized prior managed block for an idempotent upgrade."""
    base = copy.deepcopy(original)
    rulekey = 'rule' if fmt == 'shadowrocket' else 'rules'
    rules = base.get(rulekey, [])
    guarded = ai.guarded_rules(catalog, fmt, group)
    starts = [i for i in range(len(rules)) if rules[i:i + len(guarded)] == guarded]
    c.require(len(starts) <= 1, 'UNIFIED_DUPLICATE_MANAGED_RULES')
    if starts:
        at = starts[0]
        rules = rules[:at] + rules[at + len(guarded):]
        rules = [r for r in rules if r != V6_RULE]
        if fmt == 'shadowrocket':
            existing = [line for line in base.get('proxy group', []) if line.split('=', 1)[0].strip() == group]
            known = {line.split('=', 1)[0].strip() for line in base.get('proxy', [])}
            fields = [x.strip() for x in existing[0].split('=', 1)[1].split(',')] if len(existing) == 1 else []
            c.require(len(fields) == 2 and fields[0].lower() == 'select' and fields[1] in known, 'UNIFIED_EXISTING_GROUP_REVIEW_REQUIRED')
            base['proxy group'].remove(existing[0])
        else:
            matched = [g for g in base.get('proxy-groups', []) if g.get('name') == group]
            prior = matched[0] if len(matched) == 1 else {}
            members = prior.get('proxies', [])
            known = {p['name'] for p in base.get('proxies', [])}
            c.require(isinstance(members, list) and len(members) == 1 and members[0] in known
                      and prior == ai.expected_group(members[0], group), 'UNIFIED_EXISTING_GROUP_REVIEW_REQUIRED')
            base['proxy-groups'] = [g for g in base['proxy-groups'] if g.get('name') != group]
        base[rulekey] = [replace_target(r, node) if ai.target(r) == group else r for r in rules]
    return base


def replace_target(rule, target):
    parts = rule.split(',')
    index = -2 if parts[-1].strip().lower() == 'no-resolve' else -1
    parts[index] = target
    return ','.join(parts)


def direct_decisions(c, original, fmt, review=None):
    rulekey = 'rule' if fmt == 'shadowrocket' else 'rules'
    unknown = []
    for rule in original.get(rulekey, []):
        if ai.target(rule).upper() != 'DIRECT':
            continue
        parts = [x.strip() for x in rule.split(',')]
        domestic = len(parts) > 2 and parts[0].upper() in ('GEOIP', 'GEOSITE') and parts[1].lower() == 'cn'
        local = False
        if len(parts) > 2 and parts[0].upper() == 'IP-CIDR':
            try:
                network = ipaddress.ip_network(parts[1], strict=False)
                local = any(network.subnet_of(ipaddress.ip_network(x)) for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', '169.254.0.0/16'))
            except ValueError:
                pass
        if not domestic and not local:
            unknown.append(rule)
    if review is None:
        return unknown, {}
    c.require(isinstance(review, dict) and review.get('schema') == 'claude-direct-review/1'
              and review.get('config_semantic_sha256') == c.sha(c.encode(original)), 'DIRECT_REVIEW_BASELINE_MISMATCH')
    entries = review.get('entries')
    c.require(isinstance(entries, list), 'DIRECT_REVIEW_INVALID')
    decisions = {}
    for entry in entries:
        c.require(isinstance(entry, dict) and entry.get('rule') in unknown and entry['rule'] not in decisions
                  and entry.get('decision') in ('keep', 'proxy'), 'DIRECT_REVIEW_INCOMPLETE')
        c.safe_review_text(entry.get('reason'))
        decisions[entry['rule']] = entry['decision']
    c.require(set(decisions) == set(unknown), 'DIRECT_REVIEW_INCOMPLETE')
    return unknown, decisions


def direct_template(c, config, fmt):
    fmt = c.config_format(config, fmt)
    original = c.parse_config(c.read_bytes(config), fmt)
    unknown, _ = direct_decisions(c, original, fmt)
    return {'schema': 'claude-direct-review/1', 'config_semantic_sha256': c.sha(c.encode(original)),
            'entries': [{'rule': rule, 'decision': 'pending', 'reason': ''} for rule in dict.fromkeys(unknown)]}


def build_semantics(c, original, fmt, node, group, direct_review=None):
    unknown, decisions = direct_decisions(c, original, fmt, direct_review)
    c.require(not unknown or bool(decisions), 'UNIFIED_DIRECT_REVIEW_REQUIRED')
    catalog = ai.catalog(c)
    base = normalize(c, original, fmt, node, group, catalog)
    result, at = ai.semantic_candidate(c, base, fmt, node, group, catalog)
    rulekey = 'rule' if fmt == 'shadowrocket' else 'rules'
    # Leading blocks were validated/preserved by ai_routing; map all other proxy actions.
    groupkey = 'proxy group' if fmt == 'shadowrocket' else 'proxy-groups'
    if fmt == 'shadowrocket':
        names = {line.split('=', 1)[0].strip() for line in result.get('proxy', []) + result.get(groupkey, [])}
        deny_members = {line.split('=', 1)[0].strip(): [x.strip() for x in line.split('=', 1)[1].split(',')[1:] if '=' not in x] for line in result.get(groupkey, [])}
        definitions = {line.split('=', 1)[0].strip(): line.split('=', 1)[1].strip() for line in result['proxy']}
        parts = definitions[node].split(',')
        c.require(len(parts) >= 2, 'UNIFIED_NODE_SERVER_REQUIRED')
        server = parts[1].strip()
    else:
        names = {p['name'] for p in result.get('proxies', []) + result.get(groupkey, [])}
        deny_members = {g['name']: g.get('proxies', []) for g in result.get(groupkey, [])}
        selected = next(p for p in result['proxies'] if p['name'] == node)
        server = selected.get('server')
    c.require(isinstance(server, str) and server, 'UNIFIED_NODE_SERVER_REQUIRED')
    try:
        address = ipaddress.ip_address(server.strip('[]'))
    except ValueError:
        address = None
    c.require(address is None or address.version == 4, 'UNIFIED_IPV6_NODE_REVIEW_REQUIRED')
    denied = ai.deny_targets(c, deny_members)
    rules = []
    for rule in result[rulekey]:
        action = ai.target(rule)
        if action.upper() == 'DIRECT' and decisions.get(rule) == 'proxy':
            rules.append(replace_target(rule, group))
        elif action.upper() in {'DIRECT'} | ai.REJECT_ACTIONS or action in denied:
            rules.append(rule)
        else:
            c.require(action in names and action.upper() not in c.BUILTINS, 'UNIFIED_RULE_ACTION_REVIEW_REQUIRED')
            rules.append(replace_target(rule, group))
    # IPv6 targets are rejected before ordinary/domain policies; DIRECT IPv4 rules stay intact.
    rules.insert(at, V6_RULE)
    result[rulekey] = rules
    if fmt == 'shadowrocket':
        lines = result.setdefault('general', [])
        lines = [x for x in lines if not re.match(r'^\s*ipv6\s*=', x, re.I)]
        lines.append('ipv6 = false')
        result['general'] = lines
    else:
        result['ipv6'] = False
        dns = result.setdefault('dns', {})
        c.require(isinstance(dns, dict), 'UNIFIED_DNS_OBJECT_REQUIRED')
        dns['ipv6'] = False
        def check_resolver(value):
            if isinstance(value, dict):
                for child in value.values(): check_resolver(child)
            elif isinstance(value, list):
                for child in value: check_resolver(child)
            elif isinstance(value, str):
                raw = value.split('#', 1)[0]
                host = urlsplit(raw).hostname if '://' in raw else raw.strip('[]')
                try:
                    address = ipaddress.ip_address(host)
                except ValueError:
                    return
                c.require(address.version == 4, 'UNIFIED_IPV6_DNS_REVIEW_REQUIRED')
            else:
                c.require(False, 'UNIFIED_DNS_VALUE_INVALID')
        for key in ('nameserver', 'fallback', 'default-nameserver', 'proxy-server-nameserver', 'nameserver-policy', 'direct-nameserver'):
            if key in dns: check_resolver(dns[key])

        selected['ip-version'] = 'ipv4'
    return result


def render_yaml(c, text, expected):
    """Replace only changed top-level subtrees; retain other source bytes and comments."""
    import yaml
    original = c.parse_config(text.encode(), 'yaml')
    tree = yaml.compose(text, Loader=yaml.SafeLoader)
    nodes = {key.value: (key, value) for key, value in tree.value}
    nl = '\r\n' if '\r\n' in text else '\n'
    edits = []
    for key, value in expected.items():
        if original.get(key) == value and key in original:
            continue
        if key in nodes:
            start, end = nodes[key][1].start_mark.index, nodes[key][1].end_mark.index
            # Source marks may include the final newline; retain a boundary before following key.
            suffix = nl if text[start:end].endswith(('\n', '\r')) else ''
            indent = '  ' if nodes[key][1].start_mark.column == 0 else ''
            edits.append((start, end, indent + json.dumps(value, ensure_ascii=False) + suffix))
        else:
            edits.append((len(text), len(text), ('' if text.endswith(('\n', '\r')) else nl) + key + ': ' + json.dumps(value, ensure_ascii=False) + nl))
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    c.require(c.parse_config(text.encode(), 'yaml') == expected, 'UNIFIED_RENDER_MISMATCH')
    return text


def render_shadow(c, text, expected):
    old = c.parse_config(text.encode(), 'shadowrocket')
    lines = text.splitlines(keepends=True)
    nl = '\r\n' if '\r\n' in text else '\n'
    sections = {}
    for i, line in enumerate(lines):
        match = re.fullmatch(r'\s*\[([^\]]+)\]\s*', line.strip())
        if match:
            sections[match.group(1).lower()] = i
    edits = []
    for name in ('general', 'proxy group', 'rule'):
        if old.get(name) == expected.get(name):
            continue
        values = expected.get(name, [])
        if name in sections:
            start = sections[name] + 1
            later = [i for i in sections.values() if i >= start]
            end = min(later) if later else len(lines)
            comments = [line for line in lines[start:end] if not line.strip() or line.lstrip().startswith(('#', ';', '//'))]
            edits.append((start, end, comments + [x + nl for x in values]))
        else:
            edits.append((len(lines), len(lines), [nl, '[' + name.title() + ']' + nl] + [x + nl for x in values]))
    if lines and not lines[-1].endswith(('\n', '\r')):
        lines[-1] += nl
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = replacement
    result = ''.join(lines)
    c.require(c.parse_config(result.encode(), 'shadowrocket') == expected, 'UNIFIED_RENDER_MISMATCH')
    return result


def audit(c, baseline, candidate, fmt, node, group=ai.GROUP, direct_review=None):
    original, actual = c.parse_config(baseline, fmt), c.parse_config(candidate, fmt)
    expected = build_semantics(c, original, fmt, node, group, direct_review)
    match = expected == actual
    return {'schema': 'claude-setup-ai-audit/1', 'policy': POLICY,
            'status': 'static_policy_matches' if match else 'unexpected_policy_or_other_changes',
            'unified_proxy_rules': match, 'direct_scope_reviewed': match,
            'core_ipv6_disabled_in_config': match, 'node_ipv4_only_declared': match and fmt != 'shadowrocket',
            'system_ipv6_verified': False, 'remote_exit_family_verified': False,
            'runtime_verified': False, 'application_loaded': 'not_verified'}


def prepare(c, current, fmt, node, output, group=ai.GROUP, direct_review=None):
    baseline = c.read_bytes(current)
    fmt = c.config_format(current, fmt)
    original = c.parse_config(baseline, fmt)
    expected = build_semantics(c, original, fmt, node, group, direct_review)
    if fmt == 'json':
        candidate = c.encode(expected)
    else:
        text = c.decode(baseline)
        result = render_shadow(c, text, expected) if fmt == 'shadowrocket' else render_yaml(c, text, expected)
        candidate = (b'\xef\xbb\xbf' if baseline.startswith(b'\xef\xbb\xbf') else b'') + result.encode()
    review = audit(c, baseline, candidate, fmt, node, group, direct_review)
    c.require(review['status'] == 'static_policy_matches', 'UNIFIED_AUDIT_FAILED')
    c.new_dir(output)
    folder = Path(output)
    candidate_path = folder / ('candidate.' + {'yaml': 'yaml', 'json': 'json', 'shadowrocket': 'conf'}[fmt])
    c.write_new(candidate_path, candidate)
    if candidate != baseline:
        c.prepare_plan(current, candidate_path, fmt, folder / 'plan')
        c.require(c.read_bytes(folder / 'plan/original.bin') == baseline, 'UNIFIED_BASELINE_CHANGED')
    c.write_new(folder / 'ai-audit.json', c.encode(review))
    return {'status': 'ai_candidate_prepared', 'policy': POLICY, 'format': fmt, 'content_changed': candidate != baseline,
            'unified_proxy_rules': True, 'ipv6_config_disabled': True, 'apply_supported': False,
            'changed_sections_comments_require_review': fmt != 'json', 'runtime_verified': False}
