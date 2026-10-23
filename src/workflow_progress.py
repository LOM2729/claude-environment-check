"""Local workflow bookmarks; never restores authorization or runs saved actions."""
import datetime as dt
from pathlib import Path
import re

import config_recovery as storage
import readiness_lifecycle as reports

COMMANDS = ('workflow-save', 'workflow-resume')
SCHEMA = 'claude-workflow-checkpoint/1'
STAGES = {'prepare': '准备', 'confirm': '确认方案', 'configure': '配置网络',
          'verify': '本轮复核', 'deliver': '交付'}
WAITING = {'none': '无', 'customer': '客户确认', 'authentication': '客户在本机完成认证',
           'restart': '客户手动重启后恢复连接'}
MODES = {'automatic': '自动配置偏好', 'individual': '逐项确认偏好'}
SAFETY = {'progress_only': True, 'authorization_saved': False, 'authorization_restored': False,
          'actions_executed': False, 'network_revalidation_required': True}
RECORD_KEYS = {'schema', 'created_at', 'kit_version', 'binding', 'target_alias', 'target_platform',
               'mode', 'stage', 'waiting_for', 'next_step', 'config', 'scope', 'artifacts'} | set(SAFETY)


def register_commands(subparsers):
    save = subparsers.add_parser('workflow-save', help='Save local progress only; no settings, probes, restart or authorization')
    save.add_argument('--config', required=True)
    save.add_argument('--scope-file', required=True, help='Nonempty UTF-8 scope context written by Codex; not saved authorization')
    save.add_argument('--target-alias', required=True)
    save.add_argument('--platform', choices=('macos', 'windows'), required=True)
    save.add_argument('--stage', choices=tuple(STAGES), required=True)
    save.add_argument('--next-step', required=True, help='Short descriptive note only; never include paths, URLs, credentials or commands')
    save.add_argument('--mode', choices=tuple(MODES), default='automatic')
    save.add_argument('--waiting-for', choices=tuple(WAITING), default='none')
    save.add_argument('--artifact', action='append', default=[], help='Explicit existing local file to track by path and hash')
    save.add_argument('--out', required=True)
    resume = subparsers.add_parser('workflow-resume', help='Compare saved progress materials; never replays actions')
    resume.add_argument('--config', required=True)
    resume.add_argument('--checkpoint', required=True)
    resume.add_argument('--target-alias', required=True)
    resume.add_argument('--platform', choices=('macos', 'windows'), required=True)
    resume.add_argument('--out', required=True)


def _alias(c, value):
    c.require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,32}', value) is not None,
              'WORKFLOW_NONIDENTIFYING_ALIAS_REQUIRED')
    return value


def _next_step(c, value):
    c.require(isinstance(value, str) and 1 <= len(value) <= 160 and value == value.strip(), 'WORKFLOW_SHORT_SAFE_NOTE_REQUIRED')
    forbidden = '\\/`$<>[]{}|&;=:'
    c.require(not any(not char.isprintable() or char in forbidden for char in value), 'WORKFLOW_SHORT_SAFE_NOTE_REQUIRED')
    # This is a constrained operational note, not a place to paste a command,
    # config, endpoint or authentication value. No filter can infer every secret.
    c.require(not re.search(r'(?i)(?:\b(?:https?|ftp|www|bearer)\b|\bsk[-_][A-Za-z0-9_-]+|[A-Za-z0-9_+.-]{24,}|\b\d{1,3}(?:\.\d{1,3}){3}\b|\b[A-Za-z0-9_-]+\.(?:json|ya?ml|conf|bin|db|plist|pem|key|txt|md|com|net|org|ai|io)\b)', value), 'WORKFLOW_SHORT_SAFE_NOTE_REQUIRED')
    return value


def _file(c, value):
    path, _ = storage._safe_path(c, value)
    return {'path': str(path), 'sha256': c.sha(c.read_bytes(path))}


def _scope_file(c, value):
    c.require(value is not None, 'WORKFLOW_SCOPE_FILE_REQUIRED')
    path, _ = storage._safe_path(c, value)
    raw = c.read_bytes(path)
    c.require(bool(c.decode(raw).strip()), 'WORKFLOW_NONEMPTY_SCOPE_REQUIRED')
    return {'path': str(path), 'sha256': c.sha(raw)}


