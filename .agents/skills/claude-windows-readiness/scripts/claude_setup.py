#!/usr/bin/env python3
"""Customer readiness: local review, opt-in probes and guarded launch; no settings writes."""
import argparse
import datetime as dt
import difflib
import hashlib
import html
import ipaddress
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace

VERSION = '0.6.0'
MAX_FILE = 2 * 1024 * 1024
ENV_KEYS = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN',
            'ANTHROPIC_BASE_URL', 'CLAUDE_CONFIG_DIR', 'HTTP_PROXY', 'HTTPS_PROXY',
            'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
RULE_TYPES = {'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'IP-CIDR', 'IP-CIDR6',
              'IP-ASN', 'GEOIP', 'GEOSITE', 'RULE-SET', 'PROCESS-NAME', 'PROCESS-PATH',
              'DST-PORT', 'SRC-PORT', 'NETWORK', 'AND', 'OR', 'NOT', 'MATCH', 'FINAL'}
BUILTINS = {'DIRECT', 'REJECT', 'REJECT-DROP', 'REJECT-NO-DROP', 'PASS', 'COMPATIBLE', 'GLOBAL'}
CONFIG_KEYS = {'kind', 'proxy_count', 'group_count', 'rule_count', 'external_rule_source_count', 'unknown_references',
               'duplicate_names', 'cyclic_groups', 'rules_after_catchall',
               'unsupported_rule_count', 'scripts_present', 'rewrite_present', 'mitm_present', 'tls_verification_disabled',
               'dns_enabled', 'dns_ipv6', 'tun_enabled', 'mode', 'parse_status'}


class SetupError(Exception):
    """Only fixed public error codes leave the CLI; never echo private input."""


def require(condition, code):
    if not condition:
        raise SetupError(code)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path, maximum=MAX_FILE):
    """Bounded regular-file read, no leaf symlinks, detect observed replacement/change."""
    path = Path(path).absolute()
    try:
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode), 'REGULAR_FILE_REQUIRED')
        require(before.st_size <= maximum, 'INPUT_TOO_LARGE')
        fd = os.open(str(path), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino), 'INPUT_CHANGED')
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        final = path.lstat()
        fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(fingerprint(before) == fingerprint(after) == fingerprint(final), 'INPUT_CHANGED')
        require(len(data) <= maximum, 'INPUT_TOO_LARGE')
        return data
    except SetupError:
        raise
    except OSError:
        raise SetupError('INPUT_UNAVAILABLE') from None


def decode(data):
    try:
        text = data.decode('utf-8-sig')
        require('\x00' not in text, 'INVALID_TEXT')
        return text
    except UnicodeError:
        raise SetupError('UTF8_REQUIRED') from None


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_KEY')
        result[key] = value
    return result


def load_json(data):
    try:
        return json.loads(decode(data), object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(SetupError('INVALID_NUMBER')))
    except SetupError:
        raise
    except (ValueError, RecursionError):
        raise SetupError('INVALID_JSON') from None


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def write_new(path, data):
    """Create a new output only; refuse overwrite/symlink and do not create parents."""
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
    except OSError:
        raise SetupError('OUTPUT_EXISTS_OR_UNAVAILABLE') from None


def new_dir(path):
    try:
        Path(path).mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError:
        raise SetupError('NEW_OUTPUT_DIRECTORY_REQUIRED') from None


def run_fixed(argv, timeout=6):
    """Fixed local commands; output stays in memory and is projected before reporting."""
    try:
        # File-backed capture bounds memory, then reject oversized native output.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=errors, shell=False)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
                return None
            if code:
                return None
            output.seek(0, 2)
            if output.tell() > MAX_FILE:
                return None
            output.seek(0)
            return output.read().decode('utf-8-sig', errors='replace').strip()
    except (OSError, subprocess.SubprocessError):
        return None


def language(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*(?:@[-A-Za-z0-9=;]+)?', value) and len(value) < 80 else None


def languages(value):
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(x.strip() for x in value[:30] if isinstance(x, str) and language(x.strip())))


def version(value):
    return value if isinstance(value, str) and re.fullmatch(r'\d+(?:\.\d+){0,4}', value) else None


def timezone_name(value):
    return value if isinstance(value, str) and len(value) <= 100 and re.fullmatch(r'[A-Za-z0-9_+:/ .()-]+', value) else None


def count(value):
    return value if type(value) is int and 0 <= value <= 100000 else None


def boolean(value):
    return value if type(value) is bool else None


def project_native(raw):
    """Allowlisted schema; never trust raw native error text or arbitrary JSON fields."""
    raw = raw if isinstance(raw, dict) else {}
    result = {k: boolean(raw.get(k)) for k in (
        'http_proxy_enabled', 'https_proxy_enabled', 'socks_proxy_enabled',
        'pac_present', 'auto_time_enabled', 'auto_timezone_enabled', 'time_service_running')}
    result.update({k: count(raw.get(k)) for k in ('dns_v4_count', 'dns_v6_count',
        'ipv4_interface_count', 'ipv6_interface_count', 'tunnel_interface_count')})
    result['system_version'] = version(raw.get('system_version'))
    result['timezone'] = timezone_name(raw.get('timezone'))
    result['system_locale'] = language(raw.get('system_locale'))
    result['ui_locale'] = language(raw.get('ui_locale'))
    result['languages'] = languages(raw.get('languages'))
    return result


def mac_native():
    raw = {'system_version': run_fixed(['/usr/bin/sw_vers', '-productVersion'])}
    try:
        target = str(Path('/etc/localtime').resolve())
        if '/zoneinfo/' in target:
            raw['timezone'] = target.split('/zoneinfo/', 1)[1]
    except OSError:
        pass
    raw['system_locale'] = run_fixed(['/usr/bin/defaults', 'read', '-g', 'AppleLocale'])
    lang = run_fixed(['/usr/bin/defaults', 'read', '-g', 'AppleLanguages'])
    if lang is not None:
        raw['languages'] = re.findall(r'(?m)^\s*"?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*)"?,?\s*$', lang)
    proxy = run_fixed(['/usr/sbin/scutil', '--proxy'])
    if proxy is not None:
        for key, native in [('http_proxy_enabled', 'HTTPEnable'), ('https_proxy_enabled', 'HTTPSEnable'),
                            ('socks_proxy_enabled', 'SOCKSEnable'), ('pac_present', 'ProxyAutoConfigEnable')]:
            match = re.search(r'(?m)^\s*' + native + r'\s*:\s*([01])\s*$', proxy)
            raw[key] = bool(int(match.group(1))) if match else None
    dns = run_fixed(['/usr/sbin/scutil', '--dns'])
    if dns is not None:
        families = []
        for addr in re.findall(r'nameserver\[\d+\]\s*:\s*(\S+)', dns):
            try:
                families.append(ipaddress.ip_address(addr.split('%')[0]).version)
            except ValueError:
                pass
        raw['dns_v4_count'] = families.count(4)
        raw['dns_v6_count'] = families.count(6)
    interfaces = run_fixed(['/sbin/ifconfig', '-a'])
    if interfaces is not None:
        raw['ipv4_interface_count'] = len(re.findall(r'(?m)^\s+inet\s', interfaces))
        raw['ipv6_interface_count'] = len(re.findall(r'(?m)^\s+inet6\s', interfaces))
        raw['tunnel_interface_count'] = len(re.findall(r'(?m)^utun\d+:', interfaces))
    for key, argv in [('auto_time_enabled', ['/usr/sbin/systemsetup', '-getusingnetworktime']),
                      ('auto_timezone_enabled', ['/usr/bin/defaults', 'read', '/Library/Preferences/com.apple.timezone.auto', 'Active'])]:
        value = run_fixed(argv)
        if value in ('1', '0'):
            raw[key] = value == '1'
        elif value and value.lower().endswith((': on', ': off')):
            raw[key] = value.lower().endswith(': on')
    return project_native(raw)


