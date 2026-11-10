"""Task-specific offline intake; facts and progress never grant execution rights."""
import copy
import re
import uuid

COMMANDS = ('intake-start', 'intake-answer', 'intake-assess')
MUTATING_COMMANDS = ()
SCHEMA = 'claude-task-intake/1'
STATES = ('known', 'unknown', 'declined', 'deferred', 'conflict', 'stale')
TASKS = ('setup', 'diagnose', 'cleanup', 'compare', 'maintenance', 'hardening',
         'remote', 'billing', 'subscribe')
VALUES = {
    'task': TASKS,
    'stage': ('first', 'returning', 'existing'),
    'platform': ('macos', 'windows', 'linux'),
    'route': ('local', 'vm', 'vps'),
    'namespace': ('native', 'wsl', 'vm_guest', 'remote'),
    'client': ('browser', 'desktop', 'code', 'ide_code', 'mixed'),
    'priority': ('simplicity', 'isolation', 'cost', 'performance'),
    'proxy': ('available', 'none'),
    'configuration': ('absent', 'imported', 'effective'),
    'issue': ('dns', 'connection', 'tls', 'login', 'permission', 'rate_limit',
              'service_error', 'billing', 'unclear'),
    'cleanup_category': ('cache', 'login', 'history', 'configuration', 'uninstall'),
    'cleanup_scope': ('site', 'profile', 'client_root'),
    'maintenance': ('update', 'reinstall', 'repair'),
    'payment_channel': ('web', 'apple', 'google', 'api', 'other'),
    'billing_issue': ('missing_entitlement', 'duplicate_charge', 'plan_mismatch', 'renewal'),
    'plan': ('free', 'pro', 'max', 'api', 'undecided'),
}
FIELDS = set(VALUES) | {'target_ref'}
SOURCES = ('user', 'target_observation', 'document')
QUESTIONS = {
    'task': '本轮要配置、排障、清理、比较路线，还是处理其他事项？',
    'stage': '目前是首次准备、重新准备，还是已有订阅？',
    'platform': '实际目标使用什么系统？',
    'route': '本轮程序准备运行在本机、虚拟机还是VPS？',
    'namespace': '本轮入口在原生系统、WSL、虚拟机客机还是远端？',
    'client': '本轮实际使用网页、Desktop、Code还是IDE？',
    'priority': '比较路线时，最看重省事、隔离、成本还是性能？',
    'proxy': '本轮是否已有准备使用的代理资源？',
    'configuration': '现有配置尚未导入、已经导入，还是确认正在生效？',
    'issue': '当前具体卡在连接、认证、额度还是其他步骤？',
    'cleanup_category': '默认仅缓存；本轮是否明确需要处理登录、历史、配置或卸载？',
    'cleanup_scope': '目标是指定站点、指定浏览器资料，还是客户端配置根？',
    'maintenance': '本轮要更新、重装还是修复程序？',
    'payment_channel': '原购买渠道是哪一个？',
    'billing_issue': '当前是权益未到账、重复扣款、套餐不符还是续费问题？',
    'plan': '当前考虑哪个套餐，还是尚未决定？',
}
REFERENCES = {
    'setup': ('five-step-setup.md',),
    'diagnose': ('incident-and-cleanup.md',),
    'cleanup': ('browser-cleanup.md', 'client-cleanup.md'),
    'compare': ('deployment-routes.md',),
    'maintenance': ('client-cleanup.md', 'execution-capabilities.md'),
    'hardening': ('execution-capabilities.md', 'recovery-and-acceptance.md'),
    'remote': ('deployment-routes.md', 'execution-capabilities.md'),
    'billing': ('billing-checks.md',),
    'subscribe': ('account-preparation.md',),
}
TASK_FIELDS = {
    'setup': ('platform', 'route', 'client', 'proxy', 'configuration'),
    'diagnose': ('platform', 'client', 'issue'),
    'cleanup': ('platform', 'client', 'cleanup_category', 'cleanup_scope'),
    'compare': ('platform', 'priority'),
    'maintenance': ('platform', 'client', 'maintenance'),
    'hardening': ('platform', 'route', 'proxy', 'configuration'),
    'remote': ('platform', 'route', 'configuration'),
    'billing': ('payment_channel', 'billing_issue'),
    'subscribe': ('stage', 'platform', 'plan'),
}
INCIDENTS = frozenset({'permission', 'rate_limit', 'service_error', 'billing'})


def _require(c, condition, code='INTAKE_STATE_INVALID'):
    c.require(condition, code)


def _value(c, field, value):
    if field == 'target_ref':
        _require(c, type(value) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', value)
                 and not re.fullmatch(r'[0-9a-fA-F]{24,}', value), 'INTAKE_ALIAS_INVALID')
    else:
        _require(c, type(value) is str and value in VALUES[field], 'INTAKE_VALUE_INVALID')


