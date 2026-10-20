"""Offline AI-only routing candidates. No downloads, application writes or core activation."""
import copy
import json
from pathlib import Path
import re

GROUP = 'AI-ONLY'
REJECT_ACTIONS = {'REJECT', 'REJECT-DROP', 'REJECT-NO-DROP'}
TRANSPORTS = {'http', 'socks5', 'ss', 'ssr', 'vmess', 'vless', 'trojan', 'hysteria',
              'hysteria2', 'tuic', 'wireguard', 'snell', 'anytls', 'ssh', 'shadowsocks',
              'shadowsocksr'}
FORBIDDEN_SUFFIXES = {'com', 'net', 'org', 'cloudflare.com', 'google.com', 'amazonaws.com',
                      'workos.com', 'stripe.com', 'sentry.io', 'github.com', 'datadoghq.com',
                      'intercom.io', 'intercomcdn.com', 'sendgrid.net'}


def catalog(c):
    data = c.load_json(c.read_bytes(Path(__file__).with_name('ai_domains.json'), 32768))
    c.require(isinstance(data, dict) and data.get('schema') == 'claude-setup-ai-domains/1', 'AI_CATALOG_INVALID')
    c.require(isinstance(data.get('revision'), str) and re.fullmatch(r'[0-9.-]{1,32}', data['revision']), 'AI_CATALOG_INVALID')
    seen = set()
    for key in ('suffixes', 'exact_hosts'):
        values = data.get(key)
        c.require(isinstance(values, list) and 0 < len(values) <= 100, 'AI_CATALOG_INVALID')
        for host in values:
            c.require(isinstance(host, str) and len(host) <= 253 and re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host)
                      and '.' in host and '..' not in host and host not in seen, 'AI_CATALOG_INVALID')
            c.require(all(label and len(label) <= 63 and not label.startswith('-') and not label.endswith('-') for label in host.split('.')), 'AI_CATALOG_INVALID')
            if key == 'suffixes':
                c.require(host not in FORBIDDEN_SUFFIXES, 'AI_SHARED_SUFFIX_FORBIDDEN')
            seen.add(host)
    return data


def label(c, value):
    c.require(isinstance(value, str) and 0 < len(value) <= 160 and value == value.strip()
              and not any(ord(x) < 32 or x in ',=[]()#;\"\'' for x in value), 'AI_LABEL_INVALID')
    c.require(value.upper() not in c.BUILTINS | {'PROXY', 'DNS', 'DIRECT', 'REJECT-NO-DROP'}, 'AI_PROXY_NODE_REQUIRED')
    return value


def guarded_rules(data, fmt, group):
    protocol = 'PROTOCOL,UDP' if fmt == 'shadowrocket' else 'NETWORK,udp'
    udp_reject = 'REJECT-NO-DROP' if fmt == 'shadowrocket' else 'REJECT'
    rules = []
    for key, kind in (('suffixes', 'DOMAIN-SUFFIX'), ('exact_hosts', 'DOMAIN')):
        for host in data[key]:
            match = kind + ',' + host
            rules += [f'AND,(({match}),({protocol})),{udp_reject}',
                      f'{match},{group}', f'{match},REJECT']
    return rules


def target(rule):
    parts = [part.strip() for part in rule.split(',')]
    return parts[-2] if parts[-1].lower() == 'no-resolve' and len(parts) > 1 else parts[-1]


def deny_targets(c, group_members):
    """Resolve explicit deny groups, rejecting mixed/recursive policies before insertion."""
    cache = {}
    def visit(name, seen):
        if name.upper() in REJECT_ACTIONS:
            return {True}
        if name not in group_members:
            return {False}
        c.require(name not in seen, 'AI_GROUP_CYCLE_REVIEW_REQUIRED')
        if name not in cache:
            result = set()
            for member in group_members[name]:
                result.update(visit(member, seen | {name}))
            c.require(len(result) <= 1, 'AI_MIXED_DENY_GROUP_REVIEW_REQUIRED')
            cache[name] = result or {False}
        return cache[name]
    return {name for name in group_members if visit(name, set()) == {True}}