def windows_native():
    root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    executable = root / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = Path(__file__).with_name('collect_windows.ps1')
    if not executable.is_file() or not script.is_file():
        return project_native({})
    # No ExecutionPolicy override, profile load, downloads, or user-supplied command strings.
    output = run_fixed([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(script)], timeout=25)
    if output is None:
        return project_native({})
    try:
        return project_native(load_json(output.encode('utf-8')))
    except SetupError:
        return project_native({})


def browser_preferences(path):
    data = load_json(read_bytes(path))
    require(isinstance(data, dict), 'BROWSER_PREFERENCES_OBJECT_REQUIRED')
    intl = data.get('intl') if isinstance(data.get('intl'), dict) else {}
    dns = data.get('dns_over_https') if isinstance(data.get('dns_over_https'), dict) else {}
    rtc = data.get('webrtc') if isinstance(data.get('webrtc'), dict) else {}
    return {'languages': languages(intl.get('accept_languages')),
            'app_locale': language(intl.get('app_locale')),
            'doh_mode': dns.get('mode') if dns.get('mode') in ('off', 'automatic', 'secure') else 'unknown',
            'webrtc_policy': rtc.get('ip_handling_policy') if rtc.get('ip_handling_policy') in (
                'default', 'default_public_and_private_interfaces', 'default_public_interface_only',
                'disable_non_proxied_udp') else 'unknown',
            'evidence': 'supplied_file_not_effective_browser_policy'}


def reject_nonfinite(value, depth=0, budget=None):
    """Keep parse complexity bounded and canonicalization deterministic."""
    budget = [0] if budget is None else budget
    budget[0] += 1
    require(depth <= 40 and budget[0] <= 50000, 'CONFIG_TOO_COMPLEX')
    if isinstance(value, dict):
        for key, child in value.items():
            require(isinstance(key, str), 'STRING_KEYS_REQUIRED')
            reject_nonfinite(child, depth + 1, budget)
    elif isinstance(value, list):
        for child in value:
            reject_nonfinite(child, depth + 1, budget)
    else:
        require(value is None or type(value) in (str, int, float, bool), 'UNSUPPORTED_VALUE')
        if type(value) is float:
            import math
            require(math.isfinite(value), 'INVALID_NUMBER')


def parse_config(data, fmt):
    text = decode(data)
    try:
        if fmt == 'json':
            parsed = load_json(data)
        elif fmt == 'yaml':
            try:
                import yaml
            except ImportError:
                raise SetupError('YAML_DEPENDENCY_MISSING') from None
            # Reject YAML aliases/anchors rather than expand shared or recursive structures.
            for event in yaml.parse(text):
                require(not isinstance(event, yaml.AliasEvent) and not getattr(event, 'anchor', None), 'YAML_ANCHORS_UNSUPPORTED')
            class StrictLoader(yaml.SafeLoader):
                pass
            def mapping(loader, node):
                pairs = []
                for key, value in node.value:
                    require(key.tag != 'tag:yaml.org,2002:merge', 'YAML_MERGE_UNSUPPORTED')
                    k = loader.construct_object(key, deep=True)
                    require(isinstance(k, str), 'STRING_KEYS_REQUIRED')
                    pairs.append((k, loader.construct_object(value, deep=True)))
                return unique_pairs(pairs)
            StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
            parsed = yaml.load(text, Loader=StrictLoader)
        elif fmt == 'shadowrocket':
            parsed = {}
            section = None
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith(('#', ';', '//')):
                    continue
                match = re.fullmatch(r'\[([^\]\r\n]+)\]', line)
                if match:
                    section = match.group(1).lower()
                    require(section not in parsed, 'DUPLICATE_SECTION')
                    parsed[section] = []
                else:
                    require(section is not None, 'SECTION_REQUIRED')
                    parsed[section].append(line)
            require(bool(parsed), 'EMPTY_CONFIG')
        else:
            raise SetupError('UNSUPPORTED_FORMAT')
        require(isinstance(parsed, dict), 'CONFIG_OBJECT_REQUIRED')
        reject_nonfinite(parsed)
        return parsed
    except SetupError:
        raise
    except Exception:
        # Parsing errors often contain the whole line, potentially including credentials.
        raise SetupError('INVALID_CONFIG') from None


def config_format(path, requested):
    if requested != 'auto':
        return requested
    suffix = Path(path).suffix.lower()
    require(suffix in ('.json', '.yaml', '.yml', '.conf'), 'FORMAT_REQUIRED')
    return {'.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.conf': 'shadowrocket'}[suffix]


