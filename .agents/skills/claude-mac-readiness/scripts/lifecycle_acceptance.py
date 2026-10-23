"""Offline lifecycle evidence review; never collects, authenticates or changes a network.

The operator records actual events and correlated client observations in private
receipts. A valid receipt is an evidence contract, not proof that its author was
truthful. Opaque source files are checked for integrity, not interpreted as a
packet capture. Imported records never authorize a restart or fault experiment.
"""
import datetime as dt
from pathlib import Path
import platform
import re
import uuid

import readiness_lifecycle as life

COMMANDS = ('lifecycle-template', 'lifecycle-accept')
SCHEMA = 'claude-lifecycle-acceptance/2'
LEGACY_SCHEMA = 'claude-lifecycle-acceptance/1'
CLIENTS = {'browser': '浏览器', 'terminal': '终端', 'claude_gui': 'Claude 桌面端',
           'codex_gui': 'Codex 桌面端', 'claude_cli': 'Claude CLI',
           'codex_cli': 'Codex CLI', 'background': '所选后台进程'}
EVENTS = {'normal_use': '当前正常使用', 'client_update': '客户端更新后',
          'proxy_update': '代理更新后', 'client_restart': '客户端重启后',
          'system_restart': '系统重启后', 'sleep_wake': '睡眠唤醒后',
          'network_change': '换网后', 'proxy_fault_recovery': '代理故障与恢复'}
CHECKS = ('function', 'proxy_path', 'dns_path', 'udp_path', 'ipv6_path')
CHECK_TITLES = {'function': '实际功能', 'proxy_path': '指定代理路径', 'dns_path': 'DNS 路径',
                'udp_path': 'UDP 路径或阻断', 'ipv6_path': 'IPv6 路径或关闭'}
KINDS = {'client_observation', 'correlated_runtime_flow', 'correlated_dns_flow',
         'packet_metadata', 'core_block_log', 'native_interface_readback',
         'native_event_log', 'version_readback', 'operator_event_record',
         'network_report', 'recheck_report', 'preflight_report', 'static', 'synthetic'}
OUTCOMES = {'worked', 'designated_proxy', 'through_proxy', 'blocked', 'disabled_verified',
            'timeout', 'no_ipv6', 'no_traffic', 'not_checked', 'failed', 'direct', 'unknown'}
HASH = re.compile(r'[0-9a-f]{64}')
IDENTIFIER = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}')
MAX_AGE = dt.timedelta(days=7)


def register_commands(subparsers):
    for command in COMMANDS:
        parser = subparsers.add_parser(command, help='Offline lifecycle evidence template or review; no network or settings changes')
        parser.add_argument('--config', required=True)
        parser.add_argument('--target-alias', required=True)
        parser.add_argument('--platform', choices=('macos', 'windows'), required=True,
                            help='Actual target platform, distinct from this tool execution platform')
        parser.add_argument('--out', required=True)
        if command == 'lifecycle-template':
            parser.add_argument('--client', action='append', choices=tuple(CLIENTS), required=True,
                                help='Only client families actually in the agreed target scope; repeat as needed')
            parser.add_argument('--required-event', action='append', choices=tuple(EVENTS),
                                help='Additional events required for this delivery; normal_use is always required')
        else:
            parser.add_argument('--input', required=True)
            parser.add_argument('--evidence-dir', help='Explicit local root for private relative receipt/source files; defaults to input parent')


def _keys(c, value, expected, code='LIFECYCLE_SCHEMA_INVALID'):
    c.require(isinstance(value, dict) and set(value) == set(expected), code)


