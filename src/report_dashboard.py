"""Pure offline presentation of existing public report rows; never runs checks."""
from datetime import datetime
from html import escape

# Questions for customers; the source check and its evidence stay in details.
CUSTOMER_TITLES = {
    'system_proxy': '代理是否开启', 'system_dns': 'DNS 是否泄露',
    'public_egress': '出口是否一致', 'ip_families': 'IPv6 是否按要求关闭',
    'webrtc': '浏览器是否暴露额外出口', 'ai_policy': 'AI 专属代理规则是否正确',
    'ai_failure': '代理断开后会不会直连', 'config': '新配置是否生效',
    'client_function': 'Claude 和 Codex 能否正常使用', 'browser': '浏览器设置是否合适',
    'system_time': '时间和时区是否正确', 'system_language': '系统语言是否保持原样',
    'auth_environment': '登录和代理设置是否冲突', 'claude_command': 'Claude Code 能否正常使用',
    'dns_records': 'DNS 特殊记录是否正常', 'lifecycle': '重启和更新后是否需要复查',
    'update_recheck': '更新后是否复查', 'active_network': '实际联网是否正常',
    'startup_check': '本次启动前是否检查',
    'config_drift': '代理配置有没有变化', 'client_drift': '软件版本有没有变化',
    'network_drift': '代理设置有没有变化', 'native_drift': '时间和语言有没有变化',
    'dns_drift': 'DNS 设置有没有变化', 'browser_drift': '浏览器设置有没有变化',
    'startup_scope': '本次检查是否准备齐全', 'network_pending': '联网情况是否已检查',
    'launch_readiness': '打开软件前网络是否就绪', 'prelaunch_drift': '检查期间环境有没有变化',
    'client_start': '软件是否正常打开', 'dns_readiness_gate': 'DNS 和代理是否准备好',
}


def _customer_words(row):
    key = row.get('id')
    title = CUSTOMER_TITLES.get(key, row['title']) if isinstance(key, str) else row['title']
    reason, action = row['reason'], row['next_step']
    kind, done = row.get('probe_type'), row['status'] == '已完成'
    if kind is None and key == 'system_dns' and 'probe_path' in row and 'outcome' in row:
        kind = 'dns'  # Older probe rows predate the explicit type field.
    drift = {
        'config_drift': ('代理配置与上次记录一致；是否真正生效还需确认。', '代理配置有变化或暂时读不到。', '让 Codex 对照当前配置核对变化。'),
        'client_drift': ('软件文件与上次记录一致。', '软件文件有变化或暂时读不到。', '核对软件更新情况后再继续。'),
        'dns_drift': ('DNS 设置与上次记录一致；这不等于没有泄露。', 'DNS 设置有变化，或还没读取完整。', '核对设置后，再检查 DNS 查询实际走的线路。'),
        'network_drift': ('已读取的代理设置与上次一致；尚不能代替实际联网测试。', '代理设置有变化，或还没读取完整。', '核对变化后补做实际连接检查。'),
        'native_drift': ('已读取的时间和语言设置与上次一致。', '时间或语言设置有变化，或还没读取完整。', '按客户需要核对，保留未要求修改的设置。'),
        'startup_scope': ('本次要检查的代理线路和对照出口已准备好。', '检测范围或对照出口还没准备完整。', '由 Codex 补齐本次检查所需资料。'),
    }
    if isinstance(key, str) and key in drift:
        good, pending, action = drift[key]
        reason = good if done else pending
    # A successful resolver query is NOT a DNS leak test. Static drift checks
    # likewise retain their narrower question, even when the check completed.
    if kind == 'dns':
        title = 'DNS 能否解析网站地址'
        if done:
            reason = '本次能解析地址；这还不能说明 DNS 没有泄露。'
            action = '继续核对 DNS 查询实际走的线路。'
    elif kind == 'egress':
        title = '出口是否一致'
        reason = ('本次测试出口与指定出口一致；只代表这条测试线路。' if done else
                  '还不能确认出口一致，需要核对指定出口和测试结果。')
        action = '再核对实际使用的软件是否走同一出口。' if done else '由 Codex 核对本机记录后再确认。'
    elif kind == 'stun':
        title = 'UDP 出口是否符合预期'
        if done:
            reason = '本次 UDP 测试出口符合预期；不代表所有应用都已检查。'
    elif kind == 'https':
        title = '代理能否连接目标网站' if row.get('probe_path') == 'proxy' else '目标网站能否连接'
        if done:
            reason = '这条测试线路连接成功；登录和实际功能还需单独确认。'
    return title, reason, action