def config_summary(data, fmt):
    obj = parse_config(data, fmt)
    raw_groups = []
    rules = []
    proxies = []
    provider_names = set()
    rule_provider_names = set()
    general = {}
    if fmt == 'shadowrocket':
        for line in obj.get('proxy', []):
            require('=' in line, 'INVALID_PROXY_DECLARATION')
            proxies.append(line.split('=', 1)[0].strip())
        for line in obj.get('proxy group', []):
            require('=' in line, 'INVALID_GROUP_DECLARATION')
            name, rest = line.split('=', 1)
            parts = [s.strip() for s in rest.split(',')]
            raw_groups.append({'name': name.strip(), 'proxies': [s for s in parts[1:] if '=' not in s]})
        rules = obj.get('rule', [])
        for line in obj.get('general', []):
            if '=' in line:
                key, value = line.split('=', 1)
                general[key.strip()] = value.strip().lower()
        scripts = bool(obj.get('script'))
        rewrites = any(bool(obj.get(k)) for k in ('url rewrite', 'header rewrite', 'body rewrite', 'map local'))
        mitm = bool(obj.get('mitm'))
        tls_disabled = any(re.search(r'(?:skip-cert-verify|skip-cert-verification)\s*=\s*true', x, re.I)
                           for lines in obj.values() for x in lines)
        dns_enabled, dns_ipv6, tun_enabled = None, (general.get('ipv6') == 'true' if general.get('ipv6') in ('true', 'false') else None), None
        mode = 'unknown'
        kind = 'shadowrocket_config'
    else:
        raw_proxies = obj.get('proxies', [])
        require(isinstance(raw_proxies, list), 'INVALID_PROXY_DECLARATION')
        for p in raw_proxies:
            require(isinstance(p, dict) and isinstance(p.get('name'), str), 'INVALID_PROXY_DECLARATION')
            proxies.append(p['name'])
        raw_groups = obj.get('proxy-groups', [])
        require(isinstance(raw_groups, list) and all(isinstance(x, dict) for x in raw_groups), 'INVALID_GROUP_DECLARATION')
        rules = obj.get('rules', [])
        require(isinstance(rules, list), 'RULE_LIST_REQUIRED')
        if any(k in obj for k in ('prepend', 'append', 'delete')):
            require(all(isinstance(obj.get(k, []), list) for k in ('prepend', 'append', 'delete')), 'RULE_LIST_REQUIRED')
            rules = obj.get('prepend', []) + obj.get('append', []) + obj.get('delete', [])
            kind = 'rules_extension'
        else:
            kind = 'profile_or_fragment'
        providers = obj.get('proxy-providers', {})
        require(isinstance(providers, dict), 'INVALID_PROVIDER_DECLARATION')
        provider_names = set(providers)
        rule_providers = obj.get('rule-providers', {})
        require(isinstance(rule_providers, dict), 'INVALID_RULE_PROVIDER_DECLARATION')
        rule_provider_names = set(rule_providers)
        scripts = any(k in obj for k in ('script', 'scripts'))
        rewrites = any(k in obj for k in ('rewrite', 'rewrites'))
        mitm = 'mitm' in obj
        def insecure(item):
            if isinstance(item, dict):
                return item.get('skip-cert-verify') is True or any(insecure(v) for v in item.values())
            return isinstance(item, list) and any(insecure(v) for v in item)
        tls_disabled = insecure(obj)
        dns = obj.get('dns') if isinstance(obj.get('dns'), dict) else {}
        tun = obj.get('tun') if isinstance(obj.get('tun'), dict) else {}
        dns_enabled, dns_ipv6, tun_enabled = boolean(dns.get('enable')), boolean(dns.get('ipv6')), boolean(tun.get('enable'))
        mode = obj.get('mode') if obj.get('mode') in ('rule', 'global', 'direct') else 'unknown'
    names = proxies[:]
    for group in raw_groups:
        require(isinstance(group.get('name'), str), 'INVALID_GROUP_DECLARATION')
        names.append(group['name'])
    known = set(names) | BUILTINS
    unknown = 0
    edges = {}
    for group in raw_groups:
        refs, providers = group.get('proxies', []), group.get('use', [])
        require(isinstance(refs, list) and all(isinstance(x, str) for x in refs), 'INVALID_GROUP_REFERENCE')
        require(isinstance(providers, list) and all(isinstance(x, str) for x in providers), 'INVALID_PROVIDER_REFERENCE')
        unknown += sum(x not in known for x in refs) + sum(x not in provider_names for x in providers)
        edges[group['name']] = refs
    cyclic = 0
    memo = {}
    def visit(name, stack):
        if name in stack:
            return True
        if name in memo:
            return memo[name]
        require(len(stack) < 100, 'GROUP_GRAPH_TOO_COMPLEX')
        memo[name] = any(visit(child, stack | {name}) for child in edges.get(name, []) if child in edges)
        return memo[name]
    for name in edges:
        cyclic += int(visit(name, set()))
    after = unsupported = external_sources = 0
    catchall = False
    for line in rules:
        require(isinstance(line, str), 'RULE_STRING_REQUIRED')
        parts = [p.strip() for p in line.split(',')]
        if catchall:
            after += 1
        if not parts or parts[0].upper() not in RULE_TYPES:
            unsupported += 1
            continue
        require(len(parts) >= (2 if parts[0].upper() in ('MATCH', 'FINAL') else 3), 'INVALID_RULE')
        action = parts[-2] if parts[-1].lower() == 'no-resolve' else parts[-1]
        unknown += action not in known
        if parts[0].upper() == 'RULE-SET':
            if fmt == 'shadowrocket':
                external_sources += 1
            else:
                unknown += parts[1] not in rule_provider_names
        catchall = catchall or parts[0].upper() in ('MATCH', 'FINAL')
    return {'kind': kind, 'parse_status': 'parsed_not_core_validated', 'proxy_count': len(proxies),
            'group_count': len(raw_groups), 'rule_count': len(rules), 'external_rule_source_count': external_sources, 'unknown_references': unknown,
            'duplicate_names': len(names) - len(set(names)), 'cyclic_groups': cyclic,
            'rules_after_catchall': after, 'unsupported_rule_count': unsupported,
            'scripts_present': scripts, 'rewrite_present': rewrites, 'mitm_present': mitm, 'tls_verification_disabled': tls_disabled,
            'dns_enabled': dns_enabled, 'dns_ipv6': dns_ipv6, 'tun_enabled': tun_enabled, 'mode': mode}


def canonical_hash(data, fmt):
    return sha(encode(parse_config(data, fmt)))


def collect(config=None, fmt='auto', preferences=None, target='local-machine'):
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,32}', target), 'NONIDENTIFYING_TARGET_ALIAS_REQUIRED')
    system = platform.system()
    family = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}.get(system, 'unknown')
    if family == 'linux' and ('microsoft' in platform.release().lower() or os.environ.get('WSL_DISTRO_NAME')):
        family = 'wsl'
    native = mac_native() if family == 'macos' else windows_native() if family == 'windows' else project_native({})
    result = {'schema': 'claude-setup-collection/1', 'tool_version': VERSION, 'collected_at': now(),
              'target_alias': target, 'platform': family, 'native': native,
              'environment': {k: ('absent' if k not in os.environ else 'empty' if not os.environ[k] else 'present') for k in ENV_KEYS},
              'claude_command_found': shutil.which('claude') is not None,
              'config': None, 'config_error': None, 'browser': None, 'browser_error': None,
              'network_requests': 0, 'evidence': 'local_metadata_and_optional_static_files'}
    if config:
        try:
            result['config'] = config_summary(read_bytes(config), config_format(config, fmt))
        except SetupError as exc:
            result['config_error'] = str(exc)
    if preferences:
        try:
            result['browser'] = browser_preferences(preferences)
        except SetupError as exc:
            result['browser_error'] = str(exc)
    return result


