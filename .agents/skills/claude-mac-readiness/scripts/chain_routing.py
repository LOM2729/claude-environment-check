"""Offline validation of local Mihomo dialer-proxy dependencies.

This module neither resolves provider contents nor chooses a selector member.
The returned names are private configuration metadata, never runtime evidence.
"""
import ai_routing as ai


GROUP_TYPES = frozenset(('select', 'url-test', 'fallback', 'load-balance'))
TERMINALS = frozenset(('DIRECT', 'REJECT', 'REJECT-DROP', 'REJECT-NO-DROP', 'PASS', 'COMPATIBLE'))
DYNAMIC_KEYS = ('use', 'include-all', 'include-all-proxies', 'include-all-providers')


def graph(c, obj):
    """Validate every local node/group edge without reading external resources."""
    c.require(isinstance(obj, dict), 'CHAIN_CONFIG_INVALID')
    proxies, groups = obj.get('proxies', []), obj.get('proxy-groups', [])
    c.require(isinstance(proxies, list) and isinstance(groups, list), 'CHAIN_CONFIG_INVALID')
    c.require(len(proxies) + len(groups) <= 5000, 'CHAIN_GRAPH_TOO_COMPLEX')
    definitions, folded, kinds, edges, dynamic = {}, set(), {}, {}, set()
    for entries, category in ((proxies, 'node'), (groups, 'selector')):
        for entry in entries:
            c.require(isinstance(entry, dict), 'CHAIN_DEFINITION_INVALID')
            name = ai.label(c, entry.get('name'))
            c.require(name.casefold() not in folded, 'CHAIN_LABEL_COLLISION')
            folded.add(name.casefold())
            definitions[name], kinds[name], edges[name] = entry, category, []
            c.require(not any(k in entry for k in ('detour', 'proxy-chain', 'underlying-proxy')),
                      'CHAIN_SYNTAX_UNSUPPORTED')
            if category == 'node':
                c.require(isinstance(entry.get('type'), str) and entry['type'] in ai.TRANSPORTS,
                          'CHAIN_TRANSPORT_UNSUPPORTED')
                if 'dialer-proxy' in entry:
                    ref = entry['dialer-proxy']
                    c.require(isinstance(ref, str) and bool(ref), 'CHAIN_REFERENCE_INVALID')
                    edges[name] = [ref]
            else:
                c.require(entry.get('type') != 'relay', 'CHAIN_RELAY_UNSUPPORTED')
                c.require(isinstance(entry.get('type'), str) and entry['type'] in GROUP_TYPES,
                          'CHAIN_SELECTOR_UNSUPPORTED')
                c.require('dialer-proxy' not in entry, 'CHAIN_SYNTAX_UNSUPPORTED')
                refs, uses = entry.get('proxies', []), entry.get('use', [])
                c.require(isinstance(refs, list) and all(isinstance(r, str) and r for r in refs)
                          and isinstance(uses, list) and all(isinstance(r, str) and r for r in uses),
                          'CHAIN_REFERENCE_INVALID')
                c.require(len(refs) == len(set(refs)), 'CHAIN_DUPLICATE_MEMBER')
                edges[name] = list(refs)
                if any(entry.get(k) for k in DYNAMIC_KEYS):
                    dynamic.add(name)
                c.require(refs or name in dynamic, 'CHAIN_EMPTY_SELECTOR')
    providers = obj.get('proxy-providers', {})
    c.require(isinstance(providers, dict), 'CHAIN_PROVIDERS_INVALID')
    for name, entry in definitions.items():
        for ref in edges[name]:
            c.require(ref in definitions or ref in TERMINALS, 'CHAIN_REFERENCE_MISSING')
        if kinds[name] == 'selector':
            c.require(all(ref in providers for ref in entry.get('use', [])), 'CHAIN_PROVIDER_MISSING')
    # Iterative DFS bounds complexity and detects cycles spanning nodes and groups.
    state, postorder = {}, []
    for root in definitions:
        if state.get(root) == 2:
            continue
        stack = [(root, False)]
        while stack:
            name, done = stack.pop()
            if done:
                state[name] = 2
                postorder.append(name)
                continue
            c.require(state.get(name) != 1, 'CHAIN_DEPENDENCY_CYCLE')
            if state.get(name) == 2:
                continue
            c.require(len(stack) < 10000, 'CHAIN_GRAPH_TOO_COMPLEX')
            state[name] = 1
            stack.append((name, True))
            stack.extend((ref, False) for ref in reversed(edges[name]) if ref in definitions)
    unresolved = set(dynamic)
    for name in postorder:
        if any(ref in unresolved for ref in edges[name]):
            unresolved.add(name)
    return {'definitions': definitions, 'kinds': kinds, 'edges': edges,
            'unresolved': unresolved, 'dynamic': dynamic}


def validate(c, obj, node):
    """Accept a concrete selected node only when its full chain is locally known.

    A provider-backed selector elsewhere is retained. A selected chain depending
    on provider contents cannot be established offline and is refused.
    """
    data = graph(c, obj)
    c.require(node in data['definitions'] and data['kinds'][node] == 'node',
              'AI_CONCRETE_NODE_NOT_FOUND')
    c.require(node not in data['unresolved'], 'CHAIN_EXTERNAL_DEPENDENCY_UNRESOLVED')
    seen, pending = set(), [node]
    while pending:
        ref = pending.pop()
        if ref in seen or ref not in data['definitions']:
            continue
        seen.add(ref)
        if data['kinds'][ref] == 'node':
            entry = data['definitions'][ref]
            server, port = entry.get('server'), entry.get('port')
            c.require(isinstance(server, str) and bool(server) and port is not None,
                      'CHAIN_NODE_ENDPOINT_INCOMPLETE')
            c.require(not any(ch.isspace() or ord(ch) < 32 or ch in '/\\@?#' for ch in server)
                      and '://' not in server and type(port) is int and 1 <= port <= 65535,
                      'CHAIN_NODE_ENDPOINT_INVALID')
        pending.extend(reversed(data['edges'][ref]))
    return {'node': node, 'dependencies': [name for name in data['definitions'] if name in seen],
            'edges': {name: list(data['edges'][name]) for name in data['definitions'] if name in seen},
            'has_chain': bool(data['edges'][node]), 'runtime_verified': False}