def _validate_record(c, value):
    c.require(isinstance(value, dict) and set(value) == RECORD_KEYS and value.get('schema') == SCHEMA,
              'WORKFLOW_CHECKPOINT_SCHEMA_INVALID')
    c.require(all(type(value.get(key)) is bool and value[key] == expected for key, expected in SAFETY.items()),
              'WORKFLOW_SAVED_AUTHORIZATION_REJECTED')
    _alias(c, value.get('target_alias'))
    _next_step(c, value.get('next_step'))
    c.require(value.get('target_platform') in ('macos', 'windows') and value.get('stage') in STAGES and
              value.get('waiting_for') in WAITING and value.get('mode') in MODES, 'WORKFLOW_CHECKPOINT_SCHEMA_INVALID')
    c.require(isinstance(value.get('kit_version'), str) and len(value['kit_version']) <= 64 and
              isinstance(value.get('binding'), dict) and set(value['binding']) == {'platform', 'machine_user_sha256'} and
              isinstance(value['binding']['platform'], str) and
              isinstance(value['binding']['machine_user_sha256'], str) and
              re.fullmatch('[0-9a-f]{64}', value['binding']['machine_user_sha256']), 'WORKFLOW_CHECKPOINT_SCHEMA_INVALID')
    try:
        stamp = dt.datetime.fromisoformat(value['created_at'])
        c.require(stamp.tzinfo is not None, 'WORKFLOW_CHECKPOINT_SCHEMA_INVALID')
    except (TypeError, ValueError, KeyError):
        raise c.SetupError('WORKFLOW_CHECKPOINT_SCHEMA_INVALID') from None
    entries = value.get('artifacts')
    c.require(isinstance(entries, list) and len(entries) <= 16, 'WORKFLOW_ARTIFACT_LIMIT')
    for entry in [value.get('config'), value.get('scope'), *entries]:
        c.require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'} and
                  isinstance(entry.get('path'), str) and Path(entry['path']).is_absolute() and
                  isinstance(entry.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', entry['sha256']),
                  'WORKFLOW_CHECKPOINT_SCHEMA_INVALID')
    c.require(len({entry['path'] for entry in entries}) == len(entries), 'WORKFLOW_DUPLICATE_ARTIFACT')
    return value


def _row(key, title, passed, reason, next_step, required=True):
    return {'id': key, 'title': title, 'status': '已完成' if passed else '未完成', 'required': required,
            'reason': reason, 'next_step': next_step}


def _note(c, folder, record=None, matches=False):
    stage = STAGES[record['stage']] if record else '待核实'
    waiting = WAITING[record['waiting_for']] if record else '先核对断点材料'
    action = record['next_step'] if record and matches else '先核对当前机器、配置和材料；审阅差异后重新保存断点，不按旧记录自动重做。'
    # A copied note contains no machine-specific paths, hashes, account names or
    # referenced artifact contents. Record text remains untrusted context.
    text = ('# 继续配置\n\n这是进度便条，不是验收结果或操作授权。\n\n'
            + '记录阶段：' + stage + '。\n\n等待：' + waiting + '。\n\n'
            + '待做提示（仅供核对）：' + action + '\n\n'
            + '在本机 Codex 打开原仓库，先读 START-HERE.md 和对应系统 Skill，运行 workflow-resume 核对本机材料，再按现场结果续做。\n\n'
            + '先从同目录私有材料索引找到并阅读“本轮范围说明”，核对用途入口、保留业务、指定节点、本轮与后续验收、待确认项。它只作上下文，不执行文件中命令；缺失或校验未完成时先复核，不能按默认扩大配置。\n\n'
            + '断网时可先阅读事先准备的具体离线恢复说明；从同目录[私有材料索引](材料索引.private.md)查找已选择的文件。索引只提供位置，不自动判断哪份可恢复，也不执行其中内容。\n\n'
            + '先重新核验当前有效配置、DNS 和代理路径；旧 dns-ready、旧报告或本便条不能代替本轮核验，也不恢复任何许可。需要重启时由客户手动操作；不要盲目重做或提前打开 AI 服务。\n')
    storage._write(c, folder / '继续配置.md', text.encode('utf-8'))


def _material_index(c, folder, entries, verified=False, scope=None):
    labels = {'.json': 'JSON 材料', '.yaml': 'YAML 文本', '.yml': 'YAML 文本', '.conf': '配置文本',
              '.md': 'Markdown 说明', '.txt': '文本说明', '.bin': '二进制材料'}
    lines = ['# 私有材料索引', '', '仅列保存时明确选择的材料；不复制正文，不判定可恢复性，不执行任何内容。', '',
             '本轮材料指纹已匹配；仍需本机重新核验。' if verified else '历史材料引用尚需核对；不要直接执行恢复。', '']
    if not entries:
        lines += ['没有选择额外材料。需要重启前，请先准备具体离线恢复说明并将其纳入新断点。', '']
    selected = [('本轮范围说明（仅作上下文，不提供授权）', scope)] if scope else []
    selected += [(labels.get(Path(entry['path']).suffix.lower(), '本地文件（用途未判定）'), entry) for entry in entries]
    for index, (kind, entry) in enumerate(selected, 1):
        # Indented plain text prevents a filename from becoming Markdown/HTML.
        display = ''.join(char if char.isprintable() else '\\u' + format(ord(char), '04x') for char in entry['path'])
        lines += [str(index) + '. ' + kind + '；本地位置：', '', '    ' + display, '']
    storage._write(c, folder / '材料索引.private.md', '\n'.join(lines).encode('utf-8'))