def _time(c, value):
    try:
        c.require(isinstance(value, str) and len(value) <= 40, 'LIFECYCLE_TIME_INVALID')
        result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        c.require(result.tzinfo is not None, 'LIFECYCLE_TIME_INVALID')
        return result.astimezone(dt.timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise c.SetupError('LIFECYCLE_TIME_INVALID') from None


def _hash(c, value):
    c.require(isinstance(value, str) and HASH.fullmatch(value), 'LIFECYCLE_HASH_INVALID')


def _id(c, value):
    c.require(isinstance(value, str) and IDENTIFIER.fullmatch(value), 'LIFECYCLE_ID_INVALID')


def _execution_platform():
    return {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}.get(platform.system(), 'other')


def _binding(c, config, target, target_platform):
    _id(c, target)
    c.require(target_platform in ('macos', 'windows'), 'LIFECYCLE_PLATFORM_INVALID')
    return {'config_sha256': c.sha(c.read_bytes(config)), 'target_alias': target,
            'target_platform': target_platform, 'execution_id': life.machine_id(c),
            'execution_platform': _execution_platform()}


def _required_events(c, events):
    c.require(isinstance(events, list) and len(events) <= len(EVENTS)
              and all(isinstance(x, str) and x in EVENTS for x in events)
              and len(set(events)) == len(events), 'LIFECYCLE_REQUIRED_EVENTS_INVALID')
    return [event for event in EVENTS if event == 'normal_use' or event in events]


def _record_required_events(record):
    # Older records described one all-required acceptance run. Never silently
    # reinterpret their unfinished events as follow-up-only work.
    return list(EVENTS) if record['schema'] == LEGACY_SCHEMA else record['required_events']


def template(c, config, target, target_platform, clients, output, required_events=None):
    c.require(isinstance(clients, list) and clients and len(clients) <= len(CLIENTS)
              and all(isinstance(x, str) and x in CLIENTS for x in clients) and len(set(clients)) == len(clients), 'LIFECYCLE_CLIENT_SCOPE_INVALID')
    created = _time(c, c.now())
    required = _required_events(c, [] if required_events is None else required_events)
    binding = _binding(c, config, target, target_platform)
    binding['required_events_sha256'] = c.sha(c.encode(required))
    record = {'schema': SCHEMA, 'record_id': uuid.uuid4().hex, 'created_at': created.isoformat(),
              'expires_at': (created + MAX_AGE).isoformat(), 'binding': binding,
              'clients': list(clients), 'required_events': required, 'events': []}
    for event in EVENTS:
        record['events'].append({'id': event, 'state': 'not_performed', 'instance_id': None,
                                 'started_at': None, 'ended_at': None, 'event_receipt': None,
                                 'observations': [{'client': client, 'receipt': None} for client in clients]})
    c.new_dir(output)
    c.write_new(Path(output) / 'lifecycle-record.private.json', c.encode(record))
    return {'status': 'private_lifecycle_template_written', 'events': len(EVENTS), 'clients': len(clients),
            'required_events': required, 'followup_events': [event for event in EVENTS if event not in required],
            'completed': 0, 'required_checks_completed': False,
            'network_requests': 0, 'system_settings_changed': False,
            'evidence_authenticity_verified': False}


def _record(c, value):
    c.require(isinstance(value, dict) and value.get('schema') in (SCHEMA, LEGACY_SCHEMA), 'LIFECYCLE_SCHEMA_INVALID')
    modern = value['schema'] == SCHEMA
    fields = ('schema', 'record_id', 'created_at', 'expires_at', 'binding', 'clients', 'events')
    _keys(c, value, fields + (('required_events',) if modern else ()))
    _id(c, value['record_id'])
    binding = value['binding']
    binding_fields = ('config_sha256', 'target_alias', 'target_platform', 'execution_id', 'execution_platform')
    _keys(c, binding, binding_fields + (('required_events_sha256',) if modern else ()))
    if modern:
        required = _required_events(c, value['required_events'])
        c.require(required == value['required_events'], 'LIFECYCLE_REQUIRED_EVENTS_INVALID')
        _hash(c, binding['required_events_sha256'])
        c.require(binding['required_events_sha256'] == c.sha(c.encode(required)), 'LIFECYCLE_REQUIRED_EVENTS_BINDING_MISMATCH')
    _id(c, binding['target_alias'])
    for key in ('config_sha256', 'execution_id'):
        _hash(c, binding[key])
    c.require(binding['target_platform'] in ('macos', 'windows') and binding['execution_platform'] in
              ('macos', 'windows', 'linux', 'other'), 'LIFECYCLE_PLATFORM_INVALID')
    created, expires = _time(c, value['created_at']), _time(c, value['expires_at'])
    c.require(expires == created + MAX_AGE, 'LIFECYCLE_VALIDITY_INVALID')
    clients = value['clients']
    c.require(isinstance(clients, list) and clients and len(clients) <= len(CLIENTS)
              and all(isinstance(x, str) and x in CLIENTS for x in clients)
              and len(set(clients)) == len(clients), 'LIFECYCLE_CLIENT_SCOPE_INVALID')
    events = value['events']
    c.require(isinstance(events, list) and len(events) == len(EVENTS), 'LIFECYCLE_EVENTS_REQUIRED')
    c.require(all(isinstance(x, dict) and isinstance(x.get('id'), str) for x in events), 'LIFECYCLE_SCHEMA_INVALID')
    c.require({x['id'] for x in events} == set(EVENTS), 'LIFECYCLE_EVENTS_REQUIRED')
    for event in events:
        _keys(c, event, ('id', 'state', 'instance_id', 'started_at', 'ended_at', 'event_receipt', 'observations'))
        c.require(event['state'] in ('not_performed', 'performed', 'declined'), 'LIFECYCLE_EVENT_STATE_INVALID')
        observations = event['observations']
        c.require(isinstance(observations, list) and len(observations) == len(clients), 'LIFECYCLE_CLIENT_SCOPE_INVALID')
        for observation in observations:
            _keys(c, observation, ('client', 'receipt'))
            c.require(isinstance(observation['client'], str) and observation['client'] in clients, 'LIFECYCLE_CLIENT_SCOPE_INVALID')
        c.require({x['client'] for x in observations} == set(clients), 'LIFECYCLE_CLIENT_SCOPE_INVALID')
        if event['state'] == 'performed':
            _id(c, event['instance_id'])
            _time(c, event['started_at'])
            _time(c, event['ended_at'])
        else:
            c.require(all(event[k] is None for k in ('instance_id', 'started_at', 'ended_at', 'event_receipt'))
                      and all(x['receipt'] is None for x in observations), 'LIFECYCLE_PENDING_EVIDENCE_CONFLICT')
    return value


def _source(c, root, ref):
    _keys(c, ref, ('file', 'sha256'), 'LIFECYCLE_SOURCE_INVALID')
    _hash(c, ref['sha256'])
    name = ref['file']
    c.require(isinstance(name, str) and 0 < len(name) <= 200 and '\\' not in name and ':' not in name,
              'LIFECYCLE_SOURCE_INVALID')
    relative = Path(name)
    c.require(not relative.is_absolute() and all(x not in ('.', '..') for x in relative.parts)
              and all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', x) for x in relative.parts), 'LIFECYCLE_SOURCE_INVALID')
    # Explicit caller root is the only source of paths, never absolute paths from imported records.
    path = root
    c.require(path.is_dir() and not path.is_symlink(), 'LIFECYCLE_SOURCE_INVALID')
    for part in relative.parts:
        path = path / part
        c.require(not path.is_symlink(), 'LIFECYCLE_SOURCE_INVALID')
    raw = c.read_bytes(path)
    c.require(c.sha(raw) == ref['sha256'], 'LIFECYCLE_SOURCE_CHANGED')
    return raw


def _receipt(c, root, reference, schema, record, event, now):
    receipt = c.load_json(_source(c, root, reference))
    c.require(isinstance(receipt, dict) and receipt.get('schema') == schema, 'LIFECYCLE_RECEIPT_SCHEMA_INVALID')
    c.require(receipt.get('record_id') == record['record_id'] and receipt.get('binding') == record['binding']
              and receipt.get('event_id') == event['id'] and receipt.get('event_instance_id') == event['instance_id'],
              'LIFECYCLE_RECEIPT_BINDING_MISMATCH')
    c.require(receipt.get('evidence_mode') in ('observed', 'synthetic', 'static', 'unknown'), 'LIFECYCLE_EVIDENCE_MODE_INVALID')
    observed = _time(c, receipt.get('observed_at'))
    start, end = _time(c, event['started_at']), _time(c, event['ended_at'])
    c.require(_time(c, record['created_at']) <= start <= observed <= end <= now
              and now - observed <= MAX_AGE, 'LIFECYCLE_EVIDENCE_TIME_MISMATCH')
    c.require(receipt['evidence_mode'] == 'observed', 'LIFECYCLE_REAL_EVIDENCE_REQUIRED')
    return receipt


def _artifact(c, root, source):
    _keys(c, source, ('kind', 'artifact'))
    c.require(isinstance(source['kind'], str) and source['kind'] in KINDS, 'LIFECYCLE_SOURCE_KIND_INVALID')
    _source(c, root, source['artifact'])
    return source['kind']


def _event_evidence(c, root, record, event, now):
    r = _receipt(c, root, event['event_receipt'], 'claude-lifecycle-event/1', record, event, now)
    _keys(c, r, ('schema', 'record_id', 'binding', 'event_id', 'event_instance_id', 'evidence_mode',
                 'observed_at', 'source', 'details'))
    kind = _artifact(c, root, r['source'])
    c.require(kind in ('native_event_log', 'version_readback', 'operator_event_record'), 'LIFECYCLE_ACTUAL_EVENT_REQUIRED')
    details = r['details']
    event_id = event['id']
    if event_id == 'normal_use':
        _keys(c, details, ('actual_use_observed',))
        c.require(details['actual_use_observed'] is True, 'LIFECYCLE_ACTUAL_EVENT_REQUIRED')
    elif event_id in ('client_update', 'proxy_update'):
        _keys(c, details, ('before_version_sha256', 'after_version_sha256'))
        for x in details.values():
            _hash(c, x)
        c.require(details['before_version_sha256'] != details['after_version_sha256'], 'LIFECYCLE_ACTUAL_EVENT_REQUIRED')
    elif event_id == 'client_restart':
        _keys(c, details, ('client_instances',))
        instances = details['client_instances']
        _keys(c, instances, record['clients'])
        for identity in instances.values():
            _keys(c, identity, ('before_sha256', 'after_sha256'))
            for x in identity.values():
                _hash(c, x)
            c.require(identity['before_sha256'] != identity['after_sha256'], 'LIFECYCLE_ACTUAL_EVENT_REQUIRED')
    elif event_id in ('system_restart', 'network_change'):
        _keys(c, details, ('before_identity_sha256', 'after_identity_sha256'))
        for x in details.values():
            _hash(c, x)
        c.require(details['before_identity_sha256'] != details['after_identity_sha256'], 'LIFECYCLE_ACTUAL_EVENT_REQUIRED')
    elif event_id == 'sleep_wake':
        _keys(c, details, ('sleep_at', 'wake_at'))
        c.require(_time(c, event['started_at']) <= _time(c, details['sleep_at']) < _time(c, details['wake_at'])
                  <= _time(c, r['observed_at']), 'LIFECYCLE_ACTUAL_EVENT_REQUIRED')
    else:
        _keys(c, details, ('healthy_before_at', 'fault_started_at', 'fault_ended_at', 'recovered_at',
                          'healthy_before', 'fault_observed', 'recovery_observed', 'fault_attempt_observed',
                          'fault_block_outcome', 'fault_block_evidence', 'fault_clients'))
        c.require(all(details[x] is True for x in ('healthy_before', 'fault_observed', 'recovery_observed', 'fault_attempt_observed')),
                  'LIFECYCLE_FAULT_BASELINE_REQUIRED')
        c.require(details['fault_block_outcome'] == 'blocked', 'LIFECYCLE_BLOCK_EVIDENCE_REQUIRED')
        c.require(_time(c, event['started_at']) <= _time(c, details['healthy_before_at']) <
                  _time(c, details['fault_started_at']) < _time(c, details['fault_ended_at']) <=
                  _time(c, details['recovered_at']) <= _time(c, r['observed_at']), 'LIFECYCLE_FAULT_SEQUENCE_INVALID')
        c.require(_artifact(c, root, details['fault_block_evidence']) in ('packet_metadata', 'core_block_log'),
                  'LIFECYCLE_BLOCK_EVIDENCE_REQUIRED')
        _keys(c, details['fault_clients'], record['clients'])
        for block in details['fault_clients'].values():
            _keys(c, block, ('process_identity_sha256', 'healthy_before', 'attempt_observed', 'outcome', 'source'))
            _hash(c, block['process_identity_sha256'])
            c.require(block['healthy_before'] is True and block['attempt_observed'] is True
                      and block['outcome'] == 'blocked', 'LIFECYCLE_CLIENT_BLOCK_EVIDENCE_REQUIRED')
            c.require(_artifact(c, root, block['source']) in ('packet_metadata', 'core_block_log'),
                      'LIFECYCLE_CLIENT_BLOCK_EVIDENCE_REQUIRED')
        fault_processes = [block['process_identity_sha256'] for block in details['fault_clients'].values()]
        c.require(len(set(fault_processes)) == len(fault_processes), 'LIFECYCLE_DISTINCT_PROCESS_EVIDENCE_REQUIRED')
    return r


def _observation(c, root, record, event, client, reference, now, event_receipt):
    r = _receipt(c, root, reference, 'claude-lifecycle-observation/1', record, event, now)
    _keys(c, r, ('schema', 'record_id', 'binding', 'event_id', 'event_instance_id', 'evidence_mode',
                 'observed_at', 'client', 'process_identity_sha256', 'proofs'))
    c.require(r['client'] == client, 'LIFECYCLE_CLIENT_EVIDENCE_MISMATCH')
    _hash(c, r['process_identity_sha256'])
    if event['id'] == 'client_restart':
        c.require(r['process_identity_sha256'] == event_receipt['details']['client_instances'][client]['after_sha256'],
                  'LIFECYCLE_RESTART_PROCESS_MISMATCH')
    if event['id'] == 'proxy_fault_recovery':
        c.require(_time(c, r['observed_at']) >= _time(c, event_receipt['details']['recovered_at']), 'LIFECYCLE_RECOVERY_EVIDENCE_REQUIRED')
    proofs = r['proofs']
    c.require(isinstance(proofs, list) and len(proofs) <= len(CHECKS), 'LIFECYCLE_PROOFS_INVALID')
    results = {key: False for key in CHECKS}
    seen = set()
    for proof in proofs:
        _keys(c, proof, ('check', 'outcome', 'source'))
        key, outcome = proof['check'], proof['outcome']
        c.require(isinstance(key, str) and key in CHECKS and key not in seen
                  and isinstance(outcome, str) and outcome in OUTCOMES, 'LIFECYCLE_PROOF_ENUM_INVALID')
        seen.add(key)
        kind = _artifact(c, root, proof['source'])
        results[key] = ((key == 'function' and outcome == 'worked' and kind == 'client_observation') or
                        (key == 'proxy_path' and outcome == 'designated_proxy' and kind == 'correlated_runtime_flow') or
                        (key == 'dns_path' and outcome == 'through_proxy' and kind == 'correlated_dns_flow') or
                        (key in ('udp_path', 'ipv6_path') and outcome in ('blocked', 'designated_proxy') and
                         kind in ('packet_metadata', 'core_block_log', 'correlated_runtime_flow')) or
                        (key == 'ipv6_path' and outcome == 'disabled_verified' and kind == 'native_interface_readback'))
    return results, r['process_identity_sha256']


def accept(c, config, input_file, target, target_platform, output, evidence_dir=None):
    record = _record(c, c.load_json(c.read_bytes(input_file)))
    required = _record_required_events(record)
    actual = _binding(c, config, target, target_platform)
    now = _time(c, c.now())
    root = Path(evidence_dir).absolute() if evidence_dir else Path(input_file).absolute().parent
    reason = None
    if record['binding']['target_alias'] != target or record['binding']['target_platform'] != target_platform:
        reason = '记录属于其他目标或系统平台，不能用于本机验收。'
    elif actual['execution_platform'] != target_platform:
        reason = '当前执行平台不是指定目标系统，只能离线准备材料，不能代替目标机实际验收。'
    elif record['binding']['config_sha256'] != actual['config_sha256']:
        reason = '当前配置与记录绑定的配置不同，旧验收不能沿用。'
    elif record['binding']['execution_id'] != actual['execution_id'] or record['binding']['execution_platform'] != actual['execution_platform']:
        reason = '执行机已变化，不能将其他机器的记录当作当前目标证据。'
    elif not _time(c, record['created_at']) <= now <= _time(c, record['expires_at']):
        reason = '模板已过期或创建时间在未来，不能沿用。'
    rows, matrix = [], []
    for event in record['events']:
        completed, failures, details = False, [], []
        if reason:
            failure = reason
        elif event['state'] != 'performed':
            failure = '客户未选择执行该事件，保留未完成。' if event['state'] == 'declined' else '本轮尚未发生或观察该事件。'
        else:
            try:
                event_receipt = _event_evidence(c, root, record, event, now)
                identities = set()
                for observation in event['observations']:
                    client = observation['client']
                    try:
                        checks, identity = _observation(c, root, record, event, client, observation['receipt'], now, event_receipt)
                        c.require(identity not in identities, 'LIFECYCLE_DISTINCT_PROCESS_EVIDENCE_REQUIRED')
                        identities.add(identity)
                        missing = [CHECK_TITLES[key] for key, passed in checks.items() if not passed]
                        if missing:
                            failures.append(CLIENTS[client] + '缺少' + '、'.join(missing))
                        details.append({'client': client, 'checks': checks})
                    except c.SetupError:
                        failures.append(CLIENTS[client] + '的证据缺失、无效或与本事件不匹配')
                        details.append({'client': client, 'checks': {key: False for key in CHECKS}})
                completed = not failures
                failure = '；'.join(failures) + '。' if failures else ''
            except c.SetupError:
                failure = '缺少有效的实际事件证据，或事件时间、来源、目标绑定不符；静态声明和合成材料不能代替。'
        result = '所选客户端的实际功能与各路径证据齐全；仅代表本次提供的证据范围。' if completed else failure
        action = '保留本机证据；配置、版本或网络变化后重新核验。' if completed else (
            '为当前目标和配置新建记录，再补充实际事件及逐客户端证据。' if reason else
            'Codex 按已授权范围补充本事件证据；重启、换网或故障实验由客户决定并手动操作，未授权则保留未完成。')
        rows.append(life.item('lifecycle_' + event['id'], EVENTS[event['id']], completed, result, action,
                              required=event['id'] in required))
        matrix.append({'event': event['id'], 'details': details, 'completed': completed, 'required': event['id'] in required})
    if c.sha(c.read_bytes(config)) != actual['config_sha256']:
        rows = [life.item(row['id'], row['title'], False, '验收期间配置发生变化，本轮结果不能沿用。',
                          '读回当前配置并新建绑定记录，再按实际范围验收。', required=row['required']) for row in rows]
        for entry in matrix:
            entry['completed'] = False
    return life.save_report(c, output, 'lifecycle-acceptance', rows,
        extra={'evidence_authenticity_verified': False, 'evidence_review_only': True,
               'network_requests': 0, 'target_platform': target_platform, 'runtime_adoption_verified': False,
               'required_events': required, 'followup_events': [event for event in EVENTS if event not in required],
               'scope_note': '仅判定所提供证据的完整性与绑定，不自行采集或认证真实性；不提供持续阻断或新操作授权。'},
        private={'record_id': record['record_id'], 'binding': record['binding'], 'matrix': matrix})


def run(c, args):
    if args.command == 'lifecycle-template':
        return template(c, args.config, args.target_alias, args.platform, args.client, args.out, args.required_event)
    c.require(args.command == 'lifecycle-accept', 'LIFECYCLE_COMMAND_INVALID')
    return accept(c, args.config, args.input, args.target_alias, args.platform, args.out, args.evidence_dir)
