"""Private, offline candidate export for the lightweight native application.

Only new files in an explicitly supplied output directory are written. There
are no imports into a proxy client, network probes, downloads or core calls.
"""
import copy
import difflib
from pathlib import Path
import re
import base64
from types import SimpleNamespace

import ai_routing as ai
import chain_routing
import claude_setup as c
import domestic_policy as domestic
import unified_policy as unified


def _context():
    # Per-operation capability: never relax the legacy CLI's module context.
    return SimpleNamespace(**{**vars(c), 'allow_validated_dialer_chain': True})


def _read(path):
    path = Path(path).absolute()
    fmt = c.config_format(path, 'auto')
    c.require(fmt in ('json', 'yaml'), 'LITE_MIHOMO_FULL_CONFIG_REQUIRED')
    raw = c.read_bytes(path)
    obj = c.parse_config(raw, fmt)
    c.require(obj.get('mode', 'rule') == 'rule', 'LITE_RULE_MODE_REVIEW_REQUIRED')
    c.require(isinstance(obj.get('rules'), list)
              and bool(obj['rules']) and all(isinstance(rule, str) for rule in obj['rules']),
              'LITE_MIHOMO_FULL_CONFIG_REQUIRED')
    c.require(not any(key in obj for key in ('prepend', 'append', 'delete', 'script', 'scripts', 'sub-rules')),
              'LITE_FULL_CONFIG_REVIEW_REQUIRED')
    return path, fmt, raw, obj


def _dependencies(obj):
    """Inventory portability limits without touching paths or fetching URLs."""
    limits, warnings, details = [], [], []
    for field in ('proxy-providers', 'rule-providers'):
        providers = obj.get(field, {})
        c.require(isinstance(providers, dict), 'LITE_PROVIDERS_INVALID')
        for name, value in providers.items():
            c.require(isinstance(value, dict), 'LITE_PROVIDERS_INVALID')
            if field == 'proxy-providers' or value.get('type') != 'inline':
                code = 'EXTERNAL_' + field.upper().replace('-', '_')
                warnings.append(code)
                details.append({'kind': field, 'name': name, 'code': code, 'resolved': False})
            if value.get('type') == 'http':
                if not (isinstance(value.get('url'), str) and value['url'].startswith(('https://', 'http://'))):
                    limits.append('PROVIDER_DECLARATION_INCOMPLETE')
            elif value.get('type') not in ('inline', 'file'):
                limits.append('PROVIDER_TYPE_UNSUPPORTED')
            if value.get('type') == 'file' and not value.get('path'):
                limits.append('PROVIDER_DECLARATION_INCOMPLETE')
    def walk(value, location='config'):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('path', 'ca', 'ca-file', 'certificate', 'private-key', 'external-ui') and isinstance(child, str) and child:
                    # Inline PEM material is retained as data, not treated as a path.
                    # An HTTP provider's path is the existing client's cache,
                    # not a local input we claim to have read or bundled.
                    http_cache = key == 'path' and value.get('type') == 'http' and (
                        location.startswith('config.rule-providers.') or location.startswith('config.proxy-providers.'))
                    # Transport request paths are URL components, not files.
                    transport_path = key == 'path' and bool(re.fullmatch(
                        r'config\.proxies\[\d+\]\.(?:ws|http|h2|http-upgrade|xhttp)-opts', location))
                    inline_wg_key = False
                    if key == 'private-key' and value.get('type') == 'wireguard':
                        try:
                            inline_wg_key = len(base64.b64decode(child, validate=True)) == 32
                        except (ValueError, TypeError):
                            pass
                    if '-----BEGIN ' not in child and not http_cache and not transport_path and not inline_wg_key:
                        limits.append('LOCAL_RESOURCE_PATH_NOT_REBASED')
                        details.append({'kind': 'local_resource', 'location': location + '.' + key,
                                        'code': 'LOCAL_RESOURCE_PATH_NOT_REBASED', 'resolved': False})
                walk(child, location + '.' + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, location + '[' + str(index) + ']')
    walk(obj)
    if any(re.search(r'(?:^|[,(])\s*(?:GEOIP|GEOSITE|IP-ASN)\s*,', rule, re.I) for rule in obj['rules']):
        warnings.append('GEODATA_RESOURCE_NOT_VERIFIED')
        details.append({'kind': 'geodata', 'code': 'GEODATA_RESOURCE_NOT_VERIFIED', 'resolved': False})
    if obj.get('geox-url') or obj.get('external-ui-url'):
        warnings.append('EXTERNAL_RESOURCE_NOT_VERIFIED')
        details.append({'kind': 'external_resource', 'code': 'EXTERNAL_RESOURCE_NOT_VERIFIED', 'resolved': False})
    return {'blockers': list(dict.fromkeys(limits)), 'warnings': list(dict.fromkeys(warnings + limits)),
            'dependencies': details, 'same_client_required': bool(details)}