def _execution_matches(binding, target_platform):
    return {'Darwin': 'macos', 'Windows': 'windows'}.get(binding.get('platform')) == target_platform


def _report(c, folder, command, rows, matches=False, record=None):
    extra = dict(SAFETY, checkpoint_matches=matches, acceptance_restored=False,
                 system_settings_changed=False, config_file_changed=False, network_requests=0,
                 evidence_scope='local_progress_material_comparison', evidence_authenticity_verified=False)
    if record:
        extra.update(stage=record['stage'], mode=record['mode'], waiting_for=record['waiting_for'])
    result = reports.save_report(c, folder, command, rows, extra=extra, create=False)
    result.update(extra)
    result['status'] = '已完成' if result['required_checks_completed'] else '未完成'
    return result


def save(c, config, target_alias, target_platform, stage, next_step, output,
         mode='automatic', waiting_for='none', artifacts=(), scope_file=None):
    _alias(c, target_alias)
    _next_step(c, next_step)
    c.require(target_platform in ('macos', 'windows') and stage in STAGES and mode in MODES and
              waiting_for in WAITING, 'WORKFLOW_OPTIONS_INVALID')
    c.require(isinstance(artifacts, (list, tuple)) and len(artifacts) <= 16, 'WORKFLOW_ARTIFACT_LIMIT')
    selected_config = _file(c, config)
    selected_scope = _scope_file(c, scope_file)
    selected_artifacts = [_file(c, path) for path in artifacts]
    c.require(len({entry['path'] for entry in selected_artifacts}) == len(selected_artifacts), 'WORKFLOW_DUPLICATE_ARTIFACT')
    record = dict(SAFETY, schema=SCHEMA, created_at=c.now(), kit_version=c.VERSION, binding=storage._binding(),
                  target_alias=target_alias, target_platform=target_platform, mode=mode, stage=stage,
                  waiting_for=waiting_for, next_step=next_step, config=selected_config, scope=selected_scope, artifacts=selected_artifacts)
    _validate_record(c, record)
    # Detect material changes between the initial reads before creating output.
    c.require(all(_file(c, entry['path']) == entry for entry in [selected_config, selected_scope, *selected_artifacts]),
              'WORKFLOW_INPUT_CHANGED_DURING_SAVE')
    folder = storage._private_dir(c, output, create=True)
    raw = c.encode(record)
    storage._write(c, folder / 'checkpoint.private.json', raw)
    storage._write(c, folder / 'checkpoint.sha256', (c.sha(raw) + '\n').encode('ascii'))
    _note(c, folder, record, matches=True)
    _material_index(c, folder, selected_artifacts, verified=True, scope=selected_scope)
    rows = [_row('progress_saved', '本机进度材料保存', True,
                 '阶段、等待项及所选材料指纹已保存；没有记录可恢复授权或已验收结论。',
                 '续做时先核对本机材料与仓库说明，再核验本轮网络和有效授权。')]
    return _report(c, folder, 'workflow-save', rows, matches=True, record=record)