CSS = '''
:root{color-scheme:light;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#182230;background:#fff}
*{box-sizing:border-box}body{margin:0}main{max-width:1080px;margin:0 auto;padding:36px 24px 28px}
h1{font-size:26px;line-height:1.3;font-weight:650;margin:0 0 12px;text-wrap:balance}
h2{font-size:16px;line-height:1.5;margin:0;font-weight:650}.eyebrow{font-size:12px;color:#64748b;margin:0 0 8px}
p{margin:0;line-height:1.65;text-wrap:pretty}.time,.meta,.scope{font-size:13px;color:#526172}
time,.count{font-variant-numeric:tabular-nums}.meta{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:6px}
.snapshot{font-size:13px;color:#526172;margin:16px 0 26px;padding:10px 0;border-top:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0}
.section-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin:0 0 10px}
.count{font-size:13px;color:#526172}table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:14px;line-height:1.6}
col.topic{width:24%}col.state{width:13%}col.explanation{width:63%}
th{text-align:left;color:#526172;font-size:12px;font-weight:600;border-bottom:1px solid #cbd5e1;padding:10px 12px}
td,tbody th{vertical-align:top;text-align:left;padding:14px 12px;border-bottom:1px solid #e2e8f0;overflow-wrap:anywhere}
tbody th{color:#182230;font-size:14px;font-weight:550}.status{display:inline-block;white-space:nowrap;font-size:12px;font-weight:650;padding:2px 8px;border-radius:4px}
.done{color:#176444;background:#edf7f0}.todo{color:#8a4b13;background:#fff4e8}
.next{margin-top:5px;color:#526172}.label{font-weight:600}.record{margin-top:8px;font-size:12px;color:#526172}
details>summary{cursor:pointer;width:fit-content;max-width:100%;line-height:1.6;overflow-wrap:anywhere}
summary:focus-visible{outline:2px solid #2563eb;outline-offset:4px;border-radius:2px}
.record dl{margin:8px 0 0;line-height:1.6}.record dt{font-weight:600}.record dd{margin:2px 0 8px;overflow-wrap:anywhere}
.followup{margin-top:24px;padding-top:16px;border-top:1px solid #cbd5e1}.followup>summary{font-weight:600;font-size:14px}.followup table{margin-top:10px}
.scope{margin-top:8px}.report-notes{margin-top:24px;font-size:13px;color:#526172}.report-notes ul{padding-left:20px;margin:10px 0}.report-notes li{margin:6px 0;overflow-wrap:anywhere}
.empty{padding:18px 12px;border-bottom:1px solid #e2e8f0;color:#526172;font-size:14px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:600px){main{padding:24px 14px}h1{font-size:22px}table{font-size:13px}tbody th{font-size:13px}th,td,tbody th{padding:11px 5px}col.topic{width:26%}col.state{width:20%}col.explanation{width:54%}.status{padding:2px 6px}.meta{gap:4px 12px}}
@media print{main{max-width:none;padding:0}body{font-size:11px}tr{break-inside:avoid}.snapshot{margin:10px 0}.report-notes{margin-top:12px}}
'''


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('DASHBOARD_TEXT_REQUIRED')
    return escape(value, quote=True)


def _time(value):
    try:
        if not isinstance(value, str) or len(value) > 80:
            raise ValueError
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return '<time datetime="' + escape(stamp.isoformat(), quote=True) + '">' + escape(stamp.isoformat(sep=' ', timespec='seconds')) + '</time>'
    except (ValueError, TypeError, OverflowError):
        return '未提供有效时间'


def _rows(rows):
    projected = []
    for row in rows:
        if not isinstance(row, dict) or row.get('status') not in ('已完成', '未完成'):
            raise ValueError('DASHBOARD_BINARY_STATUS_REQUIRED')
        if type(row.get('required', True)) is not bool:
            raise ValueError('DASHBOARD_SCOPE_REQUIRED')
        item = {key: _text(row.get(key)) for key in ('title', 'status', 'reason', 'next_step')}
        title, reason, action = _customer_words(row)
        item['technical'] = None
        if (title, reason, action) != (row['title'], row['reason'], row['next_step']):
            item['technical'] = (item['title'], item['reason'], item['next_step'])
        item.update(title=_text(title), reason=_text(reason), next_step=_text(action))
        item['required'] = row.get('required', True)
        item['done'] = row['status'] == '已完成'
        item['observation'] = _text(row['observation']) if isinstance(row.get('observation'), str) and row['observation'].strip() else None
        item['verified_at'] = _time(row['verified_at']) if row.get('verified_at') is not None else None
        projected.append(item)
    return sorted(projected, key=lambda row: row['done'])


