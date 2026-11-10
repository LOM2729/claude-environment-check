"""Fixed Clash Verge Rev 2.5.8 rules adapter; no UI/reload/core control.

Profile option/rules layout follows the product's v2.5.8 PrfItem schema:
https://github.com/clash-verge-rev/clash-verge-rev/blob/v2.5.8/src-tauri/src/config/prfitem.rs
The adapter creates exact-byte candidates and reuses our text transaction engine.
It never treats a successful file write as application or route acceptance.
"""
from pathlib import Path
import os
import platform
import plistlib
import re
import subprocess
from types import SimpleNamespace

import config_recovery as storage

COMMANDS = ('native-client-plan', 'native-client-apply', 'native-client-check', 'native-client-rollback')
MUTATING_COMMANDS = ('native-client-apply', 'native-client-rollback')
SCHEMA = 'clearpath-native-client/1'
APP_INFO = Path('/Applications/Clash Verge.app/Contents/Info.plist')
SUPPORT = Path('Library/Application Support/io.github.clash-verge-rev.clash-verge-rev')
MAX_DOCUMENT = 4 * 1024 * 1024


def register_commands(sub):
    p = sub.add_parser('native-client-plan', help='Inspect fixed installed Clash profile and prepare private rules diff')
    p.add_argument('--request', required=True, help='Explicit DOMAIN/DOMAIN-SUFFIX rule request JSON')
    p.add_argument('--out', required=True)
    for command in COMMANDS[1:]:
        p = sub.add_parser(command, help='Fixed native rules transaction; never reloads application or core')
        p.add_argument('--plan', required=True)
        p.add_argument('--plan-sha256', required=True)
        if command in ('native-client-check', 'native-client-rollback'):
            p.add_argument('--receipt', required=True)
            p.add_argument('--receipt-sha256', required=True)
        if command in MUTATING_COMMANDS:
            p.add_argument('--allow-write', action='store_true')
            p.add_argument('--writer-stopped', action='store_true')
        p.add_argument('--out', required=True)


def _basename(c, value):
    c.require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.ya?ml', value), 'NATIVE_CLIENT_PROFILE_FILENAME_INVALID')
    return value


def _uid(c, value):
    c.require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value), 'NATIVE_CLIENT_UID_INVALID')
    return value