def layout(c, obj, fmt, node, group, permit_group=False):
    """Require explicit, locally declared concrete node; no hidden selector/provider chain."""
    label(c, node); label(c, group)
    c.require(node != group, 'AI_GROUP_NODE_COLLISION')
    if fmt == 'shadowrocket':
        groups = []
        members = {}
        for entry in obj.get('proxy group', []):
            c.require('=' in entry, 'AI_GROUP_INVALID')
            name, value = entry.split('=', 1)
            name = name.strip()
            groups.append(name)
            members[name] = [x.strip() for x in value.split(',')[1:] if '=' not in x]
        definitions = {}
        for entry in obj.get('proxy', []):
            c.require('=' in entry, 'AI_NODE_DEFINITION_INVALID')
            name, value = entry.split('=', 1)
            name = name.strip()
            c.require(name not in definitions, 'AI_DUPLICATE_NODE')
            definitions[name] = value.strip()
        c.require(node in definitions and node not in groups, 'AI_CONCRETE_NODE_NOT_FOUND')
        value = definitions[node]
        c.require(value.split(',')[0].strip().lower() in TRANSPORTS, 'AI_NODE_TRANSPORT_REVIEW_REQUIRED')
        c.require(not re.search(r'(?i)(?:proxy-chain|underlying-proxy|dialer-proxy|detour|via)\s*=', value), 'AI_NODE_CHAIN_REVIEW_REQUIRED')
        c.require(not obj.get('script'), 'AI_SCRIPT_REVIEW_REQUIRED')
        c.require(not any(re.match(r'\s*include\s*=', s, re.I) for s in obj.get('general', [])), 'AI_INCLUDE_REVIEW_REQUIRED')
        rules = obj.get('rule')
    else:
        c.require(obj.get('mode', 'rule') == 'rule', 'AI_RULE_MODE_REQUIRED')
        c.require(not any(k in obj for k in ('prepend', 'append', 'delete')), 'AI_FULL_CONFIG_REQUIRED')
        c.require(not any(k in obj for k in ('script', 'scripts', 'sub-rules')), 'AI_SCRIPT_REVIEW_REQUIRED')
        proxies = obj.get('proxies', [])
        proxy_groups = obj.get('proxy-groups', [])
        c.require(isinstance(proxies, list) and isinstance(proxy_groups, list), 'AI_CONFIG_INVALID')
        c.require(all(isinstance(g, dict) and isinstance(g.get('name'), str) for g in proxy_groups), 'AI_GROUP_INVALID')
        groups = [g['name'] for g in proxy_groups]
        members = {}
        for g in proxy_groups:
            items = g.get('proxies', [])
            c.require(isinstance(items, list) and all(isinstance(x, str) for x in items), 'AI_GROUP_INVALID')
            members[g['name']] = items
            # Unknown external members can change a deny group into a mixed policy.
            if g.get('use') or g.get('include-all') or g.get('include-all-proxies') or g.get('include-all-providers'):
                members[g['name']] = items + ['__external_unknown__']
        definitions = {}
        for entry in proxies:
            c.require(isinstance(entry, dict) and isinstance(entry.get('name'), str), 'AI_NODE_DEFINITION_INVALID')
            name = entry['name']
            c.require(name not in definitions, 'AI_DUPLICATE_NODE')
            definitions[name] = entry
        c.require(node in definitions and node not in groups, 'AI_CONCRETE_NODE_NOT_FOUND')
        value = definitions[node]
        c.require(value.get('type') in TRANSPORTS, 'AI_NODE_TRANSPORT_REVIEW_REQUIRED')
        c.require(not any(k in value for k in ('dialer-proxy', 'detour', 'proxy-chain')), 'AI_NODE_CHAIN_REVIEW_REQUIRED')
        rules = obj.get('rules')
    c.require(len(groups) == len(set(groups)), 'AI_DUPLICATE_GROUP')
    blocked = deny_targets(c, members)
    def rejects(rule):
        action = target(rule)
        return action.upper() in REJECT_ACTIONS or action in blocked
    if not permit_group:
        c.require(group not in groups and group not in definitions, 'AI_GROUP_ALREADY_EXISTS')
    c.require(isinstance(rules, list) and rules and all(isinstance(r, str) for r in rules), 'AI_EXISTING_RULES_REQUIRED')
    # Preserve leading blocks; never silently lift a later organizational deny above/below a new allow.
    leading = 0
    while leading < len(rules) and rejects(rules[leading]):
        leading += 1
    if not permit_group:
        c.require(not any(rejects(r) for r in rules[leading:]), 'AI_LATER_REJECT_REVIEW_REQUIRED')
    final = rules[-1].split(',')
    c.require(len(final) == 2 and final[0].strip().upper() in ('MATCH', 'FINAL'), 'AI_BASE_FALLBACK_REVIEW_REQUIRED')
    c.require(final[1].strip().upper() not in c.BUILTINS | {'PROXY', 'REJECT-NO-DROP'}, 'AI_BASE_PROXY_FALLBACK_REQUIRED')
    c.require(final[1].strip() in set(groups) | set(definitions), 'AI_BASE_FALLBACK_UNRESOLVED')
    c.require(final[1].strip() not in blocked, 'AI_BASE_PROXY_FALLBACK_REQUIRED')
    # Preserve existing domestic/private rules; their domain-set contents need separate local verification.
    c.require(any(r.split(',')[-1].strip().upper() == 'DIRECT' or
                  (r.split(',')[-1].strip().lower() == 'no-resolve' and len(r.split(',')) > 1 and r.split(',')[-2].strip().upper() == 'DIRECT')
                  for r in rules[:-1]), 'AI_BASE_DIRECT_RULES_REQUIRED')
    return rules, leading