def _count(rows):
    completed = sum(row['done'] for row in rows)
    return f'已完成 {completed} 项／共 {len(rows)} 项，未完成 {len(rows) - completed} 项'


def _table(rows, label):
    if not rows:
        return '<p class="empty">本轮没有列入检查项。下一步：先确认本次检查范围。</p>'
    body = []
    for row in rows:
        evidence = []
        if row['technical']:
            name, reason, action = row['technical']
            evidence.extend(('<dt>原检查项</dt><dd>' + name + '</dd>',
                             '<dt>详细依据</dt><dd>' + reason + '</dd>',
                             '<dt>详细处理建议</dt><dd>' + action + '</dd>'))
        if row['observation'] is not None:
            evidence.append('<dt>已记录的采集信息</dt><dd>' + row['observation'] + '</dd>')
        if row['verified_at'] is not None:
            evidence.append('<dt>项目核验时间</dt><dd>' + row['verified_at'] + '</dd>')
        disclosure = '<details class="record"><summary>查看记录</summary><dl>' + ''.join(evidence) + '</dl></details>' if evidence else ''
        body.append('<tr><th scope="row">' + row['title'] + '</th><td><span class="status ' + ('done' if row['done'] else 'todo') + '">' + row['status'] + '</span></td><td><p><span class="label">原因／结果：</span>' + row['reason'] + '</p><p class="next"><span class="label">下一步：</span>' + row['next_step'] + '</p>' + disclosure + '</td></tr>')
    return '<table><caption class="sr-only">' + _text(label) + '</caption><colgroup><col class="topic"><col class="state"><col class="explanation"></colgroup><thead><tr><th scope="col">你关心的问题</th><th scope="col">状态</th><th scope="col">结果与下一步</th></tr></thead><tbody>' + ''.join(body) + '</tbody></table>'


def render(*, title, checked_at, rows, generated_at=None, time_label='检查时间',
           current_label='本次检查', followup_label='后续复查', metadata=(), notes=(), excluded=()):
    """Render public fields only. No clock reads, I/O, automatic actions or refresh."""
    projected = _rows(rows)
    current = [row for row in projected if row['required']]
    followup = [row for row in projected if not row['required']]
    meta = ''.join('<span>' + _text(key) + '：' + _text(value) + '</span>' for key, value in metadata
                   if key in ('目标别名', '执行平台', '来源'))
    body = '<header><p class="eyebrow">Claude 环境检测 · 离线面板</p><h1>' + _text(title) + '</h1><p class="time">' + _text(time_label) + '：' + _time(checked_at) + '</p><div class="meta">' + meta + '</div></header>'
    body += '<p class="snapshot">这是检查快照。打开页面不会重新检查或启动软件；需要当前结果时，请回到 Codex 重新运行检查。</p>'
    body += '<section aria-labelledby="current-heading"><div class="section-head"><h2 id="current-heading">' + _text(current_label) + '</h2><p class="count">' + _count(current) + '</p></div>' + _table(current, current_label) + '</section>'
    if followup:
        body += '<details class="followup"><summary>' + _text(followup_label) + ' · ' + _count(followup) + '</summary><p class="scope">这些项目不计入本次必需数量；未实测仍为未完成。</p>' + _table(followup, followup_label) + '</details>'
    items = ['<li>页面生成时间：' + _time(generated_at) + '。生成页面不代表重新检查。</li>']
    items += ['<li>' + _text(note) + '</li>' for note in notes if note]
    for item in excluded:
        items.append('<li>不计入本次清单（已确认范围）：' + _text(item['title']) + '；' + _text(item['reason']) + '</li>')
    body += '<details class="report-notes"><summary>报告说明与范围</summary><ul>' + ''.join(items) + '</ul></details>'
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>' + _text(title) + '</title><style>' + CSS + '</style></head><body><main>' + body + '</main></body></html>'