def validate_collection(raw):
    """Re-project imported records; report never renders arbitrary extra fields."""
    require(isinstance(raw, dict) and raw.get('schema') == 'claude-setup-collection/1', 'COLLECTION_SCHEMA_REQUIRED')
    require(raw.get('platform') in ('macos', 'windows', 'linux', 'wsl', 'unknown'), 'INVALID_COLLECTION')
    stamp = raw.get('collected_at')
    require(isinstance(stamp, str) and len(stamp) <= 40, 'INVALID_COLLECTION')
    try:
        require(dt.datetime.fromisoformat(stamp).tzinfo is not None, 'INVALID_COLLECTION')
    except ValueError:
        raise SetupError('INVALID_COLLECTION') from None
    target = raw.get('target_alias')
    require(isinstance(target, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,32}', target), 'INVALID_COLLECTION')
    result = {'collected_at': stamp, 'target_alias': target, 'platform': raw['platform'],
              'native': project_native(raw.get('native')), 'environment': {}, 'config': None,
              'browser': None, 'claude_command_found': boolean(raw.get('claude_command_found')),
              'evidence': raw.get('evidence') if raw.get('evidence') in ('local_metadata_and_optional_static_files', 'synthetic_fixture') else 'unverified_import'}
    env = raw.get('environment') if isinstance(raw.get('environment'), dict) else {}
    for key in ENV_KEYS:
        result['environment'][key] = env.get(key) if env.get(key) in ('absent', 'empty', 'present') else 'unknown'
    cfg = raw.get('config')
    if isinstance(cfg, dict):
        projected = {}
        for key in CONFIG_KEYS:
            v = cfg.get(key)
            if key in ('kind', 'parse_status', 'mode'):
                allowed = {'kind': ('shadowrocket_config', 'rules_extension', 'profile_or_fragment'),
                           'parse_status': ('parsed_not_core_validated',), 'mode': ('rule', 'global', 'direct', 'unknown')}[key]
                projected[key] = v if v in allowed else 'unknown'
            elif key.endswith('_count') or key in ('unknown_references', 'duplicate_names', 'cyclic_groups', 'rules_after_catchall'):
                projected[key] = count(v)
            else:
                projected[key] = boolean(v)
        result['config'] = projected
    browser = raw.get('browser')
    if isinstance(browser, dict):
        result['browser'] = {'languages': languages(browser.get('languages')), 'app_locale': language(browser.get('app_locale')),
                             'doh_mode': browser.get('doh_mode') if browser.get('doh_mode') in ('off', 'automatic', 'secure') else 'unknown',
                             'webrtc_policy': browser.get('webrtc_policy') if browser.get('webrtc_policy') in ('default', 'default_public_and_private_interfaces', 'default_public_interface_only', 'disable_non_proxied_udp') else 'unknown'}
    return result


def collection_rows(raw):
    data = validate_collection(raw)
    native = data['native']
    def show(value):
        if value is None:
            return '未知'
        if type(value) is bool:
            return '是' if value else '否'
        if isinstance(value, list):
            return '、'.join(value) if value else '未知'
        return str(value)
    labels = {'system_version':'系统版本', 'timezone':'时区', 'auto_time_enabled':'自动校时',
              'auto_timezone_enabled':'自动时区', 'time_service_running':'时间服务运行',
              'system_locale':'系统区域格式', 'ui_locale':'系统界面语言', 'languages':'语言列表',
              'http_proxy_enabled':'HTTP／手动代理开关', 'https_proxy_enabled':'HTTPS代理开关',
              'socks_proxy_enabled':'SOCKS代理开关', 'pac_present':'PAC配置存在',
              'dns_v4_count':'IPv4 DNS条目数', 'dns_v6_count':'IPv6 DNS条目数',
              'ipv4_interface_count':'IPv4地址／接口条目', 'ipv6_interface_count':'IPv6地址／接口条目',
              'tunnel_interface_count':'隧道接口数', 'proxy_count':'节点数', 'group_count':'策略组数',
              'rule_count':'规则数', 'external_rule_source_count':'未读取的外部规则来源数', 'unknown_references':'待核对引用数', 'duplicate_names':'重复名称数',
              'cyclic_groups':'涉及循环的组数', 'rules_after_catchall':'兜底后规则数',
              'unsupported_rule_count':'未支持的规则数', 'scripts_present':'脚本配置存在',
              'rewrite_present':'内容改写配置存在', 'mitm_present':'MITM配置存在',
              'tls_verification_disabled':'发现关闭TLS验证', 'dns_enabled':'配置DNS启用',
              'dns_ipv6':'配置DNS解析IPv6', 'tun_enabled':'配置TUN启用', 'mode':'配置路由模式',
              'kind':'配置类别', 'parse_status':'解析层级', 'app_locale':'应用语言',
              'doh_mode':'安全DNS模式', 'webrtc_policy':'WebRTC策略'}
    rows = []
    for name, keys, caveat in (
        ('系统／时间', ('system_version', 'timezone', 'auto_time_enabled', 'auto_timezone_enabled', 'time_service_running'), '本机设置；未验证时钟同步精度。'),
        ('系统语言', ('system_locale', 'ui_locale', 'languages'), '系统设置；不代表浏览器菜单或网页语言。'),
        ('系统代理', ('http_proxy_enabled', 'https_proxy_enabled', 'socks_proxy_enabled', 'pac_present'), '未验证目标进程采用、PAC 内容或出站。'),
        ('系统 DNS', ('dns_v4_count', 'dns_v6_count'), '仅服务器地址条目计数；没有发起 DNS 查询。'),
        ('接口地址族', ('ipv4_interface_count', 'ipv6_interface_count', 'tunnel_interface_count'), '包含虚拟／回环接口；不是出口或 TUN 接管证明。')):
        observed = any(native[k] not in (None, []) for k in keys)
        rows.append((name, '已读取局部状态' if observed else '未取得状态', '；'.join(labels[k] + '：' + show(native[k]) for k in keys), caveat))
    presence = {'absent':'不存在', 'empty':'空值', 'present':'已设置', 'unknown':'未知'}
    rows.append(('认证／代理变量', '当前进程存在状态', '；'.join(k + '：' + presence[v] for k, v in data['environment'].items()), '只说明采集器环境，不代表已运行 Desktop／CLI；不输出变量值。'))
    rows.append(('Claude 命令', '只读发现', show(data['claude_command_found']), '仅 PATH 中发现入口；没有执行 Claude、登录或模型请求。'))
    if data['config'] is not None:
        cfg = data['config']
        problem = any((cfg.get(k) or 0) > 0 for k in ('duplicate_names', 'cyclic_groups', 'rules_after_catchall'))
        rows.append(('指定配置文件', '发现静态问题' if problem else '已做静态检查', '；'.join(labels[k] + '：' + show(v) for k, v in sorted(cfg.items())), '解析不代表核心兼容或已加载；引用可能来自外部节点／扩展，需现场核实。'))
    else:
        rows.append(('指定配置文件', '未验证', '未提供或无法解析', '查看 collection.json 中固定错误码；不得推断当前活动配置。'))
    for title in ('Claude／OpenAI 专属代理', 'AI 代理失败不回落直连'):
        rows.append((title, '未验证', '采集未验证 AI 实际规则命中或故障路径', '候选与静态审计不能代替客户端载入、真实请求及故障演练。'))
    if data['browser'] is not None:
        rows.append(('指定浏览器偏好文件', '静态文件', '；'.join(labels[k] + '：' + show(v) for k, v in data['browser'].items()), '非运行中 Profile／组织策略证明；未读取 Cookie／账号数据。'))
    else:
        rows.append(('浏览器偏好', '未验证', '未提供或无法解析', '在客户实际浏览器检查菜单语言、网页语言与有效政策。'))
    for title in ('DNS TYPE64／65 与 DNS64', '公网 IPv4／IPv6 出口', 'WebRTC／STUN／UDP', '规则实际命中与客户端功能', '断线／重启／更新后保护'):
        rows.append((title, '未执行', '本工具未做主动网络或故障测试', '按现场清单取得相应批准后单独验证。'))
    for title in ('更新后复查', '主动网络验证', '启动前检查'):
        rows.append((title, '未验证', '尚未执行本轮对应检查', '按生命周期流程读取当前基线、运行获准探测并检查本次结果。'))
    return data, rows


REPORT_TASKS = (
    ('system_time', '时间与时区', '尚未核对时间准确性及客户需要的时区。', '核对现状并问客户是否需要调整；需要修改时说明目标、影响和恢复办法，确认后修改并复测。'),
    ('system_language', '系统语言与地区', '尚未确认当前语言和地区格式是否符合客户需要。', '展示当前设置，询问是否保留；若要调整，按客户选定目标修改后检查显示和格式。'),
    ('system_proxy', '代理与接管', '只读取了代理开关，尚未验证实际接管范围。', '确认客户需要的分流范围；调整系统代理或 TUN 前逐项询问，随后验证目标程序路径。'),
    ('system_dns', '系统与代理 DNS', '只读取了 DNS 设置，实际解析路径尚未验证。', '核对系统、代理和浏览器解析责任；需要调整哪一层先问客户，获准后复测。'),
    ('ip_families', 'IPv4／IPv6', '接口信息不能证明实际出口和 IPv6 行为。', '在获准范围分别验证地址族与代理各段，确需调整 IPv6 时先说明范围并询问。'),
    ('auth_environment', '认证与代理来源', '变量存在状态不能证明 Claude 实际采用了哪种认证和代理。', '核对实际启动入口与认证来源；只改已确认有问题且客户批准的设置，随后复测。'),
    ('claude_command', 'Claude Code 使用', '找到命令入口不等于安装、认证和实际使用已验证。', '按客户实际需要核对 Code；安装或调整前询问，获准后验证真实任务。'),
    ('config', '配置导入与生效', '尚未验证配置已导入、载入并按预期生效。', '先审阅静态提示，逐项询问是否应用候选；确认后保存／导入，读回并验证实际规则命中。'),
    ('ai_policy', 'Claude／OpenAI 专属代理', '尚未核对指定节点、专属规则载入和实际命中；静态候选不代表生效。', '按专属代理流程准备候选，按所选模式确认后导入、读回并验证两家实际使用的功能及原有国内外分流。'),
    ('ai_failure', 'AI 代理失败不回落直连', '尚未在目标机验证指定代理失效后的流量路径。', '先确认具体故障演练及恢复办法；获准后结合规则日志和流量证据验证没有直连或换节点，恢复并复测。'),
    ('browser', '浏览器设置', '尚未核对实际浏览器档案中的语言和有效策略。', '在客户实际浏览器检查；语言、代理或策略调整分别问客户，再读回并复测。'),
    ('dns_records', 'DNS TYPE64／65 与 DNS64', '尚未执行适用的查询与功能检查。', '先确认本次是否需要检测；获准后验证实际行为，过滤设置要单独说明影响并询问。'),
    ('public_egress', '公网出口', '尚未取得本次目标程序的出口结果。', '告知检测站点及数据范围，客户同意后检测并与约定路径比较。'),
    ('webrtc', 'WebRTC／STUN／UDP', '尚未完成实际浏览器的相关检测。', '获准后在实际档案中检测；需要限制相关功能时询问客户，并复测通话／共享需求。'),
    ('client_function', '客户端实际使用', '尚未验证客户需要的网页、Desktop 或 Code 功能。', '逐个验证实际使用的客户端和必要功能；无关客户端由客户确认后不计入。'),
    ('lifecycle', '自启、更新与故障恢复', '尚未完成本次需要的持久化和恢复检查。', '先问客户需要哪些场景；断网／重启实验另行确认并准备独立恢复方法，完成后检查网络恢复。'),
    ('update_recheck', '更新后复查', '尚未比较更新后的实际配置、客户端和系统设置。', '读取已确认基线运行 recheck，审阅变化；不自动覆盖客户后续修改。'),
    ('active_network', '主动网络验证', '尚未完成本轮明确范围内的主动探测。', '先展示探测目标与数据流，获准后运行 network-check；超时或无响应保持未完成。'),
    ('startup_check', '启动前检查', '尚未运行本次启动所需的新鲜检查。', '运行 preflight；必需项未完成则不启动，启动请求成功后另验实际客户端。'),
)


def safe_review_text(value):
    require(isinstance(value, str) and 0 < len(value.strip()) <= 600, 'REVIEW_NOTE_REQUIRED')
    value = value.strip()
    require(not any(ord(c) < 32 and c not in '\n\t' for c in value), 'INVALID_REVIEW_NOTE')
    # A convenience guard, not a general data-loss-prevention guarantee. Review notes locally.
    patterns = (r'https?://', r'(?i)(?:sk-|ghp_|github_pat_|Bearer\s)\S+',
                r'(?i)(?:password|token|secret|uuid)\s*[:=]', r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',
                r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r'(?:/[Uu]sers/|/home/|[A-Za-z]:\\)',
                r'(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')
    require(not any(re.search(pattern, value) for pattern in patterns), 'REVIEW_NOTE_NEEDS_REDACTION')
    for candidate in re.findall(r'[A-Fa-f0-9:]{3,}(?:%[A-Za-z0-9]+)?', value):
        if candidate.count(':') < 2:
            continue
        try:
            address = ipaddress.ip_address(candidate.split('%')[0])
        except ValueError:
            continue
        require(address.version != 6, 'REVIEW_NOTE_NEEDS_REDACTION')
    return value


def review_template(raw, collection_digest):
    data = validate_collection(raw)
    require(re.fullmatch(r'[0-9a-f]{64}', collection_digest or ''), 'COLLECTION_DIGEST_REQUIRED')
    return {'schema': 'claude-setup-review/1', 'target_alias': data['target_alias'],
            'collection_sha256': collection_digest, 'items': [
                {'id': key, 'applicable': True, 'scope_confirmed': False,
                 'status': 'incomplete', 'change': 'none', 'decision': 'pending',
                 'verified': False, 'verified_at': '', 'evidence': '',
                 'reason': reason, 'next_step': action}
                for key, _, reason, action in REPORT_TASKS]}


def validate_review(review, data, collection_digest):
    require(isinstance(review, dict) and review.get('schema') == 'claude-setup-review/1', 'REVIEW_SCHEMA_REQUIRED')
    require(collection_digest and review.get('collection_sha256') == collection_digest, 'REVIEW_COLLECTION_MISMATCH')
    require(review.get('target_alias') == data['target_alias'], 'REVIEW_TARGET_MISMATCH')
    items = review.get('items')
    require(isinstance(items, list) and len(items) <= len(REPORT_TASKS), 'INVALID_REVIEW_ITEMS')
    known = {row[0] for row in REPORT_TASKS}
    result = {}
    for item in items:
        require(isinstance(item, dict), 'INVALID_REVIEW_ITEM')
        key = item.get('id')
        require(isinstance(key, str) and key in known and key not in result, 'INVALID_OR_DUPLICATE_TASK')
        require(type(item.get('applicable')) is bool, 'REVIEW_APPLICABILITY_REQUIRED')
        if not item['applicable']:
            require(item.get('scope_confirmed') is True, 'SCOPE_CONFIRMATION_REQUIRED')
            require(item.get('change', 'none') != 'applied', 'CHANGED_TASK_CANNOT_BE_EXCLUDED')
            result[key] = {'applicable': False, 'reason': safe_review_text(item.get('reason'))}
            continue
        state, change, decision = item.get('status'), item.get('change'), item.get('decision')
        require(state in ('completed', 'incomplete'), 'BINARY_STATUS_REQUIRED')
        require(change in ('none', 'proposed', 'applied'), 'INVALID_CHANGE_STATE')
        require(decision in ('pending', 'approved', 'declined', 'not_required'), 'INVALID_CUSTOMER_DECISION')
        require(type(item.get('verified')) is bool, 'VERIFICATION_STATE_REQUIRED')
        require(change != 'applied' or decision == 'approved', 'APPLIED_CHANGE_APPROVAL_REQUIRED')
        # An imported decision records history; it never authorizes this tool to act.
        if state == 'completed':
            require(item['verified'] and change != 'proposed', 'COMPLETION_EVIDENCE_REQUIRED')
            require(decision in ('approved', 'not_required'), 'CUSTOMER_DECISION_UNRESOLVED')
            evidence = safe_review_text(item.get('evidence'))
            stamp = item.get('verified_at')
            require(isinstance(stamp, str) and len(stamp) <= 40, 'VERIFICATION_TIME_REQUIRED')
            try:
                verified = dt.datetime.fromisoformat(stamp)
                require(verified.tzinfo is not None and dt.datetime.fromisoformat(data['collected_at']) <= verified <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5), 'INVALID_VERIFICATION_TIME')
            except ValueError:
                raise SetupError('INVALID_VERIFICATION_TIME') from None
            result[key] = {'applicable': True, 'status': '已完成', 'reason': evidence,
                           'next_step': '本项已完成；目标、配置或使用方式变化后复核。', 'verified_at': stamp}
        else:
            decision_note = {'declined': '客户选择暂不修改。', 'pending': '客户决定尚未记录。',
                             'approved': '客户已同意所列具体修改。', 'not_required': '本项无需修改。'}[decision]
            result[key] = {'applicable': True, 'status': '未完成',
                           'reason': decision_note + safe_review_text(item.get('reason')),
                           'next_step': safe_review_text(item.get('next_step'))}
    return result