def _fact(c, field, fact):
    _require(c, field in FIELDS and type(fact) is dict
             and set(fact) == {'state', 'value', 'source', 'revision', 'alternatives'})
    _require(c, fact['state'] in STATES and fact['source'] in SOURCES
             and type(fact['revision']) is int and fact['revision'] >= 0)
    _require(c, type(fact['alternatives']) is list and len(fact['alternatives']) <= 2)
    for value in fact['alternatives']:
        _value(c, field, value)
    if fact['state'] == 'known':
        _value(c, field, fact['value'])
        _require(c, not fact['alternatives'])
    else:
        _require(c, fact['value'] is None)
        _require(c, fact['state'] == 'conflict' or not fact['alternatives'])


def validate(c, state):
    _require(c, type(state) is dict and set(state) == {
        'schema', 'session_id', 'revision', 'created_at', 'updated_at', 'facts',
        'invalidated', 'history', 'actions_executed', 'authorization_restored'})
    _require(c, state['schema'] == SCHEMA and state['actions_executed'] is False
             and state['authorization_restored'] is False)
    _require(c, type(state['session_id']) is str and re.fullmatch('[0-9a-f]{32}', state['session_id']))
    _require(c, type(state['revision']) is int and 0 <= state['revision'] <= 10000)
    for field in ('created_at', 'updated_at'):
        import datetime as dt
        try:
            stamp = dt.datetime.fromisoformat(state[field])
            _require(c, stamp.tzinfo is not None)
        except (ValueError, TypeError):
            raise c.SetupError('INTAKE_STATE_INVALID') from None
    _require(c, type(state['facts']) is dict and set(state['facts']) <= FIELDS)
    for field, fact in state['facts'].items():
        _fact(c, field, fact)
        _require(c, fact['revision'] <= state['revision'])
    _require(c, type(state['invalidated']) is list and len(set(state['invalidated'])) == len(state['invalidated'])
             and set(state['invalidated']) <= {'target_binding', 'dependent_plans', 'network_evidence'})
    _require(c, type(state['history']) is list and len(state['history']) <= 64)
    for record in state['history']:
        _require(c, type(record) is dict and set(record) == {'field', 'previous', 'revision'}
                 and record['field'] in FIELDS and type(record['revision']) is int
                 and 1 <= record['revision'] <= state['revision'])
        _fact(c, record['field'], record['previous'])
    return state


def start(c, task=None):
    state = {'schema': SCHEMA, 'session_id': uuid.uuid4().hex, 'revision': 0,
             'created_at': c.now(), 'updated_at': c.now(), 'facts': {}, 'invalidated': [],
             'history': [], 'actions_executed': False, 'authorization_restored': False}
    if task:
        state = answer(c, state, [{'field': 'task', 'state': 'known', 'value': task}])
    return state


def answer(c, state, answers, accept_changes=False):
    """Validate an entire batch before changing a copy; never save partial facts."""
    validate(c, state)
    _require(c, type(answers) is list and 1 <= len(answers) <= len(FIELDS), 'INTAKE_ANSWERS_INVALID')
    normalized, fields = [], set()
    for item in answers:
        _require(c, type(item) is dict and {'field', 'state'} <= set(item)
                 and set(item) <= {'field', 'state', 'value', 'source'}, 'INTAKE_ANSWERS_INVALID')
        field = item['field']
        _require(c, type(field) is str and field in FIELDS and field not in fields,
                 'INTAKE_DUPLICATE_OR_UNKNOWN_FIELD')
        fields.add(field)
        fact = {'state': item['state'], 'value': item.get('value'),
                'source': item.get('source', 'user'), 'revision': state['revision'] + 1,
                'alternatives': []}
        _fact(c, field, fact)
        _require(c, fact['state'] not in ('stale', 'conflict'), 'INTAKE_ANSWER_STATE_INVALID')
        normalized.append((field, fact))
    result = copy.deepcopy(state)
    result['revision'] += 1
    result['updated_at'] = c.now()
    changed = set()
    for field, fact in normalized:
        old = result['facts'].get(field)
        if old and old != fact:
            result['history'].append({'field': field, 'previous': old, 'revision': result['revision']})
        if old and old['state'] == 'known' and fact['state'] == 'known' and old['value'] != fact['value']:
            if not accept_changes:
                fact = dict(fact, state='conflict', value=None, alternatives=[old['value'], fact['value']])
            changed.add(field)
        elif old and old['state'] == 'known' and fact['state'] != 'known':
            changed.add(field)
        result['facts'][field] = fact
    if changed & {'route', 'target_ref', 'platform', 'configuration', 'proxy', 'namespace'}:
        result['invalidated'] = ['dependent_plans', 'network_evidence']
    if changed & {'route', 'target_ref', 'platform', 'namespace'}:
        result['invalidated'].insert(0, 'target_binding')
        dependents = {'target_ref', 'platform', 'namespace', 'configuration'}
        for field in dependents - fields:
            old = result['facts'].get(field)
            if old and old['state'] == 'known':
                result['history'].append({'field': field, 'previous': old, 'revision': result['revision']})
                result['facts'][field] = dict(old, state='stale', value=None,
                                             revision=result['revision'], alternatives=[])
    result['history'] = result['history'][-64:]
    return validate(c, result)


