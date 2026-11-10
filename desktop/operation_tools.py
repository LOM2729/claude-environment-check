"""Private desktop adapters for scoped writes and offline bundle export."""

import os
from pathlib import Path
import re
import uuid

import config_recovery as storage
import guard_handoff
import native_client
import remote_setup
import scoped_cleanup
import system_guard


FIELDS = {
    'cleanup_plan': {'kind', 'path'},
    'cleanup_apply': {'token', 'stopped'},
    'cleanup_reconcile': {'token'},
    'cleanup_restore': {'token', 'stopped'},
    'cleanup_latest': set(),
    'native_inspect': set(),
    'native_plan': {'kind', 'domain', 'policy'},
    'native_apply': {'token', 'stopped'},
    'native_rollback': {'token', 'stopped'},
    'native_latest': set(),
    'guard_export': {'path'},
    'remote_export': {'path'},
}
TOKEN = re.compile(r'[a-f0-9]{32}')
DIGEST = re.compile(r'[a-f0-9]{64}')
STATE = 'clearpath-desktop-operation/1'
GUARD_PLAN_FIELDS = {
    'schema', 'created_at', 'spec', 'rules', 'rules_sha256', 'runtime_sha256',
    'windows_backend_sha256', 'scope', 'network_verified', 'limitations',
}
CLEANUP_RECOVERY = """缓存恢复

本目录属于一次具体的缓存隔离操作。新方案不会清除旧操作目录。
请保留整个目录的原始位置。执行隔离后，operation/backup/ 存放独立备份，operation/quarantine/ 存放隔离对象。

若桌面入口显示更新的方案，可用同一台设备和同一账户的 Claude 环境工具核对本次操作。
1. 以 operation/ 的绝对路径作为 --operation，使用 operation/operation.private.json 的文件 SHA-256 作为 --operation-sha256，运行 cleanup-reconcile。
2. 给 --out 指定新的本机私有目录，审阅对账结果及其中的 observation_sha256。原位置已有新数据或对账出现冲突时，先核对双方数据。
3. 对账明确有可恢复目录后，退出相关写入者并重新确认。用对账目录作为 --observation、返回的摘要作为 --observation-sha256，运行 cleanup-restore，另选全新 --out，并给出 --allow-write 与 --writers-stopped。

旧计划、回执和对账材料只记录范围及观察，恢复仍需当次确认。
"""


def _response(message, *, token=None, details=(), next_actions=(), folder=None):
    value = {'message': message, 'details': list(details), 'next': list(next_actions)}
    if token is not None:
        value['token'] = token
    if folder is not None:
        value['folder'] = str(folder)
    return value


def _absolute(c, value):
    c.require(type(value) is str and 0 < len(value) <= 32767 and Path(value).is_absolute()
              and not any(ch in value for ch in ('\x00', '\r', '\n')), 'TOOLS_PATH_INVALID')
    return Path(value)


def _load(c, path, limit=128 * 1024, pin=None):
    path, _ = storage._safe_path(c, path)
    raw = c.read_bytes(path, limit)
    if pin is not None:
        c.require(c.sha(raw) == pin, 'TOOLS_ARTIFACT_CHANGED')
    value = c.load_json(raw)
    c.require(type(value) is dict, 'TOOLS_RECORD_INVALID')
    return value


def _save(c, path, value):
    storage._safe_path(c, path, missing=not path.exists())
    pending = path.parent / ('.record-' + uuid.uuid4().hex)
    storage._write(c, pending, c.encode(value))
    try:
        os.replace(pending, path)
        storage._sync_dir(path.parent)
    finally:
        pending.unlink(missing_ok=True)


def _new(c, root, family):
    token = uuid.uuid4().hex
    folder = storage._private_dir(c, root / (family + '-' + token), create=True)
    return folder, {'schema': STATE, 'family': family, 'token': token}


def _read_record(c, root, family, token):
    c.require(type(token) is str and TOKEN.fullmatch(token), 'TOOLS_TOKEN_INVALID')
    folder = storage._private_dir(c, root / (family + '-' + token))
    record = _load(c, folder / 'record.private.json')
    c.require(record.get('schema') == STATE and record.get('family') == family
              and record.get('token') == token, 'TOOLS_RECORD_INVALID')
    return folder, record