def report_rows(raw, review=None, collection_digest=None):
    data, observations = collection_rows(raw)
    entries = validate_review(review, data, collection_digest) if review is not None else {}
    rows, excluded = [], []
    for index, (key, title, reason, action) in enumerate(REPORT_TASKS):
        entry = entries.get(key)
        if entry and not entry['applicable']:
            excluded.append({'title': title, 'reason': entry['reason']})
            continue
        row = {'id': key, 'title': title, 'status': '未完成', 'reason': reason,
               'next_step': action, 'observation': observations[index][2]}
        if entry:
            row.update({k: entry[k] for k in ('status', 'reason', 'next_step')})
        elif key == 'config' and data['config']:
            issues = data['config']
            if any((issues.get(k) or 0) > 0 for k in ('duplicate_names', 'cyclic_groups', 'rules_after_catchall', 'unknown_references')):
                row['reason'] = '配置存在重复名称、循环、规则顺序或待核对引用提示，尚未处理并复测。'
        rows.append(row)
    rows.sort(key=lambda row: row['status'] == '已完成')
    data['excluded'] = excluded
    return data, rows


def render_report(raw, output, review=None, collection_digest=None):
    data, rows = report_rows(raw, review, collection_digest)
    source_label = {'local_metadata_and_optional_static_files': '本机采集及可选静态文件',
                    'synthetic_fixture': '合成示例', 'unverified_import': '导入资料，来源需核对'}[data['evidence']]
    stamp = dt.datetime.fromisoformat(data['collected_at']).astimezone().isoformat(timespec='seconds')
    summary = f"目标别名：{data['target_alias']} · 执行平台：{data['platform']} · 采集时间：{stamp} · 来源：{source_label}"
    if data['evidence'] == 'synthetic_fixture':
        summary = '合成示例（非设备实测） · ' + summary
    completed = sum(row['status'] == '已完成' for row in rows)
    progress = f'已完成 {completed} 项／共 {len(rows)} 项，未完成 {len(rows) - completed} 项'
    caveat = '已完成表示该项按本次范围完成检查和必要处理，并有操作者填写的验证记录；不代表账号安全保证。单纯采集设置不会自动标为已完成。修改前应逐项询问客户。'
    md = '# Claude 环境检查报告\n\n' + progress + '\n\n' + summary + '\n\n' + caveat + '\n\n| 检查项 | 状态 | 结果／未完成原因 | 下一步 |\n| --- | --- | --- | --- |\n'
    def md_text(value):
        # Preserve plain-text notes; never turn imported Markdown into executable/linked markup.
        value = html.escape(str(value)).replace('\n', ' ').replace('\t', ' ')
        return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', value)
    for row in rows:
        md += '| ' + ' | '.join(md_text(row[k]) for k in ('title', 'status', 'reason', 'next_step')) + ' |\n'
    excluded = ''
    if data['excluded']:
        md += '\n不计入本次清单（已确认范围）：\n\n'
        for item in data['excluded']:
            md += '- ' + md_text(item['title'] + '：' + item['reason']) + '\n'
        excluded = '<p>不计入本次清单（已确认范围）：</p><ul>' + ''.join('<li>' + html.escape(x['title'] + '：' + x['reason']) + '</li>' for x in data['excluded']) + '</ul>'
    md += '\n## 原始采集信息\n\n'
    md += '\n'.join('- ' + md_text(row['title'] + '：' + row['observation']) for row in rows) + '\n'
    table = ''.join('<tr><td>' + html.escape(row['title']) + '</td><td class="' + ('done' if row['status'] == '已完成' else 'todo') + '">' + row['status'] + '</td><td>' + html.escape(row['reason']) + '</td><td>' + html.escape(row['next_step']) + '</td></tr>' for row in rows)
    details = '<details><summary>查看原始采集信息</summary><ul>' + ''.join('<li>' + html.escape(row['title'] + '：' + row['observation']) + '</li>' for row in rows) + '</ul></details>'
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Claude 环境检查报告</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#162334;background:#fafafa}h1{font-size:28px}.progress{font-size:22px;font-weight:650;padding:16px;background:#edf2f8;border-radius:8px}table{border-collapse:collapse;table-layout:fixed;width:100%;background:white}td,th{text-align:left;vertical-align:top;padding:14px;border:1px solid #dce1e8;overflow-wrap:anywhere}th{background:#edf2f8}th:nth-child(1){width:17%}th:nth-child(2){width:10%}th:nth-child(3){width:32%}th:nth-child(4){width:41%}.done{color:#176444;font-weight:650}.todo{color:#9a4e12;font-weight:650}p,details{color:#465569}details{margin-top:24px}summary{cursor:pointer}@media(max-width:700px){body{padding:0 10px;font-size:13px}td,th{padding:8px}}@media print{body{margin:0;font-size:11px}tr{break-inside:avoid}}</style><h1>Claude 环境检查报告</h1><p class="progress">' + html.escape(progress) + '</p><p>' + html.escape(summary) + '</p><p>' + html.escape(caveat) + '</p><table><thead><tr><th>检查项</th><th>状态</th><th>结果／未完成原因</th><th>下一步</th></tr></thead><tbody>' + table + '</tbody></table>' + excluded + details + '</html>'
    new_dir(output)
    write_new(Path(output) / 'report.md', md.encode('utf-8'))
    write_new(Path(output) / 'report.html', page.encode('utf-8'))


