"""A visible Claude selector bound to the same concrete node as unified traffic."""
import copy

import ai_routing as ai

SUFFIXES = frozenset(('claude.ai', 'claude.com', 'anthropic.com',
                      'claudeusercontent.com', 'claudemcpcontent.com'))


def name(group):
    return group + '-Claude'


def labels(c, node, group):
    for value in (node, group, name(group)):
        ai.label(c, value)
    c.require(node not in (group, name(group)), 'CLAUDE_GROUP_NODE_COLLISION')


def guarded_rules(catalog, fmt, group):
    rules = ai.guarded_rules(catalog, fmt, group)
    for index, rule in enumerate(rules):
        parts = rule.split(',')
        if len(parts) == 3 and parts[0] == 'DOMAIN-SUFFIX' and parts[1] in SUFFIXES and parts[2] == group:
            rules[index] = ','.join(parts[:2] + [name(group)])
    return rules


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
    guarded = guarded_rules(catalog, fmt, group)
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


def add(c, result, fmt, node, group, catalog):
    """Convert first-party Claude actions only; preserve all UDP and reject guards."""
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