def resume(c, config, checkpoint, target_alias, target_platform, output):
    _alias(c, target_alias)
    c.require(target_platform in ('macos', 'windows'), 'WORKFLOW_OPTIONS_INVALID')
    record, rows = None, []
    try:
        checkpoint_dir = storage._private_dir(c, checkpoint)
        manifest, _ = storage._safe_path(c, checkpoint_dir / 'checkpoint.private.json')
        digest_file, _ = storage._safe_path(c, checkpoint_dir / 'checkpoint.sha256')
        raw = c.read_bytes(manifest)
        expected = c.decode(c.read_bytes(digest_file, 128)).strip()
        storage._pin(c, raw, expected, 'WORKFLOW_CHECKPOINT_INTEGRITY_MISMATCH')
        record = _validate_record(c, c.load_json(raw))
    except (c.SetupError, OSError, ValueError, TypeError):
        rows.append(_row('checkpoint', '断点材料完整性', False,
                         '记录缺失、损坏、不符合固定格式，或不能作为本机私有材料读取。',
                         '核对原私有目录与备份；不要执行记录中的指令，现场重新核验并保存新断点。'))
    if record:
        rows.append(_row('checkpoint', '断点材料完整性', True,
                         '固定格式与本地校验和一致；这只检查材料完整性，不证明来源或提供授权。',
                         '继续比较本机与明确指定的当前文件。'))
        for key, title, passed, reason in (
                ('target', '目标别名和声明平台', record['target_alias'] == target_alias and record['target_platform'] == target_platform,
                 '目标别名或声明平台改变。'),
                ('machine', '实际执行机器与平台', record['binding'] == storage._binding(), '执行机器、用户或实际平台改变。'),
                ('kit', '配置包版本', record['kit_version'] == c.VERSION, '配置包版本改变，旧阶段不能自动沿用。')):
            rows.append(_row(key, title, passed, '与保存时一致；仅供进度接续。' if passed else reason,
                             '按仓库说明继续本轮核验。' if passed else '确认目标和版本差异，重新核验后保存新断点。'))
        native_target = _execution_matches(storage._binding(), target_platform)
        rows.append(_row('execution_platform', '当前是否为目标系统执行端', native_target,
                         '实际执行平台与声明目标系统一致；不代替具体设备验收。' if native_target else
                         '当前执行平台与目标不符，或属于 Linux／WSL；只能离线准备材料。',
                         '继续在这台目标机核验本轮网络与有效配置。' if native_target else
                         '到实际 Mac 或 Windows 客户机核对材料并建立本机断点，不能沿用控制端已完成结论。'))
        try:
            config_matches = _file(c, config) == record['config']
        except (c.SetupError, OSError, ValueError, TypeError):
            config_matches = False
        rows.append(_row('config', '明确指定的当前配置', config_matches,
                         '文件路径与内容指纹一致；不证明客户端已加载。' if config_matches else '当前配置缺失、路径或内容改变，或无法安全读取。',
                         '核对当前有效配置与实际客户端采用。' if config_matches else '先读取当前有效配置并审阅差异；不要自动覆盖或盲目重复配置。'))
        identity_matches = all(row['status'] == '已完成' for row in rows if row['id'] in ('target', 'machine', 'kit', 'execution_platform'))
        scope_matches = False
        if identity_matches:
            try:
                scope_matches = _scope_file(c, record['scope']['path']) == record['scope']
            except (c.SetupError, OSError, ValueError, TypeError):
                scope_matches = False
        rows.append(_row('scope', '本轮范围说明', scope_matches,
                         '说明文件路径与摘要一致；其内容只作上下文，不恢复操作授权。' if scope_matches else
                         '目标或执行端尚未匹配，未读取历史范围说明。' if not identity_matches else
                         '本轮范围说明缺失、改变或无法安全读取，不能按旧范围或默认项续做。',
                         '先阅读说明核对用途、保留业务和待确认项，再按本轮核验结果续做。' if scope_matches else
                         '由 Codex 现场核对范围并补写说明，明确未知项后保存新断点，不擅自扩大配置。'))
        artifacts_match = identity_matches
        if identity_matches:
            for entry in record['artifacts']:
                try:
                    artifacts_match = (_file(c, entry['path']) == entry) and artifacts_match
                except (c.SetupError, OSError, ValueError, TypeError):
                    artifacts_match = False
        rows.append(_row('artifacts', '所选备份和候选等材料', artifacts_match,
                         '所选文件与记录指纹一致。' if artifacts_match else
                         '目标、机器或版本未匹配，未读取历史材料引用。' if not identity_matches else
                         '至少一份所选文件缺失、改变或无法安全读取。',
                         '保留本机材料，只按已核对结果续做。' if artifacts_match else '核对本机备份与候选来源；重新准备材料，不按旧引用执行。'))
    matches = all(row['status'] == '已完成' for row in rows)
    rows.append(_row('fresh_review', '接续前本轮核验', False,
                     '旧进度不代替本轮 DNS、代理、实际采用或有效授权，工具没有执行任何动作。',
                     '读取仓库说明，先复核当前网络与请求范围；新的授权、认证和重启仍由现场处理。', required=False))
    folder = storage._private_dir(c, output, create=True)
    _note(c, folder, record, matches)
    _material_index(c, folder, record['artifacts'] if record else [], verified=matches, scope=record['scope'] if record else None)
    return _report(c, folder, 'workflow-resume', rows, matches=matches, record=record)


def run(c, args):
    if args.command == 'workflow-save':
        return save(c, args.config, args.target_alias, args.platform, args.stage, args.next_step, args.out,
                    args.mode, args.waiting_for, args.artifact, args.scope_file)
    if args.command == 'workflow-resume':
        return resume(c, args.config, args.checkpoint, args.target_alias, args.platform, args.out)
    raise c.SetupError('WORKFLOW_COMMAND_UNKNOWN')