def prepare_plan(current, candidate, fmt, output):
    current, candidate = Path(current), Path(candidate)
    require(current.resolve() != candidate.resolve(), 'DISTINCT_CANDIDATE_REQUIRED')
    before, after = read_bytes(current), read_bytes(candidate)
    fmt = config_format(current, fmt)
    before_info, after_info = config_summary(before, fmt), config_summary(after, fmt)
    # No parsing failure or unsupported YAML creates a partial plan directory.
    original_semantic, candidate_semantic = canonical_hash(before, fmt), canonical_hash(after, fmt)
    require(before != after, 'NO_CHANGE')
    plan = {'schema': 'claude-setup-plan/1', 'created_at': now(), 'format': fmt,
            'target_path': str(current.resolve()), 'original_sha256': sha(before),
            'candidate_sha256': sha(after), 'original_semantic_sha256': original_semantic,
            'candidate_semantic_sha256': candidate_semantic, 'candidate_summary': after_info,
            'application_loaded': 'not_verified', 'network_verified': False, 'apply_supported': False}
    changes = ''.join(difflib.unified_diff(decode(before).splitlines(keepends=True), decode(after).splitlines(keepends=True),
                                         fromfile='original', tofile='candidate'))
    new_dir(output)
    dest = Path(output)
    write_new(dest / 'original.bin', before)
    write_new(dest / 'candidate.bin', after)
    write_new(dest / 'diff.private.txt', changes.encode('utf-8'))
    write_new(dest / 'plan.json', encode(plan))
    write_new(dest / 'plan.sha256', (sha(encode(plan)) + '\n').encode())
    # Structural summary never includes rule text, proxy names, domain names or secrets.
    summary = {'schema': 'claude-setup-plan-summary/1', 'changes': {
        key: {'before': before_info[key], 'candidate': after_info[key]}
        for key in sorted(CONFIG_KEYS) if before_info[key] != after_info[key]},
        'content_changed': True, 'semantic_changed': original_semantic != candidate_semantic,
        'private_files_contain_configuration': True, 'application_loaded': 'not_verified', 'apply_supported': False}
    write_new(dest / 'summary.json', encode(summary))
    return summary