def _record(c, folder, record, phase, **fields):
    record.update(phase=phase, **fields)
    _save(c, folder / 'record.private.json', record)


def _latest(c, root, family):
    path = root / (family + '-latest.private.json')
    if not path.exists() and not path.is_symlink():
        return None, None
    token = _load(c, path).get('token')
    return _read_record(c, root, family, token)


def _remember(c, root, record):
    _save(c, root / (record['family'] + '-latest.private.json'), {'token': record['token']})


def _present(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _pending_cleanup(c, root, token=None):
    folder, record = _latest(c, root, 'cleanup')
    if not record or record['token'] == token or not record.get('interrupted'):
        return None
    if not _present(folder / 'operation' / 'operation.private.json'):
        return None
    result = _cleanup_status(c, folder, record)
    result['details'].insert(0, '请先处理上次中断的缓存操作。')
    return result


def _cleanup_plan(c, root, kind, value):
    c.require(kind in ('cli', 'desktop'), 'TOOLS_CLEANUP_KIND_INVALID')
    selected = _absolute(c, value)
    pending = _pending_cleanup(c, root)
    if pending:
        return pending
    scope_key = 'config_root' if kind == 'cli' else 'desktop_root'
    cache_kind = kind + '-cache'
    host = scoped_cleanup.NativeHost()
    request = {'schema': 'claude-cleanup-scope/1', 'target_alias': 'desktop-cache',
               scope_key: str(selected), 'roots': []}
    host.validate_scope(c, request)
    selected = scoped_cleanup._path(c, selected, directory=True)
    _, names = scoped_cleanup.KINDS[cache_kind]
    for name in names:
        path = selected / name
        if _present(path):
            scoped_cleanup._path(c, path, directory=True)
            request['roots'].append({'kind': cache_kind, 'path': str(path)})
    if not request['roots']:
        return _response('所选目录没有可隔离的缓存。', details=[str(selected)])
    device = root.stat().st_dev
    c.require(all(Path(row['path']).lstat().st_dev == device for row in request['roots']),
              'CLEANUP_SAME_VOLUME_REQUIRED')
    folder, record = _new(c, root, 'cleanup')
    result = scoped_cleanup.plan(c, request, folder / 'plan', host=host)
    paths = [row['path'] for row in request['roots']]
    storage._write(c, folder / '缓存恢复说明.txt', CLEANUP_RECOVERY.encode('utf-8'))
    _record(c, folder, record, 'planned', plan_sha256=result['plan_sha256'], paths=paths,
            items=result['items'], size=result['bytes'], interrupted=False)
    _remember(c, root, record)
    return _cleanup_status(c, folder, record)


def _cleanup_status(c, folder, record):
    paths = record['paths']
    phase = record['phase']
    token = record['token']
    if phase == 'planned':
        details = [f'{len(paths)} 个缓存目录，{record["items"]} 个文件或目录，{record["size"]} 字节。',
                   '隔离方案有效期 10 分钟。', *paths]
        return _response('缓存隔离方案已就绪。', token=token, details=details, next_actions=['cleanup_apply'], folder=folder)
    if phase == 'restored':
        return _response('已恢复本次隔离的缓存。', token=token, details=paths, folder=folder)
    if phase == 'unchanged':
        return _response('对账完成，未发现需要恢复的缓存。', token=token, details=paths, folder=folder)
    if phase == 'observed' and record.get('restorable'):
        details = [f'{record["isolated_roots"]} 个缓存目录可恢复。', *record['restore_paths']]
        return _response('对账完成，可以审阅恢复。', token=token, details=details,
                         next_actions=['cleanup_restore', 'cleanup_reconcile'], folder=folder)
    if phase == 'observed':
        return _response('缓存状态存在冲突，请保留操作记录。', token=token, details=paths,
                         next_actions=['cleanup_reconcile'], folder=folder)
    if phase == 'reconcile_started':
        return _response('本轮对账未完成，请保留操作记录并核对缓存目录。', token=token, details=paths,
                         next_actions=['cleanup_reconcile'], folder=folder)
    if phase == 'quarantined':
        return _response('缓存已隔离，备份已保留。', token=token, details=paths,
                         next_actions=['cleanup_reconcile'], folder=folder)
    if _present(folder / 'operation' / 'operation.private.json'):
        return _response('操作尚未确认，请先对账。', token=token, details=paths,
                         next_actions=['cleanup_reconcile'], folder=folder)
    return _response('隔离未完成。请重新检查缓存并生成方案。', token=token, details=paths)


def _cleanup_apply(c, folder, record):
    c.require(record['phase'] == 'planned', 'TOOLS_CLEANUP_PLAN_USED')
    pending = _pending_cleanup(c, folder.parent, record['token'])
    if pending:
        return pending
    _record(c, folder, record, 'apply_started', interrupted=True)
    _remember(c, folder.parent, record)
    try:
        result = scoped_cleanup.quarantine(c, folder / 'plan', record['plan_sha256'],
                                           folder / 'operation', allow=True, stopped=True)
    except c.SetupError:
        if _present(folder / 'operation' / 'operation.private.json'):
            return _cleanup_status(c, folder, record)
        raise
    phase = 'quarantined' if result['status'] == 'quarantined' else 'apply_started'
    _record(c, folder, record, phase, operation_sha256=result['operation_sha256'],
            interrupted=phase != 'quarantined')
    return _cleanup_status(c, folder, record)


def _cleanup_reconcile(c, folder, record):
    c.require(record['phase'] not in ('planned', 'restored'), 'TOOLS_CLEANUP_OPERATION_REQUIRED')
    operation = folder / 'operation'
    path, _ = storage._safe_path(c, operation / 'operation.private.json')
    raw = c.read_bytes(path, scoped_cleanup.MAX_DOCUMENT)
    pin = c.sha(raw)
    value = c.load_json(raw)
    c.require(type(value) is dict and value.get('plan_sha256') == record['plan_sha256']
              and value.get('plan_path') == str(folder / 'plan')
              and record.get('operation_sha256', pin) == pin, 'TOOLS_ARTIFACT_CHANGED')
    # Invalidate an older observation before trying to produce a current one.
    _record(c, folder, record, 'reconcile_started', operation_sha256=pin)
    name = 'observation-' + uuid.uuid4().hex
    try:
        result = scoped_cleanup.reconcile(c, operation, pin, folder / name)
    except c.SetupError:
        return _cleanup_status(c, folder, record)
    observation_pin = result['observation_sha256']
    observation = _load(c, folder / name / 'observation.private.json',
                        scoped_cleanup.MAX_DOCUMENT, observation_pin)
    restore_paths = [path for path, row in zip(record['paths'], observation['roots'])
                     if row['state'] == 'isolated']
    phase = 'unchanged' if not result['isolated_roots'] and not result['conflict_roots'] else 'observed'
    _record(c, folder, record, phase, observation=name, observation_sha256=observation_pin,
            restorable=bool(result['isolated_roots'] and not result['conflict_roots']),
            isolated_roots=result['isolated_roots'], restore_paths=restore_paths,
            interrupted=phase != 'unchanged' and record.get('interrupted', False))
    return _cleanup_status(c, folder, record)


def _cleanup_restore(c, folder, record):
    c.require(record['phase'] == 'observed' and record.get('restorable'), 'TOOLS_CLEANUP_OBSERVATION_REQUIRED')
    pending = _pending_cleanup(c, folder.parent, record['token'])
    if pending:
        return pending
    name = record.get('observation')
    c.require(type(name) is str and name.startswith('observation-') and
              TOKEN.fullmatch(name.removeprefix('observation-')), 'TOOLS_RECORD_INVALID')
    pin = record.get('observation_sha256')
    c.require(type(pin) is str and DIGEST.fullmatch(pin), 'TOOLS_RECORD_INVALID')
    _record(c, folder, record, 'restore_started', interrupted=True)
    _remember(c, folder.parent, record)
    try:
        result = scoped_cleanup.restore(c, folder / name, pin, folder / ('restore-' + uuid.uuid4().hex),
                                        allow=True, stopped=True)
    except c.SetupError:
        return _cleanup_status(c, folder, record)
    if result['status'] == 'restored':
        _record(c, folder, record, 'restored', interrupted=False)
    return _cleanup_status(c, folder, record)


def _policy(value):
    return type(value) is str and 0 < len(value) <= 128 and value.isprintable() and ',' not in value


def _native_inspect(c):
    observed = native_client.capture(c)
    policies = sorted(name for name in observed['policy_names'] if _policy(name))[:128]
    result = _response('已读取当前 Clash Verge Rev 配置中的策略。',
                       details=[f'此处可选择 {len(policies)} 个策略。'])
    result['policies'] = policies
    return result


def _native_plan(c, root, kind, domain, policy):
    c.require(kind in ('DOMAIN', 'DOMAIN-SUFFIX') and type(domain) is str and 0 < len(domain) <= 253
              and re.fullmatch(r'[a-z0-9.-]+', domain) and _policy(policy), 'TOOLS_NATIVE_RULE_INVALID')
    request = {'schema': 'clearpath-native-rules/1', 'target_alias': 'desktop-clash-rules',
               'rules': [f'{kind},{domain},{policy}']}
    folder, record = _new(c, root, 'native')
    result = native_client.prepare(c, request, folder / 'plan')
    if result['status'] == 'no_change':
        folder.rmdir()
        return _response('当前规则已与所选规则一致。', details=[request['rules'][0]])
    pin = result['plan_sha256']
    plan = _load(c, folder / 'plan' / 'native-plan.private.json', native_client.MAX_DOCUMENT, pin)
    _record(c, folder, record, 'planned', plan_sha256=pin, rule=request['rules'][0],
            target=plan['binding']['target_path'], version=result['version'],
            later_chain_review_required=result['later_chain_review_required'])
    _remember(c, root, record)
    return _native_status(c, folder, record)


def _native_status(c, folder, record):
    details = [f'Clash Verge Rev {record["version"]}', record['rule'], record['target']]
    if record['later_chain_review_required']:
        details.append('当前配置含后续合并或脚本，实际规则顺序仍需核对。')
    phase = record['phase']
    token = record['token']
    if phase == 'planned':
        return _response('规则写入方案已就绪。', token=token, details=details, next_actions=['native_apply'])
    if phase == 'applied':
        details.append('文件已读回核对，客户端载入和实际路由待验证。')
        return _response('规则文件已写入，备份已保留。', token=token, details=details,
                         next_actions=['native_rollback'], folder=folder / 'apply')
    if phase == 'rolled_back':
        return _response('规则文件已恢复，客户端载入待验证。', token=token, details=details,
                         folder=folder / 'rollback')
    if _present(folder / 'apply'):
        return _response('规则操作尚未确认，请保留记录并核对当前文件。', token=token, details=details, folder=folder)
    return _response('规则写入未完成。请重新检查客户端并生成方案。', token=token, details=details)


def _native_apply(c, folder, record):
    c.require(record['phase'] == 'planned', 'TOOLS_NATIVE_PLAN_USED')
    _record(c, folder, record, 'apply_started')
    _remember(c, folder.parent, record)
    try:
        result = native_client.apply(c, folder / 'plan', record['plan_sha256'],
                                     folder / 'apply', allow=True, stopped=True)
    except c.SetupError:
        if _present(folder / 'apply'):
            return _native_status(c, folder, record)
        raise
    receipt = result.get('receipt_sha256')
    if result.get('status') == 'written_but_not_verified' and result.get('required_checks_completed') is True \
            and type(receipt) is str and DIGEST.fullmatch(receipt):
        _record(c, folder, record, 'applied', receipt_sha256=receipt)
    return _native_status(c, folder, record)


def _native_rollback(c, folder, record):
    c.require(record['phase'] == 'applied', 'TOOLS_NATIVE_RECEIPT_REQUIRED')
    _record(c, folder, record, 'rollback_started')
    _remember(c, folder.parent, record)
    try:
        result = native_client.rollback(c, folder / 'plan', record['plan_sha256'], folder / 'apply',
                                        record['receipt_sha256'], folder / 'rollback', allow=True, stopped=True)
    except c.SetupError:
        if _present(folder / 'rollback'):
            return _native_status(c, folder, record)
        _record(c, folder, record, 'applied')
        raise
    if result.get('recovery_state') == 'committed' and result.get('required_checks_completed') is True:
        _record(c, folder, record, 'rolled_back')
    return _native_status(c, folder, record)


def _export_guard(c, root, value, engine_prefix):
    path = _absolute(c, value)
    plan = _load(c, path, system_guard.MAX_INPUT)
    c.require(set(plan) == GUARD_PLAN_FIELDS, 'GUARD_PLAN_SCHEMA')
    system_guard.validate_plan(plan)
    trusted = guard_handoff.runtime_prefix(c)
    c.require(type(engine_prefix) in (tuple, list) and list(engine_prefix) == trusted, 'TOOLS_GUARD_RUNTIME_INVALID')
    folder, _ = _new(c, root, 'guard')
    system_guard.private_write(folder / 'plan.json', plan, True)
    source = Path(system_guard.__file__)
    for name in ('system_guard.py', 'system_guard_windows.ps1'):
        system_guard.private_write(folder / name, source.with_name(name).read_bytes(), True)
    handoff = guard_handoff.export_launchers(c, plan, folder, runtime_prefix=trusted)
    details = [f'目标平台 {plan["spec"]["platform"]}。', f'方案摘要 {system_guard.digest(plan)}。',
               '启用时需要在目标设备上重新确认。']
    message = '断线保护交接包已导出。'
    if not handoff['launcher_generated']:
        message = '断线保护方案已导出，请在目标系统生成启动器。'
    return _response(message, details=details, folder=folder)


def _export_remote(c, root, value):
    path = _absolute(c, value)
    plan = remote_setup.validate_plan(_load(c, path, remote_setup.MAX_JSON))
    pin = remote_setup.digest(plan)
    folder = root / ('remote-' + uuid.uuid4().hex)
    result = remote_setup.export_bundle(plan, pin, folder)
    return _response('VM／VPS 部署包已导出。', folder=folder,
                     details=[f'方案摘要 {pin}。', f'部署包摘要 {result["bundle_sha256"]}。',
                              '在目标系统审阅后，重新确认部署。'])


def dispatch(c, root, action, payload, engine_prefix):
    c.require(type(action) is str and action in FIELDS and type(payload) is dict and
              set(payload) == FIELDS[action], 'TOOLS_REQUEST_INVALID')
    if 'stopped' in payload:
        c.require(payload['stopped'] is True, 'TOOLS_STOPPED_CONFIRMATION_REQUIRED')
    root = storage._private_dir(c, root)
    try:
        if action == 'guard_export':
            return _export_guard(c, root, payload['path'], engine_prefix)
        if action == 'remote_export':
            return _export_remote(c, root, payload['path'])
        if action == 'native_inspect':
            return _native_inspect(c)
        if action == 'native_plan':
            return _native_plan(c, root, **payload)
        if action == 'cleanup_plan':
            return _cleanup_plan(c, root, payload['kind'], payload['path'])
        family, operation = action.split('_', 1)
        if operation == 'latest':
            folder, record = _latest(c, root, family)
            if not record:
                return _response('还没有此工具的操作记录。')
            status = _cleanup_status if family == 'cleanup' else _native_status
            return status(c, folder, record)
        folder, record = _read_record(c, root, family, payload['token'])
        handler = {'cleanup_apply': _cleanup_apply, 'cleanup_reconcile': _cleanup_reconcile,
                   'cleanup_restore': _cleanup_restore, 'native_apply': _native_apply,
                   'native_rollback': _native_rollback}[action]
        return handler(c, folder, record)
    except (system_guard.GuardError, remote_setup.RemoteError) as error:
        raise c.SetupError(str(error)) from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise c.SetupError('TOOLS_IO_OR_STATE_INVALID') from None