def _direct_review(obj, preserve):
    c.require(type(preserve) is bool, 'LITE_PRESERVE_FLAG_INVALID')
    unknown, _ = unified.direct_decisions(c, obj, 'yaml')
    entries = []
    for rule in dict.fromkeys(unknown):
        classification = unified.classify_direct_rule(rule)
        if classification['decision'] == 'pending' and preserve:
            classification = {'classification': 'preserved_existing', 'decision': 'keep',
                              'reason': 'Explicitly preserve the baseline DIRECT intent; destination safety and runtime are not verified.'}
        entries.append({'rule': rule, **classification})
    return {'schema': 'claude-direct-review/1', 'config_semantic_sha256': c.sha(c.encode(obj)),
            'entries': entries, 'runtime_verified': False,
            'preserve_existing_direct': preserve}


def inspect_config(path):
    """Return private local labels and graph metadata, never node credentials."""
    _, fmt, raw, obj = _read(path)
    context = _context()
    data = chain_routing.graph(context, obj)
    review = _direct_review(obj, False)
    nodes, chains = [], []
    for name, value in data['definitions'].items():
        if data['kinds'][name] != 'node':
            continue
        row = {'name': name, 'type': value['type'], 'has_chain': bool(data['edges'][name]),
               'selectable': True}
        try:
            validated = chain_routing.validate(context, obj, name)
        except c.SetupError as exc:
            row['selectable'] = False
            row['reason'] = str(exc)
        else:
            if data['edges'][name]:
                chains.append(validated)
        nodes.append(row)
    dependency_info = _dependencies(obj)
    warnings = list(dependency_info['warnings'])
    if data['dynamic']:
        warnings.append('PROVIDER_SELECTOR_MEMBERS_NOT_VERIFIED')
    pending = sum(entry['decision'] == 'pending' for entry in review['entries'])
    if pending:
        warnings.append('EXISTING_DIRECT_REQUIRES_EXPLICIT_PRESERVATION')
    return {'schema': 'lite-config-inspection/1', 'format': fmt, 'source_sha256': c.sha(raw),
            'nodes': nodes, 'chains': chains,
            'pending_direct_count': pending, 'runtime_verified': False,
            'portable': False, 'portability': 'not_verified',
            'export_ready': not dependency_info['blockers'], **dependency_info, 'warnings': warnings}


def _managed_group(obj, requested):
    ai.label(c, requested)
    existing = {entry['name'].casefold() for entry in obj.get('proxies', []) + obj.get('proxy-groups', [])}
    for number in range(1, 10002):
        name = requested if number == 1 else requested + '-' + str(number)
        ai.label(c, name)
        ai.label(c, name + '-Claude')
        if all(candidate.casefold() not in existing for candidate in (name, name + '-Claude')):
            return name
    raise c.SetupError('LITE_GROUP_NAME_UNAVAILABLE')


def _build(obj, node, group, preserve):
    context = _context()
    chain_routing.validate(context, obj, node)
    group = _managed_group(obj, group)
    review = _direct_review(obj, preserve)
    c.require(not any(entry['decision'] == 'pending' for entry in review['entries']),
              'LITE_EXISTING_DIRECT_REVIEW_REQUIRED')
    structural = c.config_summary(c.encode(obj), 'json')
    c.require(all(structural[key] == 0 for key in
                  ('unknown_references', 'duplicate_names', 'cyclic_groups', 'rules_after_catchall', 'unsupported_rule_count')),
              'LITE_CONFIG_STRUCTURE_REVIEW_REQUIRED')
    expected = domestic.build_semantics(context, obj, 'yaml', node, group, review)
    # Preserve exact imported node definitions, including every chain field and
    # credential. The legacy builder's selected-node ip-version rewrite is not
    # part of the lightweight application's offline export contract.
    expected['proxies'] = copy.deepcopy(obj['proxies'])
    original_groups = obj.get('proxy-groups', [])
    c.require(expected['proxy-groups'][:len(original_groups)] == original_groups,
              'LITE_EXISTING_SELECTORS_CHANGED')
    chain_routing.validate(context, expected, node)
    return expected, review, group


def _audit_result(raw, actual_bytes, obj, expected, actual, actual_group):
    match = actual == expected
    return {'schema': 'lite-static-audit/1', 'status': 'static_policy_matches' if match else 'unexpected_changes',
            'source_sha256': c.sha(raw), 'candidate_sha256': c.sha(actual_bytes),
            'original_nodes_preserved': actual.get('proxies') == obj.get('proxies'),
            'managed_group': actual_group,
            'runtime_verified': False, 'application_loaded': 'not_verified'}