def verify_readback(plan_dir, target, exported=False):
    directory = Path(plan_dir)
    plan_bytes = read_bytes(directory / 'plan.json', 65536)
    expected = decode(read_bytes(directory / 'plan.sha256', 128)).strip()
    require(re.fullmatch(r'[0-9a-f]{64}', expected) and sha(plan_bytes) == expected, 'PLAN_INTEGRITY_MISMATCH')
    plan = load_json(plan_bytes)
    require(isinstance(plan, dict) and plan.get('schema') == 'claude-setup-plan/1', 'PLAN_SCHEMA_REQUIRED')
    fmt = plan.get('format')
    require(fmt in ('json', 'yaml', 'shadowrocket'), 'INVALID_PLAN')
    # The caller always supplies the actual read target; never follow paths from imported JSON.
    require(isinstance(plan.get('target_path'), str), 'INVALID_PLAN')
    if not exported:
        require(str(Path(target).resolve()) == plan['target_path'], 'TARGET_MISMATCH')
    original = read_bytes(directory / 'original.bin')
    candidate = read_bytes(directory / 'candidate.bin')
    require(sha(original) == plan.get('original_sha256') and sha(candidate) == plan.get('candidate_sha256'), 'SNAPSHOT_INTEGRITY_MISMATCH')
    require(canonical_hash(original, fmt) == plan.get('original_semantic_sha256') and canonical_hash(candidate, fmt) == plan.get('candidate_semantic_sha256'), 'SNAPSHOT_INTEGRITY_MISMATCH')
    actual = read_bytes(target)
    digest = sha(actual)
    if digest == plan['candidate_sha256']:
        status = 'candidate_bytes_match'
    elif digest == plan['original_sha256']:
        status = 'unchanged_original'
    else:
        try:
            same = canonical_hash(actual, fmt) == plan['candidate_semantic_sha256']
        except SetupError:
            same = False
        status = 'formatting_or_comments_changed_review_required' if same else 'unexpected_content_conflict'
    return {'schema': 'claude-setup-readback/1', 'checked_at': now(), 'status': status,
            'evidence': 'caller_supplied_export' if exported else 'reread_bound_target_file',
            'byte_comparison': 'match' if status == 'candidate_bytes_match' else 'not_match',
            'application_loaded': 'not_verified', 'process_adoption': 'not_verified',
            'network_verified': False, 'system_changes_performed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('collect', help='Read local metadata; no network requests or system changes')
    c.add_argument('--output', required=True)
    c.add_argument('--target-alias', default='local-machine')
    c.add_argument('--config')
    c.add_argument('--format', choices=('auto', 'json', 'yaml', 'shadowrocket'), default='auto')
    c.add_argument('--browser-preferences')
    r = sub.add_parser('report', help='Render an existing collection to offline HTML and Markdown')
    r.add_argument('--input', required=True)
    r.add_argument('--out', required=True)
    r.add_argument('--review', help='Operator verification records bound to this collection; not action authorization')
    rt = sub.add_parser('review-template', help='Create an incomplete-by-default customer review checklist')
    rt.add_argument('--input', required=True)
    rt.add_argument('--output', required=True)
    p = sub.add_parser('plan', help='Prepare private original/candidate snapshots and diff; never apply')
    p.add_argument('--current', required=True)
    p.add_argument('--candidate', required=True)
    p.add_argument('--format', choices=('auto', 'json', 'yaml', 'shadowrocket'), default='auto')
    p.add_argument('--out', required=True)
    v = sub.add_parser('verify', help='Read the explicitly supplied target again and compare with a plan')
    v.add_argument('--plan', required=True)
    v.add_argument('--target', required=True)
    v.add_argument('--exported-readback', action='store_true')
    v.add_argument('--output')
    for name in ('ai-route', 'ai-audit'):
        a = sub.add_parser(name, help='Prepare or audit private AI-only routing; never apply')
        a.add_argument('--config', required=True)
        a.add_argument('--format', choices=('auto', 'json', 'yaml', 'shadowrocket'), default='auto')
        a.add_argument('--node', required=True, help='Existing concrete proxy name, not a selector or DIRECT')
        a.add_argument('--group', default='AI-ONLY')
        if name == 'ai-route':
            a.add_argument('--out', required=True)
        else:
            a.add_argument('--baseline', required=True)
            a.add_argument('--output')
    np = sub.add_parser('network-plan', help='Create a reviewable probe plan; no network')
    np.add_argument('--proxy', required=True)
    np.add_argument('--output', required=True)
    nc = sub.add_parser('network-check', help='Run only explicitly approved, bounded probes')
    nc.add_argument('--plan', required=True)
    nc.add_argument('--allow-network', action='store_true')
    nc.add_argument('--out', required=True)
    for command in ('baseline', 'recheck', 'preflight'):
        lc = sub.add_parser(command, help='Private baseline, drift report or fresh startup checks')
        lc.add_argument('--config', required=True)
        lc.add_argument('--executable', required=True)
        lc.add_argument('--browser-preferences')
        lc.add_argument('--out', required=True)
        if command == 'baseline':
            lc.add_argument('--ai-original', required=True)
            lc.add_argument('--node', required=True)
            lc.add_argument('--group', default='AI-ONLY')
            lc.add_argument('--format', choices=('auto', 'json', 'yaml', 'shadowrocket'), default='auto')
        else:
            lc.add_argument('--baseline', required=True)
        if command == 'preflight':
            lc.add_argument('--network-plan', required=True)
            lc.add_argument('--allow-network', action='store_true')
            lc.add_argument('--launch', action='store_true', help='Request launch only if fresh required checks pass')
    args = parser.parse_args(argv)
    try:
        if args.command in ('network-plan', 'network-check', 'baseline', 'recheck', 'preflight'):
            import network_checks
            import readiness_lifecycle as lifecycle
            context = SimpleNamespace(**globals())
            if args.command == 'network-plan':
                value = network_checks.validate_plan(context, network_checks.template(args.proxy))
                write_new(args.output, encode(value))
                result = {'status': 'network_plan_written', 'network_requests': 0}
            elif args.command == 'network-check':
                value = network_checks.validate_plan(context, load_json(read_bytes(args.plan)))
                require(args.allow_network, 'EXPLICIT_NETWORK_OPT_IN_REQUIRED')
                new_dir(args.out)
                rows, private = network_checks.run_checks(context, value, args.allow_network)
                result = lifecycle.save_report(context, args.out, 'network', rows,
                    {'plan_sha256': sha(encode(value))}, private, create=False)
            elif args.command == 'baseline':
                result = lifecycle.create_baseline(context, args.config, args.format, args.ai_original,
                    args.node, args.group, args.executable, args.browser_preferences, args.out)
            elif args.command == 'recheck':
                rows, saved = lifecycle.recheck(context, args.baseline, args.config, args.executable, args.browser_preferences)
                result = lifecycle.save_report(context, args.out, 'recheck', rows)
            else:
                value = network_checks.validate_plan(context, load_json(read_bytes(args.network_plan)))
                require(args.allow_network, 'EXPLICIT_NETWORK_OPT_IN_REQUIRED')
                result = lifecycle.startup(context, args.baseline, args.config, args.executable,
                    args.browser_preferences, value, args.allow_network, args.launch, args.out)
        elif args.command in ('ai-route', 'ai-audit'):
            import ai_routing
            context = SimpleNamespace(**globals())
            if args.command == 'ai-route':
                result = ai_routing.prepare(context, args.config, args.format, args.node, args.out, args.group)
            else:
                fmt = config_format(args.config, args.format)
                result = ai_routing.audit(context, read_bytes(args.baseline), read_bytes(args.config), fmt, args.node, args.group)
                if args.output:
                    write_new(args.output, encode(result))
        elif args.command == 'collect':
            data = collect(args.config, args.format, args.browser_preferences, args.target_alias)
            write_new(args.output, encode(data))
            result = {'status': 'collection_written', 'network_requests': 0, 'system_changes_performed': False}
        elif args.command == 'report':
            source = read_bytes(args.input)
            review = load_json(read_bytes(args.review)) if args.review else None
            render_report(load_json(source), args.out, review, sha(source))
            result = {'status': 'report_written', 'environment_verified': False}
        elif args.command == 'review-template':
            source = read_bytes(args.input)
            write_new(args.output, encode(review_template(load_json(source), sha(source))))
            result = {'status': 'review_template_written', 'system_changes_performed': False}
        elif args.command == 'plan':
            result = prepare_plan(args.current, args.candidate, args.format, args.out)
        else:
            result = verify_readback(args.plan, args.target, args.exported_readback)
            if args.output:
                write_new(args.output, encode(result))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if args.command in ('network-check', 'recheck', 'preflight') and not result['required_checks_completed']:
            return 2
        if args.command == 'ai-audit' and result['status'] != 'static_policy_matches':
            return 2
        return 2 if args.command == 'verify' and result['status'] != 'candidate_bytes_match' else 0
    except SetupError as exc:
        print(json.dumps({'error': str(exc), 'system_changes_performed': False}), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print(json.dumps({'error': 'OPERATION_FAILED', 'system_changes_performed': False}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
