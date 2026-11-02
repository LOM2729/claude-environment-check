"""Optional, read-only Mihomo selection probe for an explicitly chosen source.

Only a source's literal loopback controller is contacted. Source credentials are
sent to that origin, never returned, logged, or obtained from controller replies.
The probe makes at most two GET requests and never follows redirects.
"""
from __future__ import annotations

from contextlib import closing
import http.client
import ipaddress
import json
import re
import urllib.error
import urllib.request

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TIMEOUT = 2
MAX_HOPS = 64
MAX_PROXIES = 5000
BUILTINS = frozenset({'DIRECT', 'REJECT', 'REJECT-DROP', 'REJECT-NO-DROP', 'PASS', 'COMPATIBLE'})
SELECTOR_TYPES = frozenset({'selector', 'select', 'url-test', 'urltest', 'fallback',
                            'load-balance', 'loadbalance', 'relay'})


class _Invalid(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Invalid()


def _controller(value):
    if not isinstance(value, str) or len(value) > 128:
        raise _Invalid()
    match = re.fullmatch(r'(\[[0-9a-fA-F:]+\]|[0-9.]+):([0-9]{1,5})', value)
    if not match:
        raise _Invalid()
    host, port = match.groups()
    bracketed = host.startswith('[')
    try:
        address = ipaddress.ip_address(host[1:-1] if bracketed else host)
    except ValueError:
        raise _Invalid() from None
    if bracketed != (address.version == 6) or not 1 <= int(port) <= 65535:
        raise _Invalid()
    if str(address) == '0.0.0.0':
        address = ipaddress.ip_address('127.0.0.1')
    if not address.is_loopback:
        raise _Invalid()
    host = f'[{address}]' if address.version == 6 else str(address)
    return f'http://{host}:{int(port)}'


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _Invalid()
        result[key] = value
    return result


def _json(data):
    def invalid(_):
        raise _Invalid()
    try:
        return json.loads(data.decode('utf-8-sig'), object_pairs_hook=_pairs,
                          parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise _Invalid() from None


def _get(opener, origin, endpoint, secret):
    headers = {'Accept': 'application/json'}
    if secret:
        headers['Authorization'] = 'Bearer ' + secret
    request = urllib.request.Request(origin + endpoint, headers=headers, method='GET')
    with closing(opener.open(request, timeout=TIMEOUT)) as response:
        if response.getcode() != 200 or response.geturl() != request.full_url:
            raise _Invalid()
        # A bounded read remains authoritative even without Content-Length.
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if not isinstance(data, bytes) or len(data) > MAX_RESPONSE_BYTES:
            raise _Invalid()
    return _json(data)


def _source(obj):
    if not isinstance(obj, dict):
        raise _Invalid()
    nodes = obj.get('proxies', [])
    groups = obj.get('proxy-groups', [])
    rules = obj.get('rules', [])
    if not isinstance(nodes, list) or not isinstance(groups, list) or not isinstance(rules, list):
        raise _Invalid()
    if len(nodes) + len(groups) > MAX_PROXIES:
        raise _Invalid()
    definitions, node_names, group_names = set(), set(), set()
    for entries, names in ((nodes, node_names), (groups, group_names)):
        for item in entries:
            if not isinstance(item, dict):
                raise _Invalid()
            name, kind = item.get('name'), item.get('type')
            if (not isinstance(name, str) or not name or len(name) > 1024
                    or name in definitions or name in BUILTINS
                    or not isinstance(kind, str) or not kind):
                raise _Invalid()
            definitions.add(name)
            names.add(name)
            if entries is nodes and (kind.lower() in SELECTOR_TYPES or kind.upper() in BUILTINS):
                raise _Invalid()
    finals = []
    for rule in rules:
        if not isinstance(rule, str):
            raise _Invalid()
        parts = [part.strip() for part in rule.split(',')]
        if parts[0].upper() in ('MATCH', 'FINAL'):
            if len(parts) != 2 or not parts[1]:
                raise _Invalid()
            finals.append(parts[1])
    if len(finals) != 1 or finals[0] not in definitions:
        raise _Invalid()
    return finals[0], node_names, group_names


def _selections(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('proxies'), dict):
        raise _Invalid()
    proxies = payload['proxies']
    if not proxies or len(proxies) > MAX_PROXIES:
        raise _Invalid()
    selections = {}
    for name, item in proxies.items():
        if not isinstance(name, str) or not name or len(name) > 1024 or not isinstance(item, dict):
            raise _Invalid()
        if not isinstance(item.get('type'), str) or not item['type']:
            raise _Invalid()
        if 'now' in item:
            now, members = item['now'], item.get('all')
            if (not isinstance(now, str) or not now or len(now) > 1024
                    or not isinstance(members, list) or len(members) > MAX_PROXIES
                    or not all(isinstance(x, str) and x and len(x) <= 1024 for x in members)
                    or len(members) != len(set(members)) or now not in members):
                raise _Invalid()
            selections[name] = now
    return proxies, selections


def inspect_selection(config_obj, opener=None):
    """Inspect a selected source without changing its client or configuration.

    ``opener`` may inject an object with ``open(Request, timeout=2)`` for tests.
    ``selection_origin`` distinguishes runtime evidence from config-fallback.
    ``available`` only means both controller responses passed schema checks.
    """
    result = {'available': False, 'selections': {}, 'selected_node': None,
              'warning': None, 'selection_origin': None}
    try:
        target, nodes, groups = _source(config_obj)
    except _Invalid:
        result['warning'] = 'RUNTIME_SELECTION_UNRESOLVED'
        return result
    if target in nodes:
        result.update(selected_node=target, selection_origin='config-fallback')
        return result
    try:
        origin = _controller(config_obj.get('external-controller'))
    except _Invalid:
        result['warning'] = 'RUNTIME_CONTROLLER_REJECTED'
        return result
    secret = config_obj.get('secret', '')
    if (not isinstance(secret, str) or len(secret) > 4096
            or any(ord(char) < 32 or ord(char) > 126 for char in secret)):
        result['warning'] = 'RUNTIME_SECRET_INVALID'
        return result
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        version = _get(opener, origin, '/version', secret)
        if (not isinstance(version, dict) or not isinstance(version.get('version'), str)
                or not version['version'] or len(version['version']) > 256):
            raise _Invalid()
        proxies, selections = _selections(_get(opener, origin, '/proxies', secret))
    except _Invalid:
        result['warning'] = 'RUNTIME_RESPONSE_INVALID'
        return result
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError, TypeError):
        result['warning'] = 'RUNTIME_PROBE_UNAVAILABLE'
        return result
    result.update(available=True, selections=selections)
    visited = set()
    for _ in range(MAX_HOPS):
        if target in visited:
            break
        visited.add(target)
        if target in nodes:
            if (target in proxies and target not in selections
                    and proxies[target]['type'].lower() not in SELECTOR_TYPES
                    and proxies[target]['type'].upper() not in BUILTINS):
                result.update(selected_node=target, selection_origin='runtime')
                return result
            break
        if target not in groups or target not in selections:
            break
        target = selections[target]
    result['warning'] = 'RUNTIME_SELECTION_UNRESOLVED'
    return result
