"""A visible Claude selector with legacy-safe community protection upgrades."""
import copy
import re

import ai_routing as ai
import community_routing as community

SUFFIXES = frozenset(('claude.ai', 'claude.com', 'anthropic.com',
                      'claudeusercontent.com', 'claudemcpcontent.com'))


def name(group):
    return group + '-Claude'


def labels(c, node, group):
    for value in (node, group, name(group)):
        ai.label(c, value)
    c.require(node not in (group, name(group)), 'CLAUDE_GROUP_NODE_COLLISION')


def legacy_guarded_rules(catalog, fmt, group):
    rules = ai.guarded_rules(catalog, fmt, group)
    for index, rule in enumerate(rules):
        parts = rule.split(',')
        if len(parts) == 3 and parts[0] == 'DOMAIN-SUFFIX' and parts[1] in SUFFIXES and parts[2] == group:
            rules[index] = ','.join(parts[:2] + [name(group)])
    return rules


def guarded_rules(catalog, fmt, group):
    return community.guarded_rules(fmt, name(group)) + legacy_guarded_rules(catalog, fmt, group)


def normalize(c, original, fmt, node, group, catalog):
    """Accept only our complete two-selector block before the legacy normalizer."""
    labels(c, node, group)
    base = copy.deepcopy(original)
    shadow = fmt == 'shadowrocket'
    rulekey = 'rule' if shadow else 'rules'
    groupkey = 'proxy group' if shadow else 'proxy-groups'
    derived = name(group)
    if shadow:
        c.require(all(isinstance(base.get(k, []), list)
                      and all(isinstance(x, str) and '=' in x for x in base.get(k, []))
                      for k in ('proxy', groupkey)), 'AI_GROUP_INVALID')
        definitions = [x.split('=', 1)[0].strip() for x in base.get('proxy', [])]
        groups = base.get(groupkey, [])
        existing = [x for x in groups if x.split('=', 1)[0].strip() == derived]
    else:
        c.require(all(isinstance(base.get(k, []), list)
                      and all(isinstance(x, dict) for x in base.get(k, []))
                      for k in ('proxies', groupkey)), 'AI_GROUP_INVALID')
        definitions = [x.get('name') for x in base.get('proxies', [])]
        groups = base.get(groupkey, [])
        existing = [x for x in groups if x.get('name') == derived]
    c.require(derived not in definitions, 'CLAUDE_GROUP_NAME_COLLISION')
    rules = base.get(rulekey, [])
    references = [r for r in rules if ai.target(r) == derived]
    if not existing:
        c.require(not references, 'CLAUDE_GROUP_MANAGED_BLOCK_CHANGED')
        return base
    variants = (guarded_rules(catalog, fmt, group), legacy_guarded_rules(catalog, fmt, group))
    guarded = next((block for block in variants if rules[:len(block)] == block), variants[0])
    c.require(len(existing) == 1 and rules[:len(guarded)] == guarded
              and references == [r for r in guarded if ai.target(r) == derived]
              and sum(rules[i:i + len(guarded)] == guarded for i in range(len(rules))) == 1,
              'CLAUDE_GROUP_MANAGED_BLOCK_CHANGED')
    if shadow:
        entries = [x for x in groups if x.split('=', 1)[0].strip() == group]
        fields = [x.strip() for x in existing[0].split('=', 1)[1].split(',')]
        c.require(len(fields) == 2 and fields[0].lower() == 'select', 'CLAUDE_GROUP_BINDING_CHANGED')
        prior = fields[1]
        base_fields = [x.strip() for x in entries[0].split('=', 1)[1].split(',')] if len(entries) == 1 else []
        c.require(len(base_fields) == 2 and base_fields[0].lower() == 'select'
                  and base_fields[1] == prior, 'CLAUDE_GROUP_BINDING_CHANGED')
        for entry in groups:
            if entry != existing[0]:
                members = [x.strip() for x in entry.split('=', 1)[1].split(',')[1:]]
                c.require(derived not in members, 'CLAUDE_GROUP_EXTERNAL_REFERENCE')
    else:
        entries = [x for x in groups if x.get('name') == group]
        members = existing[0].get('proxies', [])
        c.require(isinstance(members, list) and len(members) == 1, 'CLAUDE_GROUP_BINDING_CHANGED')
        prior = members[0]
        c.require(existing[0] == ai.expected_group(prior, derived)
                  and entries == [ai.expected_group(prior, group)], 'CLAUDE_GROUP_BINDING_CHANGED')
        c.require(all(derived not in x.get('proxies', []) for x in groups if x != existing[0]),
                  'CLAUDE_GROUP_EXTERNAL_REFERENCE')
    ai.label(c, prior)
    ai.layout(c, base, fmt, prior, group, permit_group=True)
    base[groupkey].remove(existing[0])
    base[rulekey] = ai.guarded_rules(catalog, fmt, group) + rules[len(guarded):]
    return base


