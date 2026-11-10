"""Desktop operations with explicit inputs and private artifacts."""
import argparse
import datetime as dt
from pathlib import Path
import re
import sys
import uuid

import browser_webrtc
import config_recovery as storage
import intake_flow
import operation_tools
import skill_updates

STUN_URL = 'stun:stun.cloudflare.com:3478'
SESSION_SECONDS = 120
TOKEN = re.compile(r'[0-9a-f]{32}')
BROWSER_URL = re.compile(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/[A-Za-z0-9_-]{43}/')
FIELDS = dict(operation_tools.FIELDS, intake_start={'task'}, intake_answer={'token', 'revision', 'value'},
              intake_copy={'token', 'revision', 'kit'}, update_check={'path', 'approved'},
              browser_prepare={'approved'}, browser_status={'token'}, browser_serve={'token'})


def platform():
    return {'darwin': 'macos', 'win32': 'windows'}.get(sys.platform, 'linux' if sys.platform.startswith('linux') else 'unsupported')


def directory(c, root, kind, token, create=False):
    c.require(type(token) is str and TOKEN.fullmatch(token), 'DESKTOP_TOOL_TOKEN_INVALID')
    return storage._private_dir(c, root / (kind + '-' + token), create=create)


def read(c, folder, name, maximum=131072):
    path, _ = storage._safe_path(c, folder / name)
    return c.load_json(c.read_bytes(path, maximum))


def intake_result(c, state, folder):
    report = intake_flow.assess(c, state)
    message = {'needs_input': '请选择当前问题的答案。', 'needs_review': '仍有待核对的条件，可以把已知信息交给 Codex。',
               'explanation_only': '已整理路线比较所需信息。', 'ready_for_plan': '已整理本轮需求，可以准备方案。'}[report['status']]
    return {'message': message, 'token': state['session_id'], 'revision': state['revision'],
            'question': report['next_question'], 'folder': str(folder)}


def intake(c, root, operation, payload):
    if operation == 'intake_start':
        c.require(payload['task'] in intake_flow.TASKS, 'DESKTOP_TOOL_INPUT_INVALID')
        state = intake_flow.start(c, payload['task'])
        folder = directory(c, root, 'intake', state['session_id'], create=True)
    else:
        folder = directory(c, root, 'intake', payload['token'])
        rev = payload['revision']
        c.require(type(rev) is int and 0 <= rev <= 10000, 'DESKTOP_TOOL_INPUT_INVALID')
        state = intake_flow.validate(c, read(c, folder, f'facts-{rev}.private.json'))
        c.require(state['revision'] == rev and state['session_id'] == payload['token'] and
                  not (folder / f'facts-{rev + 1}.private.json').exists(), 'DESKTOP_TOOL_STAGE_CHANGED')
        if operation == 'intake_copy':
            kit = Path(payload['kit'])
            c.require(kit.is_absolute() and not any(ord(ch) < 32 for ch in str(kit)), 'DESKTOP_TOOL_INPUT_INVALID')
            report = intake_flow.assess(c, state)
            target = 'windows' if platform() == 'windows' else 'mac'
            skill = kit / '.agents' / 'skills' / f'claude-{target}-readiness' / 'SKILL.md'
            facts = {k: v['value'] if v['state'] == 'known' else v['state'] for k, v in state['facts'].items()}
            text = ('请使用我们维护的 Claude 环境工具 https://github.com/LOM2729/claude-environment-check 。'
                    f'桌面随包 Skill 在 {skill} 。以下是本轮已整理的事实，请复用并按任务准备下一步。'
                    '需要变更或联网时先核对本轮具体范围。\n'
                    + c.encode({'facts': facts, 'missing': report['missing_fields'], 'references': report['references']}).decode('utf-8'))
            return dict(intake_result(c, state, folder), message='已复制本轮需求。', clipboard_text=text)
        report = intake_flow.assess(c, state)
        question = report['next_question']
        value = payload['value']
        c.require(question and type(value) is str and (not value or value in question['options']), 'DESKTOP_TOOL_INPUT_INVALID')
        state = intake_flow.answer(c, state, [{'field': question['field'], 'state': 'known' if value else 'unknown',
                                               'value': value or None, 'source': 'user'}])
    c.write_new(folder / f"facts-{state['revision']}.private.json", c.encode(state))
    return intake_result(c, state, folder)


def browser_prepare(c, root, payload, selected_source):
    c.require(payload['approved'] is True, 'DESKTOP_TOOL_NETWORK_APPROVAL_REQUIRED')
    source, data = selected_source()
    token = uuid.uuid4().hex
    folder = directory(c, root, 'browser', token, create=True)
    plan = browser_webrtc.validate_plan({'schema': browser_webrtc.PLAN_SCHEMA, 'created_at': c.now(),
        'target_alias': 'desktop', 'profile_alias': 'selected-browser', 'platform': platform(),
        'config_sha256': c.sha(data), 'stun_urls': [STUN_URL], 'measurement_seconds': 12})
    c.write_new(folder / 'plan.private.json', c.encode(plan))
    c.write_new(folder / 'config.private.bin', data)
    c.write_new(folder / 'source.private.json', c.encode({'path': str(source), 'plan_sha256': browser_webrtc.plan_digest(plan)}))
    return {'message': '正在准备浏览器检测页。', 'token': token, 'folder': str(folder)}


def browser_serve(c, root, payload):
    folder = directory(c, root, 'browser', payload['token'])
    plan = browser_webrtc.validate_plan(read(c, folder, 'plan.private.json'))
    record = read(c, folder, 'source.private.json')
    plan_digest = browser_webrtc.plan_digest(plan)
    age = (dt.datetime.now(dt.timezone.utc) - browser_webrtc._stamp(plan['created_at'])).total_seconds()
    c.require(plan['platform'] == platform() and 0 <= age <= 60 and plan['stun_urls'] == [STUN_URL]
              and record['plan_sha256'] == plan_digest, 'DESKTOP_BROWSER_PLAN_CHANGED')
    def matches():
        source, _ = storage._safe_path(c, record['path'])
        return c.sha(c.read_bytes(source)) == plan['config_sha256']
    c.require(c.sha(c.read_bytes(folder / 'config.private.bin')) == plan['config_sha256'] and matches(),
              'DESKTOP_BROWSER_PLAN_CHANGED')
    # A launch is used once. An interrupted server does not restart from its files.
    c.write_new(folder / 'started', b'used\n')
    return browser_webrtc.serve(c, plan, SESSION_SECONDS, folder / 'session.private.json',
                               folder / 'report.private.json', config_check=matches)


def browser_status(c, root, payload):
    folder = directory(c, root, 'browser', payload['token'])
    plan = browser_webrtc.validate_plan(read(c, folder, 'plan.private.json'))
    expected = browser_webrtc.plan_digest(plan)
    if (folder / 'report.private.json').exists():
        report = read(c, folder, 'report.private.json')
        c.require(report['plan_sha256'] == expected and report['network_protection_verified'] is False,
                  'DESKTOP_BROWSER_PLAN_CHANGED')
        status = report['status']
        messages = {'sample_matches': '本次 IPv4 样本与输入的参考地址一致。', 'ipv6_observed': '本次浏览器样本观察到 IPv6 公网候选。',
                    'mismatch_observed': '本次浏览器样本与输入的参考地址有差异。',
                    'incomplete': '样本不足，保留未完成。', 'cancelled': '浏览器检测已取消。', 'expired': '检测页已到期。'}
        return {'message': messages.get(status, '检测未完成。'), 'finished': True, 'folder': str(folder)}
    if not (folder / 'session.private.json').exists():
        return {'message': '正在启动本机检测页。', 'finished': False}
    session = read(c, folder, 'session.private.json')
    url = session['url']
    match = BROWSER_URL.fullmatch(url)
    c.require(session['plan_sha256'] == expected and match and int(match.group(1)) <= 65535, 'DESKTOP_BROWSER_SESSION_INVALID')
    return {'message': '复制链接，用平时的浏览器资料打开。', 'url': url, 'finished': False, 'folder': str(folder)}


def update(c, root, payload):
    c.require(payload['approved'] is True, 'DESKTOP_TOOL_NETWORK_APPROVAL_REQUIRED')
    folder = directory(c, root, 'update', uuid.uuid4().hex, create=True)
    target = 'windows' if platform() == 'windows' else 'mac'
    result = skill_updates.run(c, argparse.Namespace(skill_root=payload['path'], platform=target,
        snapshot=None, snapshot_output=None, allow_network=True, output=folder / 'report.private.json'))
    return {'message': '已完成文件差异核对。', 'folder': str(folder), 'details': [
        f"GitHub 提交 {result['upstream_commit'][:12]}", f"内容不同 {result['changed_count']} 项",
        f"仓库独有 {result['upstream_only_count']} 项", f"本机独有 {result['local_only_count']} 项"]}


def dispatch(c, root, operation, payload, selected_source, engine_prefix):
    c.require(operation in FIELDS and type(payload) is dict and set(payload) == FIELDS[operation],
              'DESKTOP_TOOL_INPUT_INVALID')
    if operation.startswith('intake_'):
        return intake(c, root, operation, payload)
    if operation == 'browser_prepare':
        return browser_prepare(c, root, payload, selected_source)
    if operation == 'browser_serve':
        return browser_serve(c, root, payload)
    if operation == 'browser_status':
        return browser_status(c, root, payload)
    if operation == 'update_check':
        return update(c, root, payload)
    return operation_tools.dispatch(c, root, operation, payload, engine_prefix)
