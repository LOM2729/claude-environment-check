"""Narrow offline JSON worker for the desktop shell; never activates a configuration.

The shell supplies native-dialog paths and a private workspace. The saved session
is evidence, never authority. CLI forwarding retains the existing CLI contracts.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

SOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
import claude_setup as c
import config_recovery as recovery
import contact_checks
import domestic_policy

CLIENTS = {'browser': '网页浏览器', 'claude_gui': 'Claude 桌面端', 'codex_gui': 'Codex 桌面端',
           'claude_cli': 'Claude CLI', 'codex_cli': 'Codex CLI'}
FIELDS = {'status': set(), 'select_config': {'path'}, 'collect': set(),
          'prepare': {'node', 'clients', 'keep'}, 'confirm_export': {'destination', 'plan_id'},
          'verify_readback': {'path'}, 'import_report': {'path'}, 'handoff': {'kit_path', 'node', 'clients', 'keep'}, 'get_report': set()}
MESSAGES = {
    'INVALID_REQUEST': '请求格式或字段不受支持。',
    'WORKSPACE_UNSAFE': '任务目录无法安全使用，请重新创建本机私有任务。',
    'SESSION_INVALID': '进度文件无法安全读取，请使用新的私有任务目录。',
    'BUSY': '另一个操作正在处理此任务，请稍后重试。',
    'CONFIG_REQUIRED': '请先选择本机已有的文本配置文件。',
    'CONFIG_UNSAFE': '配置无法安全读取或格式不受支持；请选择普通本机文本文件。',
    'SOURCE_CHANGED': '原配置已变化，旧方案已失效；请重新选择配置并准备。',
    'COLLECTION_REQUIRED': '请先完成本机只读检查。',
    'SCOPE_REQUIRED': '请选择实际用途、文件中的具体节点，并填写简短的保留业务。',
    'IMPLICIT_REVIEW_REQUIRED': '发现尚未确认的隐含请求；先交给 Codex 核对应用与依赖。',
    'DIRECT_REVIEW_REQUIRED': '现有直连或拒绝例外需要逐项核对，未自动改变这些规则。',
    'PREPARE_BLOCKED': '当前配置不能自动形成完整候选，请交给 Codex 核对兼容性与依赖。',
    'DEPENDENCY_REQUIRED': '缺少 YAML 解析依赖，尚未准备候选；需补齐打包依赖。',
    'PLAN_REQUIRED': '没有可确认的当前方案，请重新准备。',
    'PLAN_CHANGED': '方案文件或摘要已变化，请重新准备后确认。',
    'EXPORT_UNSAFE': '无法导出：目标必须是本机安全目录中的全新文件，不能覆盖已有文件。',
    'READBACK_MISMATCH': '所选读回文件与候选不完全一致，仍需核对；尚未验证运行与网络。',
    'REPORT_INVALID': '报告格式、时间或文字不符合安全查看要求；未导入任何核验结论。',
    'REPORT_CHANGED': '导入报告的私有副本已变化或不可读，请重新选择原报告；不会沿用其结论。',
    'REPORT_REQUIRED': '尚无本机检查报告，请先运行只读检查。',
    'OPERATION_FAILED': '本次操作未完成；请保留私有任务材料并交给 Codex 核对。',
}


class DesktopError(Exception):
    pass


def need(condition, code):
    if not condition:
        raise DesktopError(code)


def row(title, passed, reason, next_step):
    return {'title': title, 'status': '已完成' if passed else '未完成', 'reason': reason, 'next_step': next_step}


def initial():
    return {'schema': 'claude-desktop-session/1', 'stage': 'prepare', 'config': None, 'plan': None,
            'scope': {'clients': [], 'keep': []}, 'requested_node': '', 'checks': [], 'last_action': '', 'updated_at': None}


def text_label(value, maximum=120):
    need(isinstance(value, str) and 0 < len(value.strip()) <= maximum, 'SCOPE_REQUIRED')
    try:
        result = c.safe_review_text(value)
    except c.SetupError:
        raise DesktopError('SCOPE_REQUIRED') from None
    need('\n' not in result and '\t' not in result and not any(x in result for x in ('<', '>')), 'SCOPE_REQUIRED')
    return result


def display_name(value, fallback):
    try:
        return text_label(value)
    except DesktopError:
        return fallback


def public(state):
    result = {k: state[k] for k in ('stage', 'config', 'scope', 'requested_node', 'checks', 'last_action', 'updated_at')}
    result['plan'] = None
    if state.get('plan'):
        result['plan'] = {k: state['plan'][k] for k in ('id', 'summary', 'ready', 'candidate_name', 'activation_ready', 'activation_blockers', 'node')}
    for key in ('report_path', 'handoff_path', 'report_source'):
        if key in state:
            result[key] = state[key]
    return result


def private_file(root, relative, missing=False):
    need(isinstance(relative, str), 'SESSION_INVALID')
    p = Path(relative)
    need(not p.is_absolute() and p.parts and all(x not in ('.', '..') for x in p.parts), 'SESSION_INVALID')
    path = root / p
    recovery._safe_path(c, path, missing=missing)
    return path


def atomic_session(root, state):
    path = root / 'session.private.json'
    recovery._safe_path(c, path, missing=not path.exists())
    temporary = root / ('.session-' + uuid.uuid4().hex)
    recovery._write(c, temporary, c.encode(state))
    try:
        os.replace(temporary, path)
        recovery._sync_dir(root)
    finally:
        if temporary.exists():
            temporary.unlink()


def load(root, ignore_report=False):
    path = root / 'session.private.json'
    if not path.exists() and not path.is_symlink():
        return initial()
    try:
        recovery._safe_path(c, path)
        state = c.load_json(c.read_bytes(path, 1024 * 1024))
        need(isinstance(state, dict) and state.get('schema') == 'claude-desktop-session/1', 'SESSION_INVALID')
        # Existing sessions predate the explicit draft-node field.
        state.setdefault('requested_node', (state.get('plan') or {}).get('node', ''))
        need(all(k in state for k in initial()), 'SESSION_INVALID')
        need(state['last_action'] == '' or state['last_action'] in FIELDS, 'SESSION_INVALID')
        need(state['updated_at'] is None or (isinstance(state['updated_at'], str) and re.fullmatch(r'[0-9T:+.-]{20,40}', state['updated_at'])), 'SESSION_INVALID')
        need(bool(state.get('source')) == bool(state.get('config')), 'SESSION_INVALID')
        need(not state.get('plan') or state.get('source'), 'SESSION_INVALID')
        need(state['stage'] in ('prepare', 'confirm', 'configure', 'verify', 'deliver'), 'SESSION_INVALID')
        # A saved file cannot claim network/AI completion: this worker has no such operation.
        if state['stage'] == 'deliver':
            state['stage'] = 'verify'
        need(isinstance(state['scope'], dict) and set(state['scope']) == {'clients', 'keep'}, 'SESSION_INVALID')
        scope_values(state['scope']['clients'], state['scope']['keep'])
        need(isinstance(state['checks'], list) and len(state['checks']) <= 202, 'SESSION_INVALID')
        for item in state['checks']:
            need(isinstance(item, dict) and set(item) == {'title', 'status', 'reason', 'next_step'}, 'SESSION_INVALID')
            need(item['status'] in ('已完成', '未完成'), 'SESSION_INVALID')
            for key in ('title', 'reason', 'next_step'):
                c.safe_review_text(item[key])
        if state['config'] is not None:
            need(set(state['config']) == {'name', 'format', 'node_names'}, 'SESSION_INVALID')
            text_label(state['config']['name'])
            need(state['config']['format'] in ('json', 'yaml', 'shadowrocket'), 'SESSION_INVALID')
            need(isinstance(state['config']['node_names'], list), 'SESSION_INVALID')
            for name in state['config']['node_names']:
                text_label(name)
        need(isinstance(state['requested_node'], str) and
             (state['requested_node'] == '' or state['requested_node'] in (state.get('config') or {}).get('node_names', [])),
             'SESSION_INVALID')
        state.pop('handoff_prompt', None)  # regenerate from scope, never replay saved instructions
        for key in ('report_path', 'handoff_path'):
            if key in state:
                rel = Path(state[key]).relative_to(root)
                private_file(root, str(rel))
        if ignore_report:
            if state.get('imported_report'):
                state['checks'] = [imported_notice()]
            state.pop('imported_report', None)
            state.pop('report_source', None)
        if state.get('imported_report'):
            checked_at, imported_rows = imported_rows_from_copy(root, state)
            state['checks'] = imported_rows
            state['report_source'] = report_source(checked_at)
        else:
            state.pop('report_source', None)
        return state
    except DesktopError as exc:
        if str(exc) == 'REPORT_CHANGED':
            raise
        raise DesktopError('SESSION_INVALID') from None
    except Exception:
        raise DesktopError('SESSION_INVALID') from None


def scope_values(clients, keep):
    need(isinstance(clients, list) and len(clients) <= len(CLIENTS)
         and all(isinstance(x, str) and x in CLIENTS for x in clients)
         and len(set(clients)) == len(clients), 'SCOPE_REQUIRED')
    need(isinstance(keep, list) and len(keep) <= 12, 'SCOPE_REQUIRED')
    return {'clients': list(clients), 'keep': [text_label(x, 80) for x in keep]}


def snapshot(path):
    need(isinstance(path, str) and Path(path).is_absolute() and len(path) <= 4096, 'CONFIG_UNSAFE')
    try:
        return recovery._snapshot(c, path)
    except Exception:
        raise DesktopError('CONFIG_UNSAFE') from None


def invalidate(state):
    state['plan'] = None
    state['stage'] = 'prepare'
    for key in ('readback', 'handoff_path', 'handoff_prompt'):
        state.pop(key, None)


def check_bindings(root, state):
    if not state.get('source'):
        return
    try:
        data, _ = snapshot(state['source']['path'])
        need(c.sha(data) == state['source']['sha256'], 'SOURCE_CHANGED')
    except Exception:
        invalidate(state)
        state['checks'] = [row('原配置一致性', False, MESSAGES['SOURCE_CHANGED'], '重新选择配置、只读检查并准备新方案。')]
        raise DesktopError('SOURCE_CHANGED') from None
    if state.get('plan'):
        try:
            plan = state['plan']
            need(set(plan) == {'id', 'summary', 'ready', 'candidate_name', 'folder', 'node', 'bindings', 'source_sha256', 'scope_sha256', 'activation_ready', 'activation_blockers'}, 'PLAN_CHANGED')
            text_label(plan['summary'], 600)
            text_label(plan['candidate_name'])
            text_label(plan['node'])
            need(plan['activation_ready'] is False and isinstance(plan['activation_blockers'], list), 'PLAN_CHANGED')
            for blocker in plan['activation_blockers']:
                c.safe_review_text(blocker)
            need(plan['ready'] is True and re.fullmatch('[a-f0-9]{64}', plan['id']), 'PLAN_CHANGED')
            need(plan['source_sha256'] == state['source']['sha256'] and plan['node'] == state['requested_node'] and
                 plan['scope_sha256'] == c.sha(c.encode(state['scope'])), 'PLAN_CHANGED')
            for relative, digest in plan['bindings'].items():
                need(c.sha(c.read_bytes(private_file(root, relative))) == digest, 'PLAN_CHANGED')
            need(plan['bindings'] and str(Path(plan['folder']) / plan['candidate_name']) in plan['bindings'], 'PLAN_CHANGED')
            if state.get('readback'):
                actual, _ = snapshot(state['readback']['path'])
                need(c.sha(actual) == state['readback']['sha256'], 'PLAN_CHANGED')
        except Exception:
            invalidate(state)
            state['checks'] = [row('方案一致性', False, MESSAGES['PLAN_CHANGED'], '重新生成候选，复核具体方案后再导出。')]
            raise DesktopError('PLAN_CHANGED') from None


def source_copy(root, state, folder):
    need(state.get('source'), 'CONFIG_REQUIRED')
    data, _ = snapshot(state['source']['path'])
    need(c.sha(data) == state['source']['sha256'], 'SOURCE_CHANGED')
    suffix = '.conf' if state['config']['format'] == 'shadowrocket' else '.' + state['config']['format']
    path = folder / ('source' + suffix)
    recovery._write(c, path, data)
    return path


def new_folder(root, prefix):
    folder = root / (prefix + '-' + uuid.uuid4().hex)
    return recovery._private_dir(c, folder, create=True)


def unverified_rows():
    return [row('实际导入与进程采用', False, '候选文件尚不能证明客户端已导入或进程已采用。', '由 Codex 核对持久化入口、活动配置与实际节点。'),
            row('非 AI 网络与 DNS', False, '尚未核验接口 IPv6、DNS 与真实非 AI 路径。', '先准备具体网络方案并确认，完成获准的非 AI 核验与当前 dns-ready。'),
            row('实际 AI 使用与交付', False, '尚未启动、登录或请求 AI 服务，未完成使用验收。', '网络门槛通过后，仅验证本轮选择的入口；未测项保留未完成。')]


def select(root, state, payload):
    invalidate(state)
    state.update(config=None, checks=[], requested_node='')
    for key in ('source', 'collection', 'report_path'):
        state.pop(key, None)
    data, identity = snapshot(payload['path'])
    fmt = c.config_format(identity['path'], 'auto')
    obj = c.parse_config(data, fmt)
    if fmt == 'shadowrocket':
        names = [line.split('=', 1)[0].strip() for line in obj.get('proxy', []) if '=' in line]
    else:
        proxies = obj.get('proxies', [])
        need(isinstance(proxies, list), 'CONFIG_UNSAFE')
        names = [p['name'] for p in proxies if isinstance(p, dict) and isinstance(p.get('name'), str)]
    safe = []
    for name in names:
        try:
            value = text_label(name)
            if value == name and name not in safe:
                safe.append(name)
        except DesktopError:
            continue
    state['config'] = {'name': display_name(Path(identity['path']).name, '已选配置'), 'format': fmt, 'node_names': safe}
    state['source'] = {'path': identity['path'], 'sha256': c.sha(data)}
    state['checks'] = [row('配置离线识别', True, '已安全读取所选文本配置，仅列出文件中已有的具体节点。', '选择实际用途和具体节点，再运行本机只读检查。')]
    if not safe:
        state['checks'].append(row('可用具体节点', False, '未发现可安全显示的静态节点；动态订阅节点未物化，不能猜测。', '请提供客户端导出的普通文本配置，或交给 Codex 核对。'))


def collect(root, state):
    invalidate(state)
    folder = new_folder(root, 'collection')
    source = source_copy(root, state, folder)
    data = c.collect(str(source), fmt=state['config']['format'])
    raw = c.encode(data)
    review = c.review_template(data, c.sha(raw), mode='automatic', preserved=['system_language'])
    recovery._write(c, folder / 'collection.json', raw)
    recovery._write(c, folder / 'review.json', c.encode(review))
    c.render_report(data, folder / 'report', review, c.sha(raw))
    state['collection'] = {'folder': folder.name, 'sha256': c.sha(raw), 'review_sha256': c.sha(c.encode(review)),
                           'source_sha256': state['source']['sha256']}
    state['report_path'] = str(folder / 'report/report.html')
    _, rows = c.report_rows(data, review, c.sha(raw))
    state['checks'] = [{k: r[k] for k in ('title', 'status', 'reason', 'next_step')} for r in rows]


def prepare(root, state, payload):
    invalidate(state)
    state['checks'] = []
    state['scope'] = scope_values(payload['clients'], payload['keep'])
    need(state['scope']['clients'], 'SCOPE_REQUIRED')
    need(state.get('config') and payload['node'] in state['config']['node_names'], 'SCOPE_REQUIRED')
    state['requested_node'] = payload['node']
    need(state.get('collection') and state['collection']['source_sha256'] == state['source']['sha256'], 'COLLECTION_REQUIRED')
    folder = new_folder(root, 'prepare')
    source = source_copy(root, state, folder)
    fmt = state['config']['format']
    rows, evidence = contact_checks.scan(c, source, fmt)
    recovery._write(c, folder / 'contact.private.json', c.encode(evidence))
    state['checks'] = [{k: r[k] for k in ('title', 'status', 'reason', 'next_step')} for r in rows]
    blocking = [e for e in evidence if e['category'] in ('ai_target', 'unknown') and e['kind'] != '小火箭应用级测速/订阅/自动启动状态需现场核对']
    need(not blocking, 'IMPLICIT_REVIEW_REQUIRED')
    try:
        domestic_policy.prepare(c, source, fmt, payload['node'], folder / 'candidate')
    except c.SetupError as exc:
        code = str(exc)
        if 'DIRECT' in code or 'DENY_REVIEW' in code:
            raise DesktopError('DIRECT_REVIEW_REQUIRED') from None
        if code == 'YAML_DEPENDENCY_MISSING':
            raise DesktopError('DEPENDENCY_REQUIRED') from None
        raise DesktopError('PREPARE_BLOCKED') from None
    candidate_name = 'candidate.' + ('conf' if fmt == 'shadowrocket' else fmt)
    candidate = folder / 'candidate' / candidate_name
    candidate_rows, candidate_evidence = contact_checks.scan(c, candidate, fmt)
    # The native scanner conservatively flags words such as 'test' inside
    # generated DOMAIN rules. These static policy additions are audited above;
    # retain their unknown findings as activation blockers, never as approval.
    candidate_blockers = [e for e in candidate_evidence if e['category'] in ('ai_target', 'unknown')
                          and e['kind'] != '小火箭应用级测速/订阅/自动启动状态需现场核对'
                          and not (fmt == 'shadowrocket' and e['kind'] == '小火箭自动行为待确认')]
    need(not candidate_blockers, 'IMPLICIT_REVIEW_REQUIRED')
    if fmt == 'shadowrocket':
        state['checks'] = [{k: r[k] for k in ('title', 'status', 'reason', 'next_step')} for r in candidate_rows]
    recovery._write(c, folder / 'candidate-contact.private.json', c.encode(candidate_evidence))
    bound = [source, *sorted((folder / 'candidate').rglob('*'))]
    bindings = {str(p.relative_to(root)): c.sha(c.read_bytes(p)) for p in bound if p.is_file()}
    summary = ('仅导出 domestic-v4 候选：国内直连，普通国外与 AI 共用所选节点；保留 AI 优先、IPv6 拒绝、国内视频及 UDP 规则。'
               '系统语言、时区和浏览器语言保持；不导入、不重启。业务兼容、系统 DNS/IPv6、运行采用与网络仍需核验。原配置保持，可删除未采用的导出文件。')
    state['plan'] = {'id': c.sha(c.encode({'nonce': uuid.uuid4().hex, 'bindings': bindings, 'scope': state['scope'], 'node': payload['node']})),
                     'summary': summary, 'ready': True, 'candidate_name': candidate_name,
                     'activation_ready': False, 'activation_blockers': ['应用级隐含请求、保留业务和系统网络方案尚未现场核对；仅可导出，不能直接激活。'],
                     'folder': str((folder / 'candidate').relative_to(root)), 'node': payload['node'], 'bindings': bindings,
                     'source_sha256': state['source']['sha256'], 'scope_sha256': c.sha(c.encode(state['scope']))}
    state['stage'] = 'confirm'
    candidate_reason = ('已生成国内分流候选、静态策略审计与私有差异；尚未应用。' if c.read_bytes(candidate) != c.read_bytes(source)
                        else '配置已符合静态策略，已保存候选；没有内容差异，尚未核验运行采用。')
    state['checks'] += [row('完整离线候选', True, candidate_reason, '确认本次摘要后选择新文件导出；实际配置由 Codex 继续核对。')] + unverified_rows()
    if state['scope']['keep']:
        state['checks'].append(row('必须保留的业务', False, '已记录必保业务，尚未核验其 DNS、UDP、IPv6 或企业网络依赖。', '导入前由 Codex 逐项核对依赖并准备具体兼容方案。'))


def windows_export_new(path, expected_chain, content):
    """Create private from the first byte, then rename without replacing a target.

    Ordinary Downloads folders may have broader inherited ACLs. Their permissions
    are never changed; the new file keeps its protected current-user/SYSTEM DACL.
    Windows os.rename fails when the destination already exists.
    """
    fd, stage_name = recovery._win_private_stage(path.parent)
    stage = Path(stage_name)
    identity = None
    try:
        opened = os.fstat(fd)
        identity = (opened.st_dev, opened.st_ino)
        _, stage_chain = recovery._safe_path(c, stage)
        need(stage_chain == expected_chain, 'EXPORT_UNSAFE')
        acl = recovery._win_acl_summary(stage)
        need(all(acl[key] for key in ('owner_is_current', 'dacl_present', 'dacl_nonnull',
                                     'dacl_protected', 'only_allowed_principals',
                                     'current_user_full_access')), 'EXPORT_UNSAFE')
        stream = os.fdopen(fd, 'wb')
        fd = None  # the stream now owns the Windows handle
        with stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck both parent paths and the exact stage after closing the handle.
        _, stage_chain = recovery._safe_path(c, stage)
        _, current_chain = recovery._safe_path(c, path, missing=True)
        info = stage.lstat()
        need(stage_chain == current_chain == expected_chain
             and (info.st_dev, info.st_ino) == identity and not path.exists(), 'EXPORT_UNSAFE')
        need(c.sha(c.read_bytes(stage)) == c.sha(content), 'EXPORT_UNSAFE')
        os.rename(stage, path)  # Windows: no REPLACE_EXISTING and no overwrite.
        _, final_chain = recovery._safe_path(c, path)
        final = path.lstat()
        need(final_chain == expected_chain and (final.st_dev, final.st_ino) == identity,
             'EXPORT_UNSAFE')
        final_acl = recovery._win_acl_summary(path)
        need(all(final_acl[key] for key in ('owner_is_current', 'dacl_present', 'dacl_nonnull',
                                           'dacl_protected', 'only_allowed_principals',
                                           'current_user_full_access')), 'EXPORT_UNSAFE')
    finally:
        if fd is not None:
            os.close(fd)
        # Only remove our exact temporary inode; never remove a concurrent target.
        try:
            _, cleanup_chain = recovery._safe_path(c, stage)
            current = stage.lstat()
            if cleanup_chain == expected_chain and (current.st_dev, current.st_ino) == identity:
                stage.unlink()
        except (OSError, c.SetupError):
            pass


def confirm_export(root, state, payload):
    need(state.get('plan'), 'PLAN_REQUIRED')
    plan = state['plan']
    need(payload['plan_id'] == plan['id'] and plan['ready'] is True, 'PLAN_CHANGED')
    check_bindings(root, state)
    candidate = private_file(root, str(Path(plan['folder']) / plan['candidate_name']))
    content = c.read_bytes(candidate)
    baseline, _ = snapshot(state['source']['path'])
    audit = domestic_policy.audit(c, baseline, content, state['config']['format'], plan['node'])
    need(audit['status'] == 'static_policy_matches', 'PLAN_CHANGED')
    try:
        destination = payload['destination']
        need(isinstance(destination, str) and Path(destination).is_absolute(), 'EXPORT_UNSAFE')
        path, chain = recovery._safe_path(c, destination, missing=True)
        need(not path.exists() and path.suffix.lower() == candidate.suffix, 'EXPORT_UNSAFE')
        if os.name == 'nt':
            windows_export_new(path, chain, content)
        else:
            # POSIX keeps the existing O_EXCL / 0600 path, with no inherited ACL.
            if sys.platform == 'darwin':
                need(recovery._metadata(path.parent).get('acl') is None, 'EXPORT_UNSAFE')
            again, current_chain = recovery._safe_path(c, path, missing=True)
            need(chain == current_chain, 'EXPORT_UNSAFE')
            recovery._write(c, again, content)
    except Exception:
        raise DesktopError('EXPORT_UNSAFE') from None
    exported, _ = snapshot(str(path))
    need(c.sha(exported) == c.sha(content), 'EXPORT_UNSAFE')
    state['export'] = {'path': str(path), 'sha256': c.sha(content), 'at': c.now(), 'plan_id': plan['id']}
    state['stage'] = 'configure'
    state['checks'] = [row('候选导出', True, '本轮确认的候选已写入全新文件；原文件未改动。', '在实际导入前，由 Codex 核对应用级隐含请求、保留业务和具体网络方案。')] + unverified_rows()


def verify(root, state, payload):
    need(state.get('plan'), 'PLAN_REQUIRED')
    need(state.get('export', {}).get('plan_id') == state['plan']['id'], 'PLAN_REQUIRED')
    plan = state['plan']
    actual, identity = snapshot(payload['path'])
    folder = new_folder(root, 'readback')
    target = folder / plan['candidate_name']
    recovery._write(c, target, actual)
    plan_folder = root / plan['folder'] / 'plan'
    if plan_folder.exists():
        result = c.verify_readback(plan_folder, target, exported=True)
        matches = result['status'] == 'candidate_bytes_match'
    else:
        candidate = private_file(root, str(Path(plan['folder']) / plan['candidate_name']))
        matches = c.read_bytes(candidate) == actual
        result = {'status': 'candidate_bytes_match' if matches else 'unexpected_content_conflict', 'network_verified': False}
    baseline, _ = snapshot(state['source']['path'])
    audit = domestic_policy.audit(c, baseline, actual, state['config']['format'], plan['node'])
    matches = matches and audit['status'] == 'static_policy_matches'
    recovery._write(c, folder / 'result.json', c.encode({'readback': result, 'audit': audit}))
    state.pop('readback', None)
    state['stage'] = 'verify' if matches else 'configure'
    state['checks'] = [row('客户导出文件读回', matches, '读回文件与候选及静态策略一致；不能证明进程采用或网络已核实。' if matches else MESSAGES['READBACK_MISMATCH'], '继续核对活动配置、实际节点和获准的非 AI 网络路径。')] + unverified_rows()
    need(matches, 'READBACK_MISMATCH')
    state['readback'] = {'path': identity['path'], 'sha256': c.sha(actual)}


def project_report(raw):
    """Project untrusted report data; no extras, file references or instructions run."""
    need(isinstance(raw, dict) and raw.get('schema') == 'claude-readiness-run/1', 'REPORT_INVALID')
    kind, stamp, rows = raw.get('kind'), raw.get('checked_at'), raw.get('rows')
    need(isinstance(kind, str) and re.fullmatch('[a-z][a-z0-9_-]{0,63}', kind), 'REPORT_INVALID')
    try:
        c.safe_review_text(kind)
    except c.SetupError:
        raise DesktopError('REPORT_INVALID') from None
    need(isinstance(stamp, str) and len(stamp) <= 64 and
         re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', stamp), 'REPORT_INVALID')
    try:
        time = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        need(time.tzinfo is not None and time.utcoffset() is not None, 'REPORT_INVALID')
        stamp = time.isoformat(timespec='seconds')
    except (ValueError, OverflowError):
        raise DesktopError('REPORT_INVALID') from None
    need(isinstance(rows, list) and 0 < len(rows) <= 200, 'REPORT_INVALID')
    projected = []
    for item in rows:
        need(isinstance(item, dict) and all(k in item for k in ('title', 'status', 'reason', 'next_step')),
             'REPORT_INVALID')
        need(item['status'] in ('已完成', '未完成'), 'REPORT_INVALID')
        clean = {'status': item['status']}
        for key in ('title', 'reason', 'next_step'):
            try:
                text = c.safe_review_text(item[key])
            except c.SetupError:
                raise DesktopError('REPORT_INVALID') from None
            # Public reports are plain prose, not HTML, links, or filesystem commands.
            need(not any(x in text for x in ('<', '>', '`', '\\')) and
                 not re.search(r'(?i)(?:file|javascript|data):|[A-Z]:[\\/]|(?:^|\s)/(?:[^\s/]+/)*[^\s]+|(?:^|\s)\.\.?[\\/]', text),
                 'REPORT_INVALID')
            clean[key] = text
        projected.append(clean)
    return stamp, kind, projected


def report_source(stamp):
    return {'label': '客户选择的检查报告', 'checked_at': stamp, 'imported': True}


def imported_notice():
    return row('导入记录适用性', False,
               '仅导入记录，不证明当前整机、目标匹配或真实性；不恢复授权，也不代表本轮已完成。',
               '由 Codex 按现有证据机制核对实际目标和当前证据，未核验项保持未完成。')


def imported_rows_from_copy(root, state):
    try:
        record = state['imported_report']
        need(isinstance(record, dict) and set(record) == {'file', 'sha256'}, 'REPORT_CHANGED')
        original = c.read_bytes(private_file(root, record['file']), 1024 * 1024)
        need(c.sha(original) == record['sha256'], 'REPORT_CHANGED')
        checked_at, _, rows = project_report(c.load_json(original))
        return checked_at, [imported_notice(), *rows]
    except Exception:
        raise DesktopError('REPORT_CHANGED') from None


def import_report(root, state, payload):
    try:
        original, _ = snapshot(payload['path'])
        need(len(original) <= 1024 * 1024, 'REPORT_INVALID')
        checked_at, _, rows = project_report(c.load_json(original))
    except Exception:
        raise DesktopError('REPORT_INVALID') from None
    folder = new_folder(root, 'imported-report')
    destination = folder / 'original.private.json'
    recovery._write(c, destination, original)
    state['imported_report'] = {'file': str(destination.relative_to(root)), 'sha256': c.sha(original)}
    state['checks'] = [imported_notice(), *rows]
    state['report_source'] = report_source(checked_at)
    state.pop('report_path', None)  # do not open a stale collection HTML as this report


def get_report(root, state):
    if state.get('imported_report'):
        return imported_rows_from_copy(root, state)[1]
    need(state.get('collection'), 'REPORT_REQUIRED')
    record = state['collection']
    data = c.read_bytes(private_file(root, record['folder'] + '/collection.json'))
    review = c.read_bytes(private_file(root, record['folder'] + '/review.json'))
    need(c.sha(data) == record['sha256'] and c.sha(review) == record['review_sha256'], 'SESSION_INVALID')
    _, rows = c.report_rows(c.load_json(data), c.load_json(review), c.sha(data))
    return [{k: r[k] for k in ('title', 'status', 'reason', 'next_step')} for r in rows]


def desktop_engine():
    """Derive the trusted local entry point; never accept an executable in JSON."""
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command.append(str(Path(__file__).resolve()))
    return {'schema': 'claude-desktop-engine/1', 'kit_version': c.VERSION,
            'engine_command': command, 'cli_prefix': command + ['--cli']}


def handoff(root, state, payload):
    kit = payload['kit_path']
    need(isinstance(kit, str) and Path(kit).is_absolute() and len(kit) <= 4096 and not any(ord(ch) < 32 for ch in kit), 'INVALID_REQUEST')
    selected_scope = scope_values(payload.get('clients', state['scope']['clients']),
                                  payload.get('keep', state['scope']['keep']))
    selected_node = payload.get('node', state['requested_node'])
    need(isinstance(selected_node, str) and
         (selected_node == '' or selected_node in (state.get('config') or {}).get('node_names', [])),
         'SCOPE_REQUIRED')
    if selected_scope != state['scope'] or selected_node != state['requested_node']:
        invalidate(state)
        state.pop('imported_report', None)
        state.pop('report_source', None)
        state['checks'] = [row('本轮范围', False, '用途、保留业务或节点已更新，旧候选方案已失效。',
                               '按当前选择重新准备候选，或由 Codex 继续核对未决项。')] + unverified_rows()
    state['scope'], state['requested_node'] = selected_scope, selected_node
    folder = new_folder(root, 'handoff')
    engine = desktop_engine()
    runtime_note = ('桌面包已内置运行时。' if getattr(sys, 'frozen', False)
                    else '当前为开发模式，已绑定本次后端使用的解释器。')
    clients = '、'.join(CLIENTS[x] for x in state['scope']['clients']) or '尚未选择'
    keep = '、'.join(state['scope']['keep']) or '未指定，需核对'
    scope = ('# 本轮范围（只作上下文，不恢复授权）\n\n实际用途：' + clients + '\n必须保留：' + keep +
             '\n当前阶段：' + state['stage'] + '\n指定节点：' + (state['requested_node'] or '尚未选择') +
             '\n保持系统语言、输入法、键盘、时区和浏览器语言；仅正常使用为本轮默认必需，其他生命周期事件未测未完成。\n')
    prompt = ('工具包位置：' + kit + '。本任务私有目录：' + str(root) + '。继续说明目录：' + str(folder) + '。\n请先读应用随包的 START-HERE.md、实际平台 Skill（.agents/skills/claude-mac-readiness/SKILL.md 或 '
              '.agents/skills/claude-windows-readiness/SKILL.md）及其 references/five-step-setup.md。按唯一五步流程继续。'
              + runtime_note +
              '读取本说明同目录的 desktop-engine.private.json，其中 kit_version 是本次工具包版本，engine_command 和 cli_prefix 由后端自身推导。'
              '本次使用该引擎参数数组附加 --cli 及原工具子命令，替代文档中的 python <Skill>/scripts/claude_setup.py；无需安装系统 Python。'
              'cli_prefix 已包含 --cli，不重复追加。先只运行 --cli --version（即 cli_prefix 数组附加 ["--version"]）核对 kit_version，版本不匹配则暂停。'
              '必须按参数数组执行，不拼接 shell 命令；此入口不授予新的修改或联网权限。普通独立 ZIP 的原说明不变。'
              '本轮用途：' + clients + '；必保业务：' + keep + '；指定节点：' + (state['requested_node'] or '尚未选择') + '；当前阶段：' + state['stage'] + '。'
              '读取本说明同目录的 scope.md 与任务根目录的 session.private.json，并重新核对来源、候选与真实目标机。'
              '桌面端仅做离线准备和文件导出，不代表导入、生效、网络或 AI 使用已完成。'
              '先核对隐含请求、DIRECT 例外、必保业务与控制通道；具体变更准备可审阅方案后确认，历史文件不恢复授权。'
              '系统 DNS/IPv6 与获准非 AI 路径实测、当前 dns-ready 是 AI 访问前置门槛。'
              '需要重启时先保存进度和离线恢复说明，交客户手动完成；不自动断开当前 Codex 或远控。未测未完成。')
    recovery._write(c, folder / 'desktop-engine.private.json', c.encode(engine))
    recovery._write(c, folder / 'scope.md', scope.encode())
    recovery._write(c, folder / 'continue.txt', prompt.encode())
    # A fresh handoff folder keeps older context immutable; links stay within workspace.
    state['handoff_path'] = str(folder / 'continue.txt')
    state['handoff_prompt'] = prompt


def acquire_lock(root):
    path = root / '.desktop.lock'
    recovery._safe_path(c, path, missing=not path.exists())
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'WORKSPACE_UNSAFE')
        if os.name == 'nt':
            import msvcrt
            if info.st_size == 0:
                os.write(fd, b'0')
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except Exception:
        os.close(fd)
        raise


def handle(root, action, payload):
    state, lock, directory = initial(), None, None
    try:
        need(isinstance(action, str) and action in FIELDS and isinstance(payload, dict), 'INVALID_REQUEST')
        if action == 'handoff':
            need('kit_path' in payload and set(payload) <= FIELDS[action], 'INVALID_REQUEST')
        else:
            need(set(payload) == FIELDS[action], 'INVALID_REQUEST')
        try:
            directory = recovery._private_dir(c, root, create=not Path(root).exists())
        except Exception:
            raise DesktopError('WORKSPACE_UNSAFE') from None
        try:
            lock = acquire_lock(directory)
        except OSError:
            lock = None
            raise DesktopError('BUSY') from None
        state = load(directory, ignore_report=action == 'import_report')
        if action != 'select_config':
            check_bindings(directory, state)
        if action == 'select_config':
            select(directory, state, payload)
        elif action == 'collect':
            collect(directory, state)
        elif action == 'prepare':
            prepare(directory, state, payload)
        elif action == 'confirm_export':
            confirm_export(directory, state, payload)
        elif action == 'verify_readback':
            verify(directory, state, payload)
        elif action == 'import_report':
            import_report(directory, state, payload)
        elif action == 'handoff':
            handoff(directory, state, payload)
        if action in ('select_config', 'collect', 'prepare', 'confirm_export', 'verify_readback'):
            state.pop('imported_report', None)
            state.pop('report_source', None)
        rows = get_report(directory, state) if action == 'get_report' else None
        if action not in ('status', 'get_report'):
            state['last_action'], state['updated_at'] = action, c.now()
            atomic_session(directory, state)
        result = {'ok': True, 'state': public(state)}
        if rows is not None:
            result['rows'] = rows
        if action == 'handoff':
            result['prompt'] = state['handoff_prompt']
        return result
    except Exception as exc:
        code = str(exc) if isinstance(exc, DesktopError) and str(exc) in MESSAGES else 'OPERATION_FAILED'
        if action in ('prepare', 'select_config'):
            invalidate(state)
        if directory is not None and lock is not None and action not in ('status', 'get_report') and code not in ('SESSION_INVALID', 'REPORT_CHANGED'):
            state['last_action'], state['updated_at'] = action, c.now()
            if code not in ('SOURCE_CHANGED', 'PLAN_CHANGED', 'READBACK_MISMATCH'):
                state['checks'] = state['checks'][:201]
                state['checks'].append(row('当前操作', False, MESSAGES[code], '按提示补充材料，或导出继续配置说明交给 Codex。'))
            try:
                atomic_session(directory, state)
            except Exception:
                pass
        return {'ok': False, 'error': code, 'message': MESSAGES[code], 'state': public(state)}
    finally:
        if lock is not None:
            try:
                os.close(lock)
            except OSError:
                pass


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--cli']:
        return c.main(argv[1:])
    # Frozen CLI probes spawn sys.executable with the bundled module path.
    # Only this exact module entry is accepted, never an arbitrary Python file.
    if getattr(sys, 'frozen', False) and len(argv) == 2 and argv[1] == '--worker':
        import network_checks
        if Path(argv[0]) == Path(network_checks.__file__).resolve():
            import runpy
            sys.argv = [argv[0], '--worker']
            runpy.run_module('network_checks', run_name='__main__')
            return 0
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True)
    args = parser.parse_args(argv)
    try:
        incoming = sys.stdin.buffer.read(65537)
        need(len(incoming) <= 65536, 'INVALID_REQUEST')
        request = c.load_json(incoming)
        need(isinstance(request, dict) and set(request) == {'action', 'payload'}, 'INVALID_REQUEST')
        # Dependency messages and accidental debug prints never enter the public protocol.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = handle(args.workspace, request['action'], request['payload'])
    except Exception:
        result = {'ok': False, 'error': 'INVALID_REQUEST', 'message': MESSAGES['INVALID_REQUEST'], 'state': public(initial())}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