def audit_candidate(source, candidate, node, group=ai.GROUP, preserve_existing_direct=False):
    """Deterministic file-only audit; changing an unrelated field fails too."""
    _, _, raw, obj = _read(source)
    expected, _, actual_group = _build(obj, node, group, preserve_existing_direct)
    actual_bytes = c.read_bytes(candidate)
    actual = c.parse_config(actual_bytes, 'yaml')
    return _audit_result(raw, actual_bytes, obj, expected, actual, actual_group)


def _dump_yaml(expected):
    try:
        import yaml
    except ImportError:
        raise c.SetupError('YAML_DEPENDENCY_MISSING') from None
    return yaml.safe_dump(expected, allow_unicode=True, sort_keys=False).encode('utf-8')


def prepare_candidate(source_path, node, output_dir, preserve_existing_direct=False, group=ai.GROUP):
    """Create a separate YAML and private evidence; never alter the source."""
    source, fmt, original_bytes, obj = _read(source_path)
    c.require(not _dependencies(obj)['blockers'], 'LITE_DEPENDENCIES_UNRESOLVED')
    expected, review, actual_group = _build(obj, node, group, preserve_existing_direct)
    regenerated = False
    if fmt == 'yaml':
        # The shared renderer already performs a full strict YAML roundtrip.
        try:
            candidate = unified.render_yaml(c, c.decode(original_bytes), expected).encode('utf-8')
            parsed_candidate = expected
        except c.SetupError:
            # Valid full YAML can use a flow-style root mapping that the shared
            # minimal-edit renderer cannot extend. Regenerate only the separate
            # candidate, then verify the complete semantics strictly.
            regenerated = True
            header = []
            for line in c.decode(original_bytes).splitlines(keepends=True):
                if line.strip() and not line.lstrip().startswith('#'):
                    break
                header.append(line)
            candidate = ''.join(header).encode('utf-8') + _dump_yaml(expected)
            parsed_candidate = c.parse_config(candidate, 'yaml')
    else:
        # JSON is a YAML subset. Emit human-readable YAML for either input kind.
        candidate = _dump_yaml(expected)
        parsed_candidate = c.parse_config(candidate, 'yaml')
    c.require(len(candidate) <= c.MAX_FILE and parsed_candidate == expected,
              'LITE_CANDIDATE_ROUNDTRIP_FAILED')
    c.require(c.read_bytes(source) == original_bytes, 'LITE_SOURCE_CHANGED')
    dependency_info = _dependencies(expected)
    c.require(not dependency_info['blockers'], 'LITE_DEPENDENCIES_UNRESOLVED')
    if regenerated:
        dependency_info['warnings'].append('CANDIDATE_YAML_FORMATTING_REGENERATED')
    summary = {'schema': 'lite-private-candidate/1', 'policy': 'domestic-v4-preserved-chain',
               'source_format': fmt, 'source_sha256': c.sha(original_bytes), 'candidate_sha256': c.sha(candidate),
               'selected_node': node, 'chain': chain_routing.validate(_context(), obj, node),
               'direct_review': review,
               'managed_group': actual_group, 'export_ready': True, **dependency_info,
               'portable': False, 'portability': 'not_verified',
               'runtime_verified': False, 'application_loaded': 'not_verified', 'apply_supported': False,
               'source_unchanged': True, 'original_nodes_preserved': True}
    folder = Path(output_dir).absolute()
    c.require(folder.resolve() != source.resolve(), 'DISTINCT_CANDIDATE_REQUIRED')
    c.new_dir(folder)
    path, summary_path = folder / 'candidate.yaml', folder / 'summary.private.json'
    c.write_new(path, candidate)
    c.write_new(folder / 'original.private.bin', original_bytes)
    changes = ''.join(difflib.unified_diff(c.decode(original_bytes).splitlines(keepends=True),
                                         candidate.decode('utf-8').splitlines(keepends=True),
                                         fromfile='original', tofile='candidate'))
    c.write_new(folder / 'diff.private.txt', changes.encode('utf-8'))
    # Reuse the completed roundtrip only after exact output-byte readback. This
    # avoids repeatedly parsing the same large bundled domestic domain list.
    c.require(c.read_bytes(path) == candidate, 'LITE_EXPORT_READBACK_FAILED')
    audit = _audit_result(original_bytes, candidate, obj, expected, parsed_candidate, actual_group)
    c.require(audit['status'] == 'static_policy_matches' and c.read_bytes(source) == original_bytes,
              'LITE_EXPORT_AUDIT_FAILED')
    c.write_new(folder / 'audit.private.json', c.encode(audit))
    c.write_new(summary_path, c.encode(summary))
    return {'candidate_path': str(path), 'summary_path': str(summary_path),
            'private_summary': summary, 'runtime_verified': False, 'apply_supported': False,
            'managed_group': actual_group, 'export_ready': True, **dependency_info}