class NativeHost:
    def supported(self, c):
        c.require(platform.system() == 'Darwin', 'NATIVE_CLIENT_PLATFORM_UNSUPPORTED')

    def binding(self):
        return storage._binding()

    def paths(self):
        return APP_INFO, Path.home() / SUPPORT

    def apply_text(self, c, folder, pin, output):
        return storage.apply(c, folder, pin, True, True, output)

    def rollback_text(self, c, receipt, pin, output):
        return storage.rollback(c, receipt, pin, True, True, output)

    def guard(self, c):
        self.supported(c)
        try:
            done = subprocess.run(['/bin/ps', '-axo', 'comm='], stdin=subprocess.DEVNULL,
                                  capture_output=True, check=False, timeout=5, shell=False,
                                  env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            c.require(done.returncode == 0 and 0 < len(done.stdout) <= 1024 * 1024, 'NATIVE_CLIENT_PROCESS_STATE_UNAVAILABLE')
            commands = done.stdout.decode('utf-8').splitlines()
        except (OSError, UnicodeError, subprocess.SubprocessError):
            raise c.SetupError('NATIVE_CLIENT_PROCESS_STATE_UNAVAILABLE') from None
        # The GUI writes profiles. Its surviving core/service must not be killed.
        for command in commands:
            command = command.strip()
            c.require(not (command.startswith('/Applications/Clash Verge.app/') or
                           Path(command).name == 'clash-verge'), 'NATIVE_CLIENT_GUI_RUNNING')


def _app_snapshot(c, path):
    c.require(path.is_absolute() and '..' not in path.parts, 'NATIVE_CLIENT_APP_PATH_INVALID')
    for entry in (path, *path.parents):
        s = entry.lstat()
        c.require(not entry.is_symlink(), 'NATIVE_CLIENT_APP_LINK_REJECTED')
    info = path.lstat()
    c.require(info.st_uid in (0, os.getuid()) and not info.st_mode & 0o022 and info.st_nlink == 1,
              'NATIVE_CLIENT_APP_METADATA_UNTRUSTED')
    raw = c.read_bytes(path, MAX_DOCUMENT)
    c.require(storage._fingerprint(info) == storage._fingerprint(path.lstat()), 'NATIVE_CLIENT_APP_CHANGED')
    try:
        parsed = plistlib.loads(raw)
    except Exception:
        raise c.SetupError('NATIVE_CLIENT_PLIST_INVALID') from None
    c.require(type(parsed) is dict and parsed.get('CFBundleShortVersionString') == '2.5.8', 'NATIVE_CLIENT_VERSION_UNSUPPORTED')
    c.require(parsed.get('CFBundleIdentifier') == 'io.github.clash-verge-rev.clash-verge-rev', 'NATIVE_CLIENT_PRODUCT_UNSUPPORTED')
    return {'path': str(path), 'identity': storage._fingerprint(info), 'sha256': c.sha(raw)}


def capture(c, host=None):
    host = host or NativeHost()
    host.supported(c)
    app, support = host.paths()
    support, _ = storage._safe_path(c, support, directory=True)
    app_state = _app_snapshot(c, app)
    index_path = support / 'profiles.yaml'
    index_raw, index_state = storage._snapshot(c, index_path)
    index = c.parse_config(index_raw, 'yaml')
    current = _uid(c, index.get('current'))
    items = index.get('items')
    c.require(type(items) is list and 1 <= len(items) <= 4096 and all(type(x) is dict for x in items), 'NATIVE_CLIENT_PROFILE_INDEX_INVALID')
    ids = [_uid(c, item.get('uid')) for item in items]
    c.require(len(set(ids)) == len(ids), 'NATIVE_CLIENT_PROFILE_ALIAS_CONFLICT')
    matching = [x for x in items if x['uid'] == current]
    c.require(len(matching) == 1 and matching[0].get('type') in ('local', 'remote'), 'NATIVE_CLIENT_CURRENT_PROFILE_UNSUPPORTED')
    active = matching[0]
    options = active.get('option')
    c.require(type(options) is dict, 'NATIVE_CLIENT_PROFILE_OPTIONS_REQUIRED')
    rules_uid = _uid(c, options.get('rules'))
    extensions = [x for x in items if x['uid'] == rules_uid]
    c.require(len(extensions) == 1 and extensions[0].get('type') == 'rules', 'NATIVE_CLIENT_RULES_EXTENSION_REQUIRED')
    extension = extensions[0]
    c.require(sum(type(x.get('option')) is dict and x['option'].get('rules') == rules_uid for x in items) == 1,
              'NATIVE_CLIENT_SHARED_EXTENSION_REJECTED')
    c.require(index.get('rules') != rules_uid and rules_uid.lower() not in ('rules', 'global', 'default'),
              'NATIVE_CLIENT_GLOBAL_EXTENSION_REJECTED')
    base_name, rules_name = _basename(c, active.get('file')), _basename(c, extension.get('file'))
    c.require(base_name != rules_name and sum(x.get('file') == rules_name for x in items) == 1 and
              sum(x.get('file') == base_name for x in items) == 1, 'NATIVE_CLIENT_FILE_ALIAS_CONFLICT')
    base_path, target = support / 'profiles' / base_name, support / 'profiles' / rules_name
    base_raw, base_state = storage._snapshot(c, base_path)
    target_raw, target_state = storage._snapshot(c, target)
    base = c.parse_config(base_raw, 'yaml')
    rules = c.parse_config(target_raw, 'yaml')
    c.require(set(rules) == {'prepend', 'append', 'delete'} and
              all(type(rules[k]) is list for k in rules), 'NATIVE_CLIENT_RULES_SCHEMA_UNSUPPORTED')
    c.require(rules['append'] == [] and rules['delete'] == [], 'NATIVE_CLIENT_APPEND_DELETE_UNSUPPORTED')
    groups = base.get('proxy-groups', [])
    proxies = base.get('proxies', [])
    c.require(type(groups) is list and type(proxies) is list and
              all(type(x) is dict and type(x.get('name')) is str for x in groups + proxies), 'NATIVE_CLIENT_BASE_PROFILE_INVALID')
    names = [x['name'] for x in groups + proxies]
    c.require(len(set(names)) == len(names), 'NATIVE_CLIENT_POLICY_ALIAS_CONFLICT')
    binding = {'platform_binding': host.binding(), 'product': 'clash-verge-rev', 'version': '2.5.8',
               'current_uid': current, 'rules_uid': rules_uid, 'target_path': str(target),
               'sources': {'app': app_state, 'index': index_state, 'base': base_state},
               'later_chain_review_required': bool(options.get('merge') or options.get('script'))}
    return {'binding': binding, 'target_bytes': target_raw, 'target_snapshot': target_state,
            'rules': rules, 'policy_names': set(names) | {'REJECT', 'REJECT-DROP'}}


def candidate(c, observed, request):
    c.require(type(request) is dict and set(request) == {'schema', 'target_alias', 'rules'} and
              request.get('schema') == 'clearpath-native-rules/1', 'NATIVE_CLIENT_REQUEST_INVALID')
    c.require(type(request['target_alias']) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', request['target_alias']), 'NATIVE_CLIENT_TARGET_ALIAS_INVALID')
    requested = request['rules']
    c.require(type(requested) is list and 1 <= len(requested) <= 64 and
              all(type(x) is str for x in requested) and len(set(requested)) == len(requested), 'NATIVE_CLIENT_RULE_COUNT_INVALID')
    for rule in requested:
        c.require(type(rule) is str and len(rule) <= 512 and not any(ord(x) < 32 for x in rule), 'NATIVE_CLIENT_RULE_INVALID')
        parts = rule.split(',')
        c.require(len(parts) == 3 and parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX'), 'NATIVE_CLIENT_RULE_KIND_UNSUPPORTED')
        domain, policy = parts[1:]
        c.require(0 < len(domain) <= 253 and domain == domain.lower() and
                  all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in domain.split('.')),
                  'NATIVE_CLIENT_DOMAIN_INVALID')
        c.require(policy in observed['policy_names'] and not any(x in policy for x in (',', '\r', '\n')),
                  'NATIVE_CLIENT_POLICY_NOT_IN_ACTIVE_PROFILE')
    if observed['rules']['prepend'] == requested:
        return observed['target_bytes']
    c.require(observed['rules']['prepend'] == [], 'NATIVE_CLIENT_NONEMPTY_PREPEND_UNSUPPORTED')
    raw = observed['target_bytes']
    try:
        text = raw.decode('utf-8')  # Preserve BOM rather than stripping it.
    except UnicodeError:
        raise c.SetupError('NATIVE_CLIENT_UTF8_REQUIRED') from None
    matches = list(re.finditer(r'(?m)^(?:\ufeff)?[ \t]*prepend[ \t]*:[ \t]*(\[[ \t]*\])(?=[ \t]*(?:#[^\r\n]*)?(?:\r?$))', text))
    c.require(len(matches) == 1, 'NATIVE_CLIENT_EMPTY_INLINE_PREPEND_REQUIRED')
    match = matches[0]
    import json
    contents = ', '.join(json.dumps(rule, ensure_ascii=False) for rule in requested)
    start, end = match.span(1)
    empty = text[start:end]
    changed = (text[:start] + empty[:-1] + contents + ']' + text[end:]).encode('utf-8')
    parsed = c.parse_config(changed, 'yaml')
    c.require(parsed == dict(observed['rules'], prepend=requested), 'NATIVE_CLIENT_CANDIDATE_READBACK_FAILED')
    return changed


def prepare(c, request, output, host=None):
    host = host or NativeHost()
    observed = capture(c, host)
    after = candidate(c, observed, request)
    if after == observed['target_bytes']:
        return {'status': 'no_change', 'exit_code': 0, 'config_file_changed': False,
                'application_reload': 'not_run', 'network_requests': 0}
    folder = storage._private_dir(c, output, create=True)
    proposed = folder / 'candidate.private.yaml'
    storage._write(c, proposed, after)
    prepared = storage.prepare(c, observed['binding']['target_path'], proposed, folder / 'text-plan')
    # Re-read all sources and target after creating the private material.
    current = capture(c, host)
    c.require(current['binding'] == observed['binding'] and current['target_snapshot'] == observed['target_snapshot'], 'NATIVE_CLIENT_SOURCE_CHANGED')
    value = {'schema': SCHEMA, 'kind': 'plan', 'created_at': c.now(), 'target_alias': request['target_alias'],
             'binding': observed['binding'], 'request': request, 'request_sha256': c.sha(c.encode(request)),
             'text_plan_sha256': prepared['plan_sha256'], 'authorization_saved': False}
    raw = c.encode(value)
    storage._write(c, folder / 'native-plan.private.json', raw)
    return {'status': 'native_plan_written', 'exit_code': 0, 'plan_sha256': c.sha(raw),
            'product': 'clash-verge-rev', 'version': '2.5.8', 'rules': len(request['rules']),
            'later_chain_review_required': observed['binding']['later_chain_review_required'],
            'config_file_changed': False, 'application_reload': 'not_run', 'network_requests': 0}


def _plan(c, folder, pin, host):
    c.require(type(pin) is str and re.fullmatch(r'[a-f0-9]{64}', pin), 'NATIVE_CLIENT_DIGEST_REQUIRED')
    folder = storage._private_dir(c, folder)
    raw = c.read_bytes(storage._safe_path(c, folder / 'native-plan.private.json')[0], MAX_DOCUMENT)
    c.require(c.sha(raw) == pin, 'NATIVE_CLIENT_PLAN_CHANGED')
    value = c.load_json(raw)
    c.require(type(value) is dict and value.get('schema') == SCHEMA and value.get('kind') == 'plan' and
              value.get('binding', {}).get('platform_binding') == host.binding(), 'NATIVE_CLIENT_PLAN_INVALID')
    c.require(c.sha(c.encode(value.get('request'))) == value.get('request_sha256') and
              value.get('request', {}).get('target_alias') == value.get('target_alias'), 'NATIVE_CLIENT_REQUEST_CHANGED')
    # The text plan's target is independently bound; no path from an imported
    # native plan may silently point the generic transaction at another object.
    _, text_plan = storage._artifact(c, folder / 'text-plan', 'plan.json', value['text_plan_sha256'], 'plan')
    c.require(text_plan['target']['path'] == value['binding']['target_path'], 'NATIVE_CLIENT_TEXT_PLAN_SCOPE_CHANGED')
    return folder, value


def _guarded_context(c, host, expected):
    def recheck():
        host.guard(c)
        c.require(capture(c, host)['binding'] == expected, 'NATIVE_CLIENT_SOURCE_CHANGED')
    recheck()
    original = c.read_bytes
    def read_bytes(path, maximum=None):
        recheck()
        return original(path) if maximum is None else original(path, maximum)
    guarded = SimpleNamespace(**vars(c))
    guarded.read_bytes = read_bytes
    return guarded, recheck


def apply(c, folder, pin, output, allow=False, stopped=False, host=None):
    host = host or NativeHost()
    host.supported(c)
    c.require(allow and stopped, 'NATIVE_CLIENT_CURRENT_WRITE_AND_STOPPED_CONFIRMATION_REQUIRED')
    folder, value = _plan(c, folder, pin, host)
    _, text_plan = storage._artifact(c, folder / 'text-plan', 'plan.json', value['text_plan_sha256'], 'plan')
    before, after = storage._snapshots(c, folder / 'text-plan', text_plan)
    observed = capture(c, host)
    observed['target_bytes'], observed['rules'] = before, c.parse_config(before, 'yaml')
    c.require(candidate(c, observed, value['request']) == after, 'NATIVE_CLIENT_CANDIDATE_SCOPE_CHANGED')
    guarded, recheck = _guarded_context(c, host, value['binding'])
    result = host.apply_text(guarded, folder / 'text-plan', value['text_plan_sha256'], output)
    result.update(native_adapter='clash-verge-rev-2.5.8-rules', application_reload='not_run',
                  effective_routing='not_run', writer_exclusion='operator_stopped_and_detect_only',
                  exit_code=0 if result.get('required_checks_completed') else 2)
    if result.get('recovery_state') == 'committed':
        result['status'] = 'written_but_not_verified'
    try:
        recheck()
    except (Exception, KeyboardInterrupt):
        result.update(status='partial_or_unconfirmed', exit_code=2, reason_code='NATIVE_CLIENT_POST_WRITE_SOURCE_CHANGED',
                      required_checks_completed=False)
    return result


def check(c, folder, pin, receipt, receipt_pin, output, host=None):
    host = host or NativeHost()
    host.supported(c)
    _, value = _plan(c, folder, pin, host)
    # Reject a receipt for a different file even if its own text transaction is valid.
    _, intent, _, _, _ = storage._load_receipt(c, receipt, receipt_pin)
    c.require(intent['target']['path'] == value['binding']['target_path'] and intent.get('action') == 'apply' and
              intent.get('origin_sha256') == value['text_plan_sha256'], 'NATIVE_CLIENT_RECEIPT_SCOPE_CHANGED')
    result = storage.check(c, receipt, receipt_pin, output)
    result.update(native_adapter='clash-verge-rev-2.5.8-rules', application_reload='not_verified',
                  effective_routing='not_verified', exit_code=0 if result.get('required_checks_completed') else 2)
    try:
        matches = capture(c, host)['binding'] == value['binding']
    except (c.SetupError, OSError, ValueError):
        matches = False
    result['native_source_binding_matches'] = matches
    if not matches:
        result.update(exit_code=2, required_checks_completed=False, reason_code='NATIVE_CLIENT_SOURCE_CHANGED')
    return result


def rollback(c, folder, pin, receipt, receipt_pin, output, allow=False, stopped=False, host=None):
    host = host or NativeHost()
    host.supported(c)
    c.require(allow and stopped, 'NATIVE_CLIENT_CURRENT_WRITE_AND_STOPPED_CONFIRMATION_REQUIRED')
    _, value = _plan(c, folder, pin, host)
    _, intent, _, _, _ = storage._load_receipt(c, receipt, receipt_pin)
    c.require(intent['target']['path'] == value['binding']['target_path'] and intent.get('action') == 'apply' and
              intent.get('origin_sha256') == value['text_plan_sha256'], 'NATIVE_CLIENT_RECEIPT_SCOPE_CHANGED')
    guarded, recheck = _guarded_context(c, host, value['binding'])
    result = host.rollback_text(guarded, receipt, receipt_pin, output)
    result.update(native_adapter='clash-verge-rev-2.5.8-rules', application_reload='not_run',
                  effective_routing='not_run', exit_code=0 if result.get('required_checks_completed') else 2)
    try:
        recheck()
    except (Exception, KeyboardInterrupt):
        result.update(status='partial_or_unconfirmed', exit_code=2, reason_code='NATIVE_CLIENT_POST_WRITE_SOURCE_CHANGED',
                      required_checks_completed=False)
    return result


def run(c, args):
    if args.command == 'native-client-plan':
        return prepare(c, c.load_json(c.read_bytes(args.request, MAX_DOCUMENT)), args.out)
    if args.command == 'native-client-apply':
        return apply(c, args.plan, args.plan_sha256, args.out, args.allow_write, args.writer_stopped)
    if args.command == 'native-client-check':
        return check(c, args.plan, args.plan_sha256, args.receipt, args.receipt_sha256, args.out)
    if args.command == 'native-client-rollback':
        return rollback(c, args.plan, args.plan_sha256, args.receipt, args.receipt_sha256,
                        args.out, args.allow_write, args.writer_stopped)
    raise c.SetupError('NATIVE_CLIENT_COMMAND_UNKNOWN')