def expected_group(node, group):
    return {'name': group, 'type': 'select', 'proxies': [node], 'disable-udp': True}


def semantic_candidate(c, original, fmt, node, group, data):
    rules, at = layout(c, original, fmt, node, group)
    result = copy.deepcopy(original)
    additions = guarded_rules(data, fmt, group)
    if fmt == 'shadowrocket':
        result.setdefault('proxy group', []).append(f'{group} = select, {node}')
        result['rule'] = rules[:at] + additions + rules[at:]
    else:
        result.setdefault('proxy-groups', []).append(expected_group(node, group))
        result['rules'] = rules[:at] + additions + rules[at:]
    return result, at


def yaml_candidate(c, text, original, expected, at, additions, node, group):
    import yaml
    tree = yaml.compose(text, Loader=yaml.SafeLoader)
    nodes = {k.value: v for k, v in tree.value}
    nl = '\r\n' if '\r\n' in text else '\n'
    edits = []
    def insert_sequence(name, index, flow_value, block_lines):
        seq = nodes[name]
        c.require(isinstance(seq, yaml.SequenceNode), 'AI_YAML_SEQUENCE_REQUIRED')
        if seq.flow_style:
            # Only empty flow group lists are supported; nonempty inline layouts need manual review.
            c.require(name == 'proxy-groups' and not seq.value, 'AI_YAML_FLOW_REVIEW_REQUIRED')
            edits.append((seq.start_mark.index, seq.end_mark.index, json.dumps(flow_value, ensure_ascii=False)))
            return
        if index < len(seq.value):
            line = seq.value[index].start_mark.line
            # Mapping start_mark begins after "- "; use the real sequence-item line's leading spaces.
            lines = text.splitlines(keepends=True)
            line_start = sum(len(s) for s in lines[:line])
            line_text = lines[line]
            match = re.match(r'( *)-', line_text)
            c.require(match is not None, 'AI_YAML_LAYOUT_REVIEW_REQUIRED')
            indent = match.group(1)
            block = ''.join(indent + s + nl for s in block_lines)
            edits.append((line_start, line_start, block))
        else:
            # Appending a group at the end of the sequence, before the next root key.
            pos = seq.end_mark.index
            prefix = '' if pos == 0 or text[pos - 1] in '\r\n' else nl
            indent = ' ' * seq.start_mark.column
            edits.append((pos, pos, prefix + ''.join(indent + s + nl for s in block_lines)))
    insert_sequence('rules', at, [], ['- ' + json.dumps(rule, ensure_ascii=False) for rule in additions])
    g = expected_group(node, group)
    block = ['- name: ' + json.dumps(group, ensure_ascii=False), '  type: select',
             '  proxies:', '    - ' + json.dumps(node, ensure_ascii=False), '  disable-udp: true']
    if 'proxy-groups' in nodes:
        insert_sequence('proxy-groups', len(original['proxy-groups']), [g], block)
    else:
        edits.append((len(text), len(text), ('' if text.endswith(('\n', '\r')) else nl) + 'proxy-groups:' + nl + ''.join('  ' + s + nl for s in block)))
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    c.require(c.parse_config(text.encode('utf-8'), 'yaml') == expected, 'AI_CANDIDATE_SEMANTIC_MISMATCH')
    return text