def assess(c, state):
    validate(c, state)
    facts = state['facts']
    def known(field):
        fact = facts.get(field, {})
        return fact.get('value') if fact.get('state') == 'known' else None
    task = known('task')
    relevant = ['task'] if task is None else list(TASK_FIELDS[task])
    if task in ('setup', 'diagnose', 'cleanup', 'maintenance', 'hardening') and known('platform') == 'windows':
        relevant.append('namespace')
    # No proxy configuration to ask about when the selected resource is absent.
    if known('proxy') == 'none' and 'configuration' in relevant:
        relevant.remove('configuration')
    missing = [field for field in relevant if known(field) is None]
    # An answered unknown, decline or deferral is not a new question next turn.
    ask = next((field for field in missing if field not in facts or facts[field]['state'] in ('conflict', 'stale')), None)
    next_question = None
    if ask:
        next_question = {'field': ask, 'prompt': QUESTIONS[ask], 'options': list(VALUES[ask])}
    blocked = [field for field in missing if field in facts and facts[field]['state'] in
               ('unknown', 'declined', 'deferred', 'conflict', 'stale')]
    references = list(REFERENCES.get(task, ()))
    if task == 'cleanup' and known('client'):
        references = ['browser-cleanup.md' if known('client') == 'browser' else 'client-cleanup.md']
    if task == 'diagnose' and known('platform'):
        name = 'mac-checks.md' if known('platform') == 'macos' else 'windows-checks.md' if known('platform') == 'windows' else 'deployment-routes.md'
        references.insert(0, name)
    route_blocked = task == 'remote' and known('route') == 'local'
    if route_blocked:
        blocked.append('remote_route_required')
    status = ('needs_input' if next_question else 'needs_review' if blocked or missing else
              'explanation_only' if task == 'compare' else 'ready_for_plan')
    if route_blocked:
        status = 'needs_review'
    return {'schema': 'claude-intake-assessment/1', 'status': status,
            'explanation_available': True,
            'session_id': state['session_id'], 'revision': state['revision'],
            'next_question': next_question, 'missing_fields': missing, 'blocked_fields': blocked,
            'references': list(dict.fromkeys(references)),
            'incident_priority': task == 'diagnose' and known('issue') in INCIDENTS,
            'scope_defaults': {'cleanup_category': 'cache'} if task == 'cleanup' else {},
            'invalidated': state['invalidated'], 'facts_count': len(facts),
            'target_binding': 'declarations_only_not_verified',
            'action_authorized': False, 'actions_executed': False,
            'authorization_restored': False, 'network_requests': 0,
            'system_changes_performed': False}


def register_commands(sub):
    p = sub.add_parser('intake-start', help='Start task-specific offline intake; no device inspection')
    p.add_argument('--task', choices=TASKS)
    p.add_argument('--answers', help='Explicit structured facts; no credentials or raw transcripts')
    p.add_argument('--output', required=True)
    p = sub.add_parser('intake-answer', help='Apply a validated answer batch to a new private state file')
    p.add_argument('--state', required=True)
    p.add_argument('--answers', required=True)
    p.add_argument('--accept-changes', action='store_true', help='Explicitly resolve current fact changes; not action approval')
    p.add_argument('--output', required=True)
    p = sub.add_parser('intake-assess', help='Select the next relevant gap without executing actions')
    p.add_argument('--state', required=True)
    p.add_argument('--output')


def run(c, args):
    if args.command == 'intake-start':
        state = start(c, args.task)
        if args.answers:
            state = answer(c, state, c.load_json(c.read_bytes(args.answers, 65536)))
        c.write_new(args.output, c.encode(state))
        return assess(c, state)
    state = validate(c, c.load_json(c.read_bytes(args.state, 131072)))
    if args.command == 'intake-answer':
        state = answer(c, state, c.load_json(c.read_bytes(args.answers, 65536)), args.accept_changes)
        c.write_new(args.output, c.encode(state))
        return assess(c, state)
    result = assess(c, state)
    if args.output:
        c.write_new(args.output, c.encode(result))
    return result