def reconcile(c, original, fmt, node, group, catalog, action_aliases=None):
    """Opt-in offline preparation of a reviewed, noncanonical two-selector source.

    Return ``(prepared, report)``; a conflict returns ``(None, report)``. This is
    deliberately separate from normalize: ordinary callers still reject partial
    or changed managed blocks. The prepared object is an intermediate source,
    NOT an importable candidate. Feed it to the domestic policy builder with a
    fresh DIRECT review, then verify that builder's complete canonical guards.

    Only exact single-node selectors bound to *node* may be removed. Their rule
    actions are rebound to that same node without changing predicate/order.
    Exact bundled UDP guards are replaced by the subsequent canonical build;
    the exact single-PROTOCOL unconditional Shadowrocket UDP reject is likewise
    replaced by the domestic builder's explicit global UDP policy.
    fallback rejects are removed only if an earlier identical predicate already
    routes to that node, making the reject unreachable. Other rejects/rules are
    retained; unsupported ordering and hidden dependencies fail closed. Explicit
    action_aliases may repair case-only references to a unique existing selector.
    The sole built-in alias allowed is PROXY -> node, with validated app-local
    binding supplied on the context; it records migration intent, not a claim
    that the old client's unresolved action actually used that node.
    Reports intentionally contain codes, hashes and indexes, never private text.
    """
    report = {'schema': 'claude-group-reconciliation/1',
              'status': 'reconciliation_conflict', 'conflicts': [],
              'removed_group_indices': [], 'rebound_rule_indices': [],
              'aliased_rule_indices': [],
              'replaced_udp_rule_indices': [], 'unreachable_reject_indices': [],
              'replaced_global_udp_rule_indices': [],
              'runtime_verified': False, 'writes_performed': False}

    class Conflict(Exception):
        pass

    def require(condition, code, index=None):
        if not condition:
            entry = {'code': code}
            if index is not None:
                entry['rule_index'] = index
            report['conflicts'].append(entry)
            raise Conflict

    def predicate(rule):
        fields = rule.split(',')
        index = -2 if fields[-1].strip().lower() == 'no-resolve' else -1
        fields[index] = '__action__'
        return tuple(fields)

    def rebind(rule, action=node):
        fields = rule.split(',')
        index = -2 if fields[-1].strip().lower() == 'no-resolve' else -1
        fields[index] = action
        return ','.join(fields)

    try:
        require(fmt in ('json', 'yaml', 'shadowrocket'), 'CLAUDE_RECONCILE_FORMAT_INVALID')
        labels(c, node, group)
        require(isinstance(original, dict), 'CLAUDE_RECONCILE_CONFIG_INVALID')
        report['source_semantic_sha256'] = c.sha(c.encode(original))
        base = copy.deepcopy(original)
        shadow = fmt == 'shadowrocket'
        rulekey = 'rule' if shadow else 'rules'
        groupkey = 'proxy group' if shadow else 'proxy-groups'
        nodekey = 'proxy' if shadow else 'proxies'
        groups, definitions = base.get(groupkey, []), base.get(nodekey, [])
        require(isinstance(groups, list) and isinstance(definitions, list), 'AI_GROUP_INVALID')
        if shadow:
            require(all(isinstance(x, str) and '=' in x for x in groups + definitions), 'AI_GROUP_INVALID')
            group_names = [x.split('=', 1)[0].strip() for x in groups]
            node_names = [x.split('=', 1)[0].strip() for x in definitions]
            members = {label: [x.strip() for x in entry.split('=', 1)[1].split(',')[1:]]
                       for label, entry in zip(group_names, groups)}
            require(not any('=' in member for values in members.values() for member in values),
                    'CLAUDE_RECONCILE_EXTERNAL_GROUP_REVIEW_REQUIRED')
            general = base.get('general', [])
            require(isinstance(general, list) and all(isinstance(x, str) for x in general),
                    'CLAUDE_RECONCILE_CONFIG_INVALID')
            require(not base.get('script'), 'AI_SCRIPT_REVIEW_REQUIRED')
            require(not any(re.match(r'\s*include\s*=', x, re.I)
                            for x in general), 'AI_INCLUDE_REVIEW_REQUIRED')
        else:
            require(all(isinstance(x, dict) and isinstance(x.get('name'), str)
                        for x in groups + definitions), 'AI_GROUP_INVALID')
            group_names = [x['name'] for x in groups]
            node_names = [x['name'] for x in definitions]
            require(all(isinstance(x.get('proxies', []), list)
                        and all(isinstance(p, str) for p in x.get('proxies', [])) for x in groups),
                    'AI_GROUP_INVALID')
            members = {x['name']: x.get('proxies', []) for x in groups}
            require(not any(x.get(k) for x in groups for k in
                            ('use', 'include-all', 'include-all-proxies', 'include-all-providers')),
                    'CLAUDE_RECONCILE_EXTERNAL_GROUP_REVIEW_REQUIRED')
            require(not any(k in base for k in ('script', 'scripts', 'sub-rules')), 'AI_SCRIPT_REVIEW_REQUIRED')
        require(len(set(group_names)) == len(group_names), 'AI_DUPLICATE_GROUP')
        require(len(set(node_names)) == len(node_names), 'AI_DUPLICATE_NODE')
        require(not set(group_names).intersection(node_names), 'CLAUDE_RECONCILE_NAME_COLLISION')
        all_names = group_names + node_names
        case_names = all_names + ([node] if node not in node_names else [])
        require(len({x.casefold() for x in case_names}) == len(case_names),
                'CLAUDE_RECONCILE_CASE_COLLISION')
        # Never flatten a chain or reinterpret an unrelated selector's selection.
        require(not any(member in group_names for values in members.values() for member in values),
                'CLAUDE_RECONCILE_NESTED_GROUP_REVIEW_REQUIRED')
        require(all(member in node_names or member == node or member.upper() in {'DIRECT'} | ai.REJECT_ACTIONS
                    for values in members.values() for member in values),
                'CLAUDE_RECONCILE_UNRESOLVED_GROUP_MEMBER')
        managed = {group, name(group)}
        require(managed.issubset(group_names), 'CLAUDE_RECONCILE_TWO_SELECTORS_REQUIRED')
        for label in (group, name(group)):
            entry = groups[group_names.index(label)]
            if shadow:
                fields = [x.strip() for x in entry.split('=', 1)[1].split(',')]
                exact = len(fields) == 2 and fields[0].lower() == 'select' and fields[1] == node
            else:
                exact = entry == ai.expected_group(node, label)
            require(exact, 'CLAUDE_RECONCILE_BINDING_REVIEW_REQUIRED')
        rules = base.get(rulekey)
        require(isinstance(rules, list) and rules and all(isinstance(r, str) and r for r in rules),
                'AI_EXISTING_RULES_REQUIRED')
        aliases = {} if action_aliases is None else action_aliases
        require(isinstance(aliases, dict) and all(isinstance(a, str) and isinstance(b, str)
                                                for a, b in aliases.items()),
                'CLAUDE_RECONCILE_ALIAS_INVALID')
        for alias, destination in aliases.items():
            if alias == 'PROXY':
                binding = getattr(c, 'app_node_binding', None)
                require(shadow and destination == node and isinstance(binding, dict)
                        and binding.get('schema') == 'shadowrocket-app-node/1'
                        and binding.get('name') == node,
                        'CLAUDE_RECONCILE_APP_BINDING_REQUIRED')
                require(ai.app_node(c, node) is not None, 'CLAUDE_RECONCILE_APP_BINDING_REQUIRED')
            else:
                require(alias not in all_names and destination in group_names
                        and alias != destination and alias.casefold() == destination.casefold(),
                        'CLAUDE_RECONCILE_ALIAS_INVALID')
        normalized = []
        for index, rule in enumerate(rules):
            action = ai.target(rule)
            if action in aliases:
                normalized.append(rebind(rule, aliases[action]))
                report['aliased_rule_indices'].append(index)
            else:
                normalized.append(rule)
        rules = normalized
        base[rulekey] = rules
        # layout validates a declared concrete node (or explicit app-local node
        # metadata on the context), scripts/includes, cycles and fallback shape.
        ai.layout(c, base, fmt, node, group, permit_group=True)
        known = set(node_names) | set(group_names) | {node}
        for index, rule in enumerate(rules):
            action = ai.target(rule)
            require(action in known or action.upper() in {'DIRECT'} | ai.REJECT_ACTIONS,
                    'CLAUDE_RECONCILE_UNRESOLVED_ACTION', index)
            require(rule.split(',', 1)[0].strip().upper() not in ('SCRIPT', 'SUB-RULE', 'INCLUDE'),
                    'AI_SCRIPT_REVIEW_REQUIRED', index)
            require(index == len(rules) - 1 or rule.split(',', 1)[0].strip().upper() not in ('MATCH', 'FINAL'),
                    'CLAUDE_RECONCILE_RULES_AFTER_FALLBACK', index)
        guards = guarded_rules(catalog, fmt, group)
        udp_guards = set(guards[::3])
        fallback_guards = set(guards[2::3])
        earlier_node_routes = set()
        prepared_rules = []
        for index, rule in enumerate(rules):
            action = ai.target(rule)
            key = predicate(rule)
            if rule in udp_guards:
                report['replaced_udp_rule_indices'].append(index)
                continue
            if shadow and re.sub(r'\s+', '', rule).upper() == 'AND,((PROTOCOL,UDP)),REJECT':
                report['replaced_global_udp_rule_indices'].append(index)
                continue
            if rule in fallback_guards:
                require(key in earlier_node_routes, 'CLAUDE_RECONCILE_REACHABLE_DENY', index)
                report['unreachable_reject_indices'].append(index)
                continue
            if action in managed:
                prepared_rules.append(rebind(rule))
                report['rebound_rule_indices'].append(index)
            else:
                prepared_rules.append(rule)
            if action in managed | {node}:
                earlier_node_routes.add(key)
        report['removed_group_indices'] = [i for i, label in enumerate(group_names) if label in managed]
        base[groupkey] = [entry for label, entry in zip(group_names, groups) if label not in managed]
        base[rulekey] = prepared_rules
        # This strict check refuses arbitrary later denies instead of silently
        # moving them ahead of earlier customer allows or dropping them.
        _, leading = ai.layout(c, base, fmt, node, group)
        # Domestic builders put the new guards ahead of preserved leading denies.
        # Only provably disjoint, simple domain denies can safely remain there.
        protected = catalog['suffixes'] + catalog['exact_hosts']
        for index, rule in enumerate(prepared_rules[:leading]):
            parts = rule.split(',')
            disjoint = (len(parts) == 3 and parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX')
                        and not any(h == parts[1] or h.endswith('.' + parts[1])
                                    or parts[1].endswith('.' + h) for h in protected)
                        and not community.deny_overlap(parts[0], parts[1]))
            require(disjoint, 'DOMESTIC_EXISTING_DENY_REVIEW_REQUIRED', index)
        report.update(status='prepared_requires_policy_build',
                      prepared_semantic_sha256=c.sha(c.encode(base)),
                      canonical_guard_rule_count=len(guards),
                      canonical_regeneration_required=True,
                      global_udp_regeneration_required=bool(report['replaced_global_udp_rule_indices']),
                      direct_review_rebind_required=True,
                      preserved_rule_order=True)
        return base, report
    except Conflict:
        return None, report
    except c.SetupError as error:
        code = str(error)
        report['conflicts'].append({'code': code if re.fullmatch(r'[A-Z0-9_]+', code)
                                    else 'CLAUDE_RECONCILE_VALIDATION_FAILED'})
        return None, report


def add(c, result, fmt, node, group, catalog):
    """Add community scope and Claude actions; preserve UDP and reject guards."""
    labels(c, node, group)
    rulekey = 'rule' if fmt == 'shadowrocket' else 'rules'
    old = ai.guarded_rules(catalog, fmt, group)
    c.require(result[rulekey][:len(old)] == old, 'CLAUDE_GROUP_GUARD_POSITION_INVALID')
    result[rulekey][:len(old)] = guarded_rules(catalog, fmt, group)
    if fmt == 'shadowrocket':
        result['proxy group'].append(f'{name(group)} = select, {node}')
    else:
        result['proxy-groups'].append(ai.expected_group(node, name(group)))
    return result