def shadow_candidate(c, text, expected, at, additions, node, group):
    lines = text.splitlines(keepends=True)
    nl = '\r\n' if '\r\n' in text else '\n'
    sections = {}
    section = None
    for i, line in enumerate(lines):
        match = re.fullmatch(r'\s*\[([^\]]+)\]\s*', line.strip())
        if match:
            section = match.group(1).lower()
            sections[section] = {'start': i, 'items': []}
        elif section and line.strip() and not line.lstrip().startswith(('#', ';', '//')):
            sections[section]['items'].append(i)
    c.require('rule' in sections, 'AI_RULE_SECTION_REQUIRED')
    insert_line = sections['rule']['items'][at]
    edits = [(insert_line, [rule + nl for rule in additions])]
    if 'proxy group' in sections:
        start = sections['proxy group']['start']
        ends = [x['start'] for x in sections.values() if x['start'] > start]
        end = min(ends) if ends else len(lines)
        edits.append((end, [f'{group} = select, {node}' + nl]))
    else:
        edits.append((len(lines), [nl, '[Proxy Group]' + nl, f'{group} = select, {node}' + nl]))
    if lines and not lines[-1].endswith(('\n', '\r')):
        lines[-1] += nl
    for index, new_lines in sorted(edits, key=lambda e: e[0], reverse=True):
        lines[index:index] = new_lines
    result = ''.join(lines)
    c.require(c.parse_config(result.encode('utf-8'), 'shadowrocket') == expected, 'AI_CANDIDATE_SEMANTIC_MISMATCH')
    return result


def audit(c, baseline, candidate, fmt, node, group=GROUP):
    data = catalog(c)
    original = c.parse_config(baseline, fmt)
    actual = c.parse_config(candidate, fmt)
    expected, at = semantic_candidate(c, original, fmt, node, group, data)
    # Exact semantic comparison disallows changed DNS, global toggles, original nodes, rules or groups.
    matches = expected == actual
    return {'schema': 'claude-setup-ai-audit/1', 'status': 'static_policy_matches' if matches else 'unexpected_policy_or_other_changes',
            'catalog_revision': data['revision'], 'domain_count': len(data['suffixes']) + len(data['exact_hosts']),
            'one_designated_node': matches, 'ai_udp_rejected': matches,
            'ai_direct_fallback_absent_in_candidate_rules': matches,
            'original_other_config_semantics_preserved': matches,
            'leading_block_rules_preserved': matches, 'runtime_verified': False,
            'dns_path_verified': False, 'tunnel_exit_protection_verified': False,
            'external_rule_contents_verified': False, 'application_loaded': 'not_verified'}


def prepare(c, current, fmt, node, output, group=GROUP):
    baseline = c.read_bytes(current)
    fmt = c.config_format(current, fmt)
    data = catalog(c)
    original = c.parse_config(baseline, fmt)
    # Run existing structural checks as well; failures stay fixed-code and do not print private fields.
    c.config_summary(baseline, fmt)
    expected, at = semantic_candidate(c, original, fmt, node, group, data)
    additions = guarded_rules(data, fmt, group)
    if fmt == 'json':
        candidate = c.encode(expected)
        filename = 'candidate.json'
    else:
        text = c.decode(baseline)
        rendered = shadow_candidate(c, text, expected, at, additions, node, group) if fmt == 'shadowrocket' else yaml_candidate(c, text, original, expected, at, additions, node, group)
        candidate = (b'\xef\xbb\xbf' if baseline.startswith(b'\xef\xbb\xbf') else b'') + rendered.encode('utf-8')
        filename = 'candidate.conf' if fmt == 'shadowrocket' else 'candidate.yaml'
    result = audit(c, baseline, candidate, fmt, node, group)
    c.require(result['status'] == 'static_policy_matches', 'AI_CANDIDATE_AUDIT_FAILED')
    c.config_summary(candidate, fmt)
    c.new_dir(output)
    out = Path(output)
    c.write_new(out / filename, candidate)
    try:
        c.prepare_plan(current, out / filename, fmt, out / 'plan')
        c.require(c.read_bytes(out / 'plan' / 'original.bin') == baseline, 'AI_BASELINE_CHANGED')
    except c.SetupError:
        # Preserve the candidate for inspection, but report an incomplete build explicitly.
        raise c.SetupError('AI_PLAN_INCOMPLETE_REVIEW_OUTPUT') from None
    c.write_new(out / 'ai-audit.json', c.encode(result))
    return {'status': 'ai_candidate_prepared', 'format': fmt, 'catalog_revision': data['revision'],
            'domain_count': result['domain_count'], 'added_rule_count': len(additions),
            'private_candidate_contains_configuration': True, 'apply_supported': False,
            'other_config_semantics_preserved': True, 'runtime_verified': False}
