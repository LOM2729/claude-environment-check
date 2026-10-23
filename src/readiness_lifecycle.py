"""Explicit baselines, non-mutating drift review and fresh, opt-in startup checks."""
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import stat
import subprocess
import sys
from urllib.parse import urlsplit

import ai_routing
import network_checks

WATCHED = ('timezone', 'system_locale', 'ui_locale', 'languages', 'http_proxy_enabled',
           'https_proxy_enabled', 'socks_proxy_enabled', 'pac_present', 'dns_v4_count', 'dns_v6_count', 'ipv4_interface_count', 'ipv6_interface_count', 'tunnel_interface_count')


def file_hash(c, path):
    path = Path(path).absolute()
    before = path.lstat()
    c.require(stat.S_ISREG(before.st_mode) and before.st_size <= 1024 ** 3, 'CLIENT_REGULAR_FILE_REQUIRED')
    digest = hashlib.sha256()
    with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        c.require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino), 'CLIENT_CHANGED')
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.lstat()
    c.require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
              (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'CLIENT_CHANGED')
    return digest.hexdigest()


def client_identity(c, executable):
    path = Path(executable).absolute()
    c.require(path.is_absolute() and not path.is_symlink(), 'CLIENT_PATH_INVALID')
    binary = path
    metadata = None
    if path.suffix.lower() == '.app':
        c.require(platform.system() == 'Darwin' and path.is_dir(), 'MAC_APP_REQUIRED')
        raw = c.read_bytes(path / 'Contents/Info.plist', 1024 * 1024)
        info = plistlib.loads(raw)
        c.require(isinstance(info, dict), 'APP_METADATA_INVALID')
        name = info.get('CFBundleExecutable')
        c.require(isinstance(name, str) and name not in ('.', '..') and not any(x in name for x in ('/', '\\', '\0')), 'APP_ENTRY_INVALID')
        binary = path / 'Contents/MacOS' / name
        metadata = c.sha(raw)
    c.require(binary.suffix.lower() not in ('.cmd', '.bat', '.ps1', '.py', '.sh', '.lnk'), 'NATIVE_EXECUTABLE_REQUIRED')
    digest = file_hash(c, binary)
    with binary.open('rb') as stream:
        magic = stream.read(4)
    valid = (magic[:2] == b'MZ' and binary.suffix.lower() == '.exe' if platform.system() == 'Windows' else magic in
             (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf') or (platform.system() == 'Linux' and magic == b'\x7fELF'))
    c.require(valid, 'NATIVE_EXECUTABLE_REQUIRED')
    return {'path': str(path), 'binary_sha256': digest, 'bundle_info_sha256': metadata}


def browser_identity(c, path):
    data = c.load_json(c.read_bytes(path))
    c.require(isinstance(data, dict), 'BROWSER_PREFERENCES_OBJECT_REQUIRED')
    selected = {key: data.get(key) for key in ('intl', 'dns_over_https', 'webrtc', 'proxy')}
    return c.sha(c.encode(selected))


def machine_id(c):
    return c.sha((platform.system() + '\0' + platform.node() + '\0' + str(Path.home())).encode())


def native_state(c):
    collected = c.collect(target='lifecycle-local')
    native = collected['native']
    values = {key: native.get(key) for key in WATCHED}
    # Hash address identities locally; an unchanged count is not an unchanged DNS server.
    if platform.system() == 'Darwin':
        raw = c.run_fixed(['/usr/sbin/scutil', '--dns'])
        if raw is None:
            dns_hash = None
        else:
            entries = re.findall(r'^\s*(?:nameserver\[\d+\]|domain|search domain\[\d+\]|port|if_index|flags|options|order)\s*:.*$', raw, re.M)
            dns_hash = c.sha(c.encode(entries)) if any('nameserver[' in x for x in entries) else None
    elif platform.system() == 'Windows' :
        raw = c.run_fixed(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(Path(__file__).with_name('collect_dns_identity.ps1'))])
        try:
            data = c.load_json(raw.encode()) if raw else None
            dns_hash = c.sha(c.encode(data)) if isinstance(data, list) and data else None
        except c.SetupError:
            dns_hash = None
    else:
        dns_hash = None
    return {'values': values, 'dns_identity_sha256': dns_hash, 'platform': platform.system()}


def item(key, title, passed, reason, action, required=True):
    return {'id': key, 'title': title, 'status': '已完成' if passed else '未完成', 'required': required,
            'reason': reason, 'next_step': action}


def save_report(c, output, kind, rows, extra=None, private=None, create=True):
    if create:
        c.new_dir(output)
    folder = Path(output)
    result = {'schema': 'claude-readiness-run/1', 'kind': kind, 'checked_at': c.now(), 'rows': rows,
              'required_checks_completed': all(r['status'] == '已完成' for r in rows if r['required']),
              'system_settings_changed': False, 'continuous_protection': False}
    if extra:
        result.update(extra)
    required_rows = [r for r in rows if r['required']]
    followup_rows = [r for r in rows if not r['required']]
    counts = {'required_completed': sum(r['status'] == '已完成' for r in required_rows),
              'required_incomplete': sum(r['status'] != '已完成' for r in required_rows),
              'followup_completed': sum(r['status'] == '已完成' for r in followup_rows),
              'followup_incomplete': sum(r['status'] != '已完成' for r in followup_rows)}
    result.update(counts)
    c.write_new(folder / 'report.json', c.encode(result))
    ordered = sorted(rows, key=lambda r: r['status'] == '已完成')
    completed = sum(r['status'] == '已完成' for r in rows)
    summary = f'已完成 {completed} 项／共 {len(rows)} 项，未完成 {len(rows) - completed} 项'
    launch_text = '已发送启动／激活请求，客户端实际采用待核验。' if result.get('launch_requested') else '本轮未发送启动请求。'
    separate_acceptance = kind.startswith(('recovery', 'lifecycle-', 'workflow-')) or kind in ('config-recovery', 'lifecycle_acceptance')
    required_label = '本次必需' if separate_acceptance else '启动必需'
    if separate_acceptance:
        launch_text = ('仅处理明确指定的文本文件；应用载入和实际网络效果仍需另行核验。'
                       if 'recovery' in kind else
                       '依据本轮供给的事件与进程证据判定；本工具不主动重启、换网、断网或发送请求。')
    if kind.startswith('workflow-'):
        launch_text = '仅保存或核对续做材料；网络须重新核验，操作授权不从记录恢复。'
    lines = ['# 环境检查报告', '', summary, '', '检查时间：' + result['checked_at'], '', launch_text, '', f'| 检查项 | {required_label} | 状态 | 原因／结果 | 下一步 |', '| --- | --- | --- | --- | --- |']
    escape_md = lambda value: str(value).replace('|', '\\|').replace('\n', ' ')
    for r in ordered:
        r = dict(r, required_label='是' if r['required'] else '否（补充检查）')
        lines.append('| ' + ' | '.join(escape_md(r[k]) for k in ('title', 'required_label', 'status', 'reason', 'next_step')) + ' |')
    lines += ['', '仅覆盖本次列出的检查和证据范围；不是持续断网保护，也不证明未观测的客户端采用同一路径。', f'标为非{required_label}的项目仍如实显示未完成；不能据此宣称全项验收通过。', '']
    body = ''.join('<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in (r['title'], '是' if r['required'] else '否（补充检查）', r['status'], r['reason'], r['next_step'])) + '</tr>' for r in ordered)
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>环境检查报告</title><style>body{font:16px/1.6 system-ui;margin:32px;max-width:1100px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:12px;text-align:left}th{background:#eef2f6}</style><h1>环境检查报告</h1><p>' + html.escape(summary) + '</p><p>检查时间：' + html.escape(result['checked_at']) + '</p><p>' + html.escape(launch_text) + '</p><table><thead><tr><th>检查项</th><th>' + required_label + '</th><th>状态</th><th>原因／结果</th><th>下一步</th></tr></thead><tbody>' + body + '</tbody></table><p>仅覆盖本次列出的检查和证据范围，不是持续断网保护。补充项目仍保留未完成结果。</p></html>'
    if kind == 'lifecycle-acceptance':
        summary = f"本次交付：已完成 {counts['required_completed']} 项／共 {len(required_rows)} 项，未完成 {counts['required_incomplete']} 项"
        followup_summary = f"后续复查：已完成 {counts['followup_completed']} 项，未完成 {counts['followup_incomplete']} 项"
        lines = ['# 生命周期验收', '', summary, '', '检查时间：' + result['checked_at'], '',
                 '仅判定本轮供给证据；未实测项目仍为未完成。']
        tables = []
        for title, section in (('本次交付', required_rows), ('后续复查', followup_rows)):
            ordered_section = sorted(section, key=lambda r: r['status'] == '已完成')
            lines += ['', '## ' + title, '', '| 检查项 | 状态 | 原因／结果 | 下一步 |', '| --- | --- | --- | --- |']
            body = ''
            for row in ordered_section:
                values = [row[k] for k in ('title', 'status', 'reason', 'next_step')]
                lines.append('| ' + ' | '.join(escape_md(value) for value in values) + ' |')
                body += '<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in values) + '</tr>'
            tables.append('<table><thead><tr><th>检查项</th><th>状态</th><th>原因／结果</th><th>下一步</th></tr></thead><tbody>' + body + '</tbody></table>')
        lines += ['', followup_summary + '。后续项目不计入本次交付数量；未实测不代表通过或持续保护。', '']
        page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>生命周期验收</title><style>body{font:16px/1.6 system-ui;margin:32px;max-width:1100px}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #ddd;padding:12px;text-align:left}th{background:#eef2f6}summary{cursor:pointer}details{margin-top:24px}</style><h1>生命周期验收</h1><p>' + html.escape(summary) + '</p><p>检查时间：' + html.escape(result['checked_at']) + '</p>' + tables[0] + '<details><summary>' + html.escape(followup_summary) + '</summary>' + tables[1] + '</details><p>仅判定本轮供给证据。后续项目不计入本次交付数量；未实测不代表通过或持续保护。</p></html>'
    c.write_new(folder / 'report.md', '\n'.join(lines).encode())
    c.write_new(folder / 'report.html', page.encode())
    if private is not None:
        c.write_new(folder / 'evidence.private.json', c.encode(private))
    public = {'status': 'report_written', 'completed': sum(r['status'] == '已完成' for r in rows),
            'incomplete': sum(r['status'] != '已完成' for r in rows),
            'required_checks_completed': result['required_checks_completed'],
            'system_settings_changed': result['system_settings_changed'],
            'launch_requested': bool(result.get('launch_requested')), 'runtime_adoption_verified': False}
    public.update(counts)
    for key in ('system_changes_performed', 'config_file_changed', 'recovery_state',
                'plan_sha256', 'receipt_sha256', 'evidence_scope', 'evidence_authenticity_verified'):
        if key in result:
            public[key] = result[key]
    return public


def create_baseline(c, config, fmt, original, node, group, executable, browser, output, policy='ai-only', direct_review=None):
    fmt = c.config_format(config, fmt)
    current, before = c.read_bytes(config), c.read_bytes(original)
    if policy in ('domestic-v4', 'unified-v4'):
        import domestic_policy
        import unified_policy
        unified_policy = domestic_policy if policy == 'domestic-v4' else unified_policy
        audit = unified_policy.audit(c, before, current, fmt, node, group, direct_review)
    else:
        audit = ai_routing.audit(c, before, current, fmt, node, group)
    c.require(audit['status'] == 'static_policy_matches', 'BASELINE_AI_POLICY_MISMATCH')
    client = client_identity(c, executable)
    native = native_state(c)
    browser_hash = browser_identity(c, browser) if browser else None
    record = {'schema': 'claude-readiness-baseline/1', 'created_at': c.now(), 'machine_id': machine_id(c),
              'format': fmt, 'policy': policy, 'direct_review': direct_review, 'config_sha256': c.sha(current), 'ai_original_sha256': c.sha(before),
              'node': node, 'group': group, 'client': client, 'native': native,
              'browser_path': str(Path(browser).absolute()) if browser else None, 'browser_sha256': browser_hash}
    c.new_dir(output)
    folder = Path(output)
    c.write_new(folder / 'config.bin', current)
    c.write_new(folder / 'ai-original.bin', before)
    raw = c.encode(record)
    c.write_new(folder / 'baseline.json', raw)
    c.write_new(folder / 'baseline.sha256', (c.sha(raw) + '\n').encode())
    return {'status': 'private_baseline_created', 'system_settings_changed': False, 'runtime_adoption_verified': False,
            'dns_identity_available': native['dns_identity_sha256'] is not None}


def read_baseline(c, directory):
    root = Path(directory)
    raw = c.read_bytes(root / 'baseline.json')
    c.require(c.decode(c.read_bytes(root / 'baseline.sha256', 128)).strip() == c.sha(raw), 'BASELINE_INTEGRITY_MISMATCH')
    data = c.load_json(raw)
    c.require(isinstance(data, dict), 'BASELINE_SCHEMA_INVALID')
    c.require(data.get('schema') == 'claude-readiness-baseline/1', 'BASELINE_SCHEMA_INVALID')
    c.require(isinstance(data.get('native'), dict) and isinstance(data['native'].get('values'), dict)
              and isinstance(data.get('client'), dict) and isinstance(data.get('node'), str)
              and isinstance(data.get('group'), str) and data.get('format') in ('yaml', 'json', 'shadowrocket'), 'BASELINE_SCHEMA_INVALID')
    current = c.read_bytes(root / 'config.bin')
    original = c.read_bytes(root / 'ai-original.bin')
    c.require(c.sha(current) == data.get('config_sha256') and c.sha(original) == data.get('ai_original_sha256'), 'BASELINE_SNAPSHOT_MISMATCH')
    return data, current, original


def recheck(c, baseline, config, executable, browser=None):
    saved, previous, original = read_baseline(c, baseline)
    c.require(saved.get('machine_id') == machine_id(c), 'BASELINE_MACHINE_MISMATCH')
    rows = []
    try:
        now = c.read_bytes(config)
    except c.SetupError:
        now = None
    same = now is not None and c.sha(now) == saved['config_sha256']
    rows.append(item('config_drift', '有效配置文件复查', same,
                     '与本机已确认基线一致；尚不证明运行中核心已载入。' if same else '配置文件变化、被移动或无法读取，需要核对，不能自动恢复旧值。',
                     '核对运行中配置及订阅更新持久化。' if same else '用原基线与当前文件生成私有差异；确认新增修改后建立新基线。'))
    try:
        c.require(now is not None, 'CURRENT_CONFIG_UNAVAILABLE')
        if saved.get('policy', 'ai-only') in ('domestic-v4', 'unified-v4'):
            import domestic_policy
            import unified_policy
            unified_policy = domestic_policy if saved['policy'] == 'domestic-v4' else unified_policy
            audit = unified_policy.audit(c, original, now, saved['format'], saved['node'], saved['group'], saved.get('direct_review'))
        else:
            audit = ai_routing.audit(c, original, now, saved['format'], saved['node'], saved['group'])
        valid = audit['status'] == 'static_policy_matches'
    except c.SetupError:
        valid = False
    rows.append(item('ai_policy', 'AI 单节点及拒绝回退规则', valid,
                     '指定文件的专属规则与基线一致。' if valid else '专属规则或其他基线内容已改变，无法沿用原结论。',
                     '继续检查实际连接与运行中核心。' if valid else '审阅差异并重做规则审计；不要覆盖客户后续修改。'))
    try:
        identity = client_identity(c, executable)
        same_client = identity == saved['client']
    except (c.SetupError, OSError, ValueError):
        same_client = False
    rows.append(item('client_drift', '客户端版本文件复查', same_client,
                     '客户端入口及文件哈希与基线一致。' if same_client else '客户端路径、版本文件或应用元数据改变／无法读取。',
                     '继续启动前检查。' if same_client else '核对官方更新来源、兼容性和设置，再经确认建立新基线。'))
    native = native_state(c)
    known = {k for k, v in saved['native']['values'].items() if v is not None and v != []}
    network_keys = {'http_proxy_enabled', 'https_proxy_enabled', 'socks_proxy_enabled', 'pac_present',
                    'dns_v4_count', 'dns_v6_count', 'ipv4_interface_count', 'ipv6_interface_count', 'tunnel_interface_count'}
    for key, title, selected, required in (
            ('native_drift', '时间与语言等独立本机字段', known - network_keys, False),
            ('network_drift', '网络接管相关字段复查', known & network_keys, True)):
        changed = [name for name in selected if native['values'].get(name) != saved['native']['values'][name]]
        stable = bool(selected) and not changed
        rows.append(item(key, title, stable,
                         '已取得的字段与基线一致；未知字段未被证明。' if stable else '已记录字段变化，或基线没有可比较字段。',
                         '保留客户选择；未覆盖字段在现场补查。' if stable else '核实变化是否为客户主动调整；时间和语言可独立处理，不自动恢复。' if not required else '先核对网络变化，更新真实核验记录后再继续。', required))
    dns_same = saved['native'].get('dns_identity_sha256') is not None and saved['native']['dns_identity_sha256'] == native.get('dns_identity_sha256')
    rows.append(item('dns_drift', '系统 DNS 配置复查', dns_same,
                     '可读取的 DNS 配置身份与基线一致；不代表查询流量路径。' if dns_same else 'DNS 配置改变，或未取得可比较的 DNS 配置。',
                     '结合主动检测与核心日志验证查询路径。' if dns_same else '读取当前系统 DNS 及代理解析设置，确认变化后重建基线。'))
    if saved.get('browser_sha256') is not None:
        try:
            matched = bool(browser) and str(Path(browser).absolute()) == saved['browser_path'] and browser_identity(c, browser) == saved['browser_sha256']
        except (c.SetupError, OSError):
            matched = False
        rows.append(item('browser_drift', '指定浏览器偏好文件复查', matched,
                         '语言、DNS、WebRTC、代理相关偏好字段与基线一致；不代表运行时或组织策略。' if matched else '相关偏好字段变化，或文件未提供／无法读取。',
                         '继续核对实际浏览器行为。' if matched else '审阅本地偏好差异，只处理相关设置，不整文件回滚。'))
    return rows, saved


def startup(c, baseline, config, executable, browser, plan, allow_network, launch, output, readiness=None):
    c.require(not launch or platform.system() in ('Darwin', 'Windows'), 'NATIVE_MAC_OR_WINDOWS_REQUIRED')
    # Validate output before probes or launch, and never accept an old pass report as authority.
    c.new_dir(output)
    rows, saved = recheck(c, baseline, config, executable, browser)
    network_checks.validate_plan(c, plan)
    required = [x for x in plan['checks'] if x['required']]
    domains = ai_routing.catalog(c)['suffixes']
    def ai_endpoint(check):
        host = urlsplit(check.get('url', '')).hostname or ''
        return any(host == domain or host.endswith('.' + domain) for domain in domains)
    minimum = (any(x['type'] == 'https' and x.get('route') == 'proxy' and ai_endpoint(x) for x in required)
               and any(x['type'] == 'egress' and x.get('route') == 'proxy' and x.get('expected_ip') for x in required))
    proxy_set = {x.get('proxy') for x in required if x['type'] in ('https', 'egress')}
    minimum = minimum and len(proxy_set) == 1 and all(x.get('route') == 'proxy' for x in required if x['type'] in ('https', 'egress'))
    rows.append(item('startup_scope', '启动所需探测范围', minimum,
                     '包含同一本机代理端口的必需 AI HTTPS 与已确认探针出口检查；不同域名仍可能命中不同出站组。' if minimum else '缺少必需代理 HTTPS／预期出口，或必需探测使用不同路径。',
                     '执行本轮探测。' if minimum else '完善具体探测方案，确认指定代理和预期出口；不能用直连通过替代。'))
    private = []
    if minimum and all(r['status'] == '已完成' for r in rows if r['required']):
        active, private = network_checks.run_checks(c, plan, allow_network, readiness=readiness, config=config, browser=browser)
        rows += active
    else:
        rows.append(item('network_pending', '本轮启动前网络检测', False, '本机基线或探测范围尚未满足，未发起本轮网络检测。', '先处理上面的未完成项，再重新检查。'))
    passed = all(r['status'] == '已完成' for r in rows if r['required'])
    requested = False
    if launch and passed:
        # Recheck local inputs after network probes; no imported path or argv is executed.
        fresh, _ = recheck(c, baseline, config, executable, browser)
        import dns_readiness
        endpoint = next((x.get('proxy') for x in required if x['type'] in ('https', 'egress')), None)
        still_ready, ready_code = dns_readiness.check(c, readiness, config, browser, endpoint)
        if not still_ready:
            fresh.append(item('launch_readiness', '启动瞬间 DNS/代理核验', False, '启动前核验记录失效、过期或代理入口变化，已阻止启动。', '重新核对网络条件和本轮记录，再执行启动检查。'))
        if not all(r['status'] == '已完成' for r in fresh if r['required']):
            rows.append(item('prelaunch_drift', '启动瞬间复查', False, '检测期间本机状态变化，已阻止启动。', '核对变化后重新运行。'))
        else:
            path = Path(executable).absolute()
            args = ['/usr/bin/open', str(path)] if platform.system() == 'Darwin' and path.suffix.lower() == '.app' else [str(path)]
            c.write_new(Path(output) / 'launch-intent.private.json', c.encode({'created_at': c.now(), 'client_sha256': saved['client']['binary_sha256'], 'phase': 'launch_requested_next_not_yet_confirmed'}))
            try:
                subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
                requested = True
                rows.append(item('client_start', '客户端实际启动与采用', False, '启动／激活请求已发送；尚未确认界面、登录及客户端实际采用的网络路径。', '由客户机 Codex 检查应用界面和实际请求，再完成此项验收。', False))
            except OSError:
                rows.append(item('client_start', '客户端启动', False, '启动请求失败。', '检查本机权限与客户端入口后重试。'))
    return save_report(c, output, 'preflight', rows, {'launch_requested': requested, 'plan_sha256': c.sha(c.encode(plan))}, private, create=False)
