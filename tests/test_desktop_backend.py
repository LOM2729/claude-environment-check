"""Synthetic desktop worker tests. No real native collection or network calls."""
import copy
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop'))
sys.path.insert(0, str(ROOT / 'src'))
import backend as b
import claude_setup as c

SECRET = 'SYNTHETIC_PASSWORD_NOT_PUBLIC'
BASE = {
    'mode': 'rule',
    'proxies': [{'name': '测试节点', 'type': 'socks5', 'server': '192.0.2.10',
                 'port': 1080, 'password': SECRET, 'udp': False}],
    'proxy-groups': [{'name': 'Foreign', 'type': 'select', 'proxies': ['测试节点']}],
    'dns': {'enable': True, 'ipv6': False, 'nameserver': ['https://example.test/dns-query']},
    'rules': ['DOMAIN,blocked.test,REJECT', 'GEOIP,CN,DIRECT', 'MATCH,Foreign'],
}
SHADOW = '''[General]
ipv6 = false
udp-policy-not-supported-behaviour = DIRECT
[Proxy]
测试节点 = socks5, 192.0.2.10, 1080, password=SYNTHETIC_PASSWORD_NOT_PUBLIC
[Proxy Group]
Foreign = select, 测试节点
[Rule]
DOMAIN,blocked.invalid,REJECT
GEOIP,CN,DIRECT
FINAL,Foreign
'''


class DesktopBackend(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / 'private'
        self.source = self.root / 'source.json'
        self.source.write_bytes(c.encode(BASE))
        # Tests never invoke the real host collector, AI clients, or network workers.
        self.native = mock.patch.object(c, 'mac_native', return_value=c.project_native({}))
        self.windows = mock.patch.object(c, 'windows_native', return_value=c.project_native({}))
        self.native.start()
        self.windows.start()
        self.commands = mock.patch.object(c, 'run_fixed', side_effect=AssertionError('native command forbidden'))
        self.commands.start()

    def tearDown(self):
        self.commands.stop()
        self.native.stop()
        self.windows.stop()
        self.temp.cleanup()

    def call(self, action, payload=None, good=True):
        result = b.handle(self.workspace, action, payload or {})
        if good:
            self.assertTrue(result['ok'], result)
        text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(SECRET, text)
        self.assertNotIn('192.0.2.10', text)
        return result

    def select(self, path=None):
        return self.call('select_config', {'path': str(path or self.source)})

    def ready(self):
        self.select()
        self.call('collect')
        return self.prepare()

    def prepare(self, **updates):
        payload = {'node': '测试节点', 'clients': ['codex_gui'], 'keep': ['视频会议']}
        payload.update(updates)
        return self.call('prepare', payload)

    def plan_path(self, state):
        session = json.loads((self.workspace / 'session.private.json').read_text(encoding='utf-8'))
        return self.workspace / session['plan']['folder'] / state['plan']['candidate_name']

    @unittest.skipUnless(os.name == 'nt', 'native Windows read identity regression and safe diagnostics')
    def test_000_windows_session_and_source_read_fingerprints(self):
        # Report only fixed stage names / error codes and mismatched stat fields.
        # No path, content, SID, descriptor, or raw exception enters diagnostics.
        b.recovery._private_dir(c, self.workspace, create=True)
        self.source.write_bytes(c.encode(dict(BASE, mode='global')))
        state = b.initial()
        state.update(last_action='select_config', updated_at=c.now())
        b.atomic_session(self.workspace, state)
        results = {}
        for label, path in (('source', self.source),
                            ('session', self.workspace / 'session.private.json')):
            before = path.lstat()
            with path.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                stream.read()
                after = os.fstat(stream.fileno())
            final = path.lstat()
            fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            results[label + '_path_handle_differences'] = [key for key in fields if getattr(before, key) != getattr(opened, key)]
            results[label + '_path_stable'] = all(getattr(before, key) == getattr(final, key) for key in fields)
            results[label + '_handle_stable'] = all(getattr(opened, key) == getattr(after, key) for key in fields)
        steps = {'source_read': lambda: c.read_bytes(self.source),
                 'source_snapshot': lambda: b.recovery._snapshot(c, self.source),
                 'session_read': lambda: c.read_bytes(self.workspace / 'session.private.json'),
                 'session_load': lambda: b.load(self.workspace)}
        for label, operation in steps.items():
            try:
                operation()
                results[label] = 'ok'
            except Exception as exc:
                code = str(exc)
                results[label] = code if isinstance(exc, (c.SetupError, b.DesktopError)) and b.re.fullmatch('[A-Z0-9_]{1,96}', code) else 'unexpected_error'
        lock = b.acquire_lock(self.workspace)
        os.close(lock)
        results['lock_reusable'] = self.call('status', good=False)['ok']
        self.assertTrue(all(results[name] == 'ok' for name in steps), json.dumps(results, sort_keys=True))
        self.assertTrue(results['lock_reusable'], json.dumps(results, sort_keys=True))

    def test_status_does_not_collect_or_create_session(self):
        with mock.patch.object(c, 'collect', side_effect=AssertionError('collect forbidden')):
            result = self.call('status')
        self.assertEqual(result['state']['stage'], 'prepare')
        self.assertIsNone(result['state']['config'])
        self.assertFalse((self.workspace / 'session.private.json').exists())

    def test_full_offline_flow_never_claims_network_or_adoption(self):
        state = self.ready()['state']
        self.assertEqual(state['stage'], 'confirm')
        self.assertTrue(state['plan']['ready'])
        self.assertFalse(state['plan']['activation_ready'])
        candidate = self.plan_path(state)
        target = self.root / 'export.json'
        result = self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']})
        self.assertEqual(result['state']['stage'], 'configure')
        self.assertEqual(target.read_bytes(), candidate.read_bytes())
        result = self.call('verify_readback', {'path': str(target)})
        self.assertEqual(result['state']['stage'], 'verify')
        self.assertEqual(sum(r['status'] == '未完成' for r in result['state']['checks']), 3)
        self.assertEqual(self.call('status')['state']['stage'], 'verify')
        self.assertEqual(self.source.read_bytes(), c.encode(BASE))

    def test_collection_is_real_schema_and_never_auto_completes(self):
        self.select()
        result = self.call('collect')
        self.assertTrue(all(r['status'] == '未完成' for r in result['state']['checks']))
        report = self.call('get_report')
        self.assertTrue(report['rows'])
        self.assertTrue(all(r['status'] == '未完成' for r in report['rows']))
        self.assertTrue(Path(report['state']['report_path']).is_file())
        raw = next(self.workspace.glob('collection-*/collection.json'))
        self.assertEqual(json.loads(raw.read_text(encoding='utf-8'))['network_requests'], 0)

    def test_repeated_prepare_has_new_folder_and_id(self):
        first = self.ready()['state']
        one = self.plan_path(first)
        second = self.prepare()['state']
        self.assertNotEqual(first['plan']['id'], second['plan']['id'])
        self.assertNotEqual(one, self.plan_path(second))
        result = self.call('confirm_export', {'destination': str(self.root / 'bad.json'), 'plan_id': first['plan']['id']}, good=False)
        self.assertEqual(result['error'], 'PLAN_CHANGED')
        self.assertFalse((self.root / 'bad.json').exists())

    def test_invalid_new_node_clears_old_plan(self):
        self.ready()
        result = self.call('prepare', {'node': '不存在', 'clients': ['codex_gui'], 'keep': []}, good=False)
        self.assertFalse(result['ok'])
        self.assertIsNone(result['state']['plan'])
        self.assertIsNone(self.call('status')['state']['plan'])

    def test_source_change_invalidates_on_reopen(self):
        self.ready()
        self.source.write_bytes(c.encode(dict(BASE, mode='global')))
        result = self.call('status', good=False)
        self.assertEqual(result['error'], 'SOURCE_CHANGED')
        self.assertIsNone(result['state']['plan'])
        self.select()
        self.assertIsNone(self.call('status')['state']['plan'])

    def test_candidate_change_invalidates(self):
        state = self.ready()['state']
        self.plan_path(state).write_text('{}', encoding='utf-8')
        result = self.call('status', good=False)
        self.assertEqual(result['error'], 'PLAN_CHANGED')
        self.assertIsNone(result['state']['plan'])

    def test_export_refuses_existing_destination(self):
        state = self.ready()['state']
        target = self.root / 'exists.json'
        target.write_text('do not overwrite', encoding='utf-8')
        result = self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']}, good=False)
        self.assertEqual(result['error'], 'EXPORT_UNSAFE')
        self.assertEqual(target.read_text(encoding='utf-8'), 'do not overwrite')

    def test_mismatch_does_not_claim_readback_success(self):
        state = self.ready()['state']
        target = self.root / 'export.json'
        self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']})
        result = self.call('verify_readback', {'path': str(self.source)}, good=False)
        self.assertEqual(result['error'], 'READBACK_MISMATCH')
        self.assertEqual(result['state']['stage'], 'configure')

    def test_direct_unknown_blocks_without_modifying_customer_file(self):
        original = copy.deepcopy(BASE)
        original['rules'].insert(-1, 'DOMAIN,customer.test,DIRECT')
        self.source.write_bytes(c.encode(original))
        self.select()
        self.call('collect')
        result = self.call('prepare', {'node': '测试节点', 'clients': ['browser'], 'keep': []}, good=False)
        self.assertEqual(result['error'], 'DIRECT_REVIEW_REQUIRED')
        self.assertIsNone(result['state']['plan'])
        self.assertEqual(self.source.read_bytes(), c.encode(original))

    def test_ai_implicit_target_blocks_without_rewriting_url(self):
        original = copy.deepcopy(BASE)
        original['proxy-groups'][0].update(type='url-test', url='https://api.anthropic.com/')
        self.source.write_bytes(c.encode(original))
        self.select()
        self.call('collect')
        result = self.call('prepare', {'node': '测试节点', 'clients': ['browser'], 'keep': []}, good=False)
        self.assertEqual(result['error'], 'IMPLICIT_REVIEW_REQUIRED')
        self.assertEqual(self.source.read_bytes(), c.encode(original))

    def test_shadowrocket_offline_candidate_requires_activation_review(self):
        shadow = self.root / 'source.conf'
        shadow.write_text(SHADOW, encoding='utf-8')
        self.select(shadow)
        self.call('collect')
        state = self.prepare()['state']
        self.assertEqual(state['config']['format'], 'shadowrocket')
        self.assertTrue(state['plan']['ready'])
        self.assertFalse(state['plan']['activation_ready'])
        self.assertTrue(state['plan']['activation_blockers'])
        target = self.root / 'export.conf'
        self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']})
        self.assertTrue(target.read_text(encoding='utf-8').startswith('[General]'))

    def test_dynamic_provider_does_not_invent_nodes(self):
        self.source.write_bytes(c.encode({'proxy-providers': {'remote': {'type': 'http', 'url': 'https://example.test/config'}}}))
        result = self.select()
        self.assertEqual(result['state']['config']['node_names'], [])

    def test_source_symlink_hardlink_and_parent_symlink_rejected(self):
        linked = self.root / 'linked.json'
        linked.symlink_to(self.source)
        hard = self.root / 'hard.json'
        os.link(self.source, hard)
        for path in (linked, hard):
            result = self.call('select_config', {'path': str(path)}, good=False)
            self.assertEqual(result['error'], 'CONFIG_UNSAFE')
        hard.unlink()
        parent = self.root / 'alias'
        parent.symlink_to(self.root, target_is_directory=True)
        result = self.call('select_config', {'path': str(parent / 'source.json')}, good=False)
        self.assertEqual(result['error'], 'CONFIG_UNSAFE')

    def test_workspace_must_be_private_and_not_linked(self):
        public = self.root / 'public'
        public.mkdir(mode=0o755)
        if os.name != 'nt':
            result = b.handle(public, 'status', {})
            self.assertEqual(result['error'], 'WORKSPACE_UNSAFE')
        alias = self.root / 'alias'
        alias.symlink_to(public, target_is_directory=True)
        self.assertEqual(b.handle(alias, 'status', {})['error'], 'WORKSPACE_UNSAFE')

    def test_unknown_fields_actions_and_secret_errors_are_sanitized(self):
        self.assertEqual(self.call('status', {'command': 'echo secret'}, good=False)['error'], 'INVALID_REQUEST')
        self.assertEqual(self.call('exec', {}, good=False)['error'], 'INVALID_REQUEST')
        with mock.patch.object(b.recovery, '_snapshot', side_effect=RuntimeError(SECRET)):
            self.assertEqual(self.call('select_config', {'path': str(self.source)}, good=False)['error'], 'CONFIG_UNSAFE')

    def test_handoff_contains_scope_and_no_restored_authority(self):
        self.ready()
        result = self.call('handoff', {'kit_path': str(ROOT)})
        self.assertIn('视频会议', result['prompt'])
        self.assertIn('Codex 桌面端', result['prompt'])
        self.assertIn('不恢复授权', result['prompt'])
        self.assertIn('客户手动', result['prompt'])
        self.assertIn('dns-ready', result['prompt'])
        path = Path(result['state']['handoff_path'])
        self.assertTrue(path.is_file())
        self.assertTrue((path.parent / 'scope.md').is_file())
        self.assertNotIn('prompt', self.call('status'))

    def test_handoff_uses_current_draft_without_prior_prepare(self):
        self.select()
        result = self.call('handoff', {'kit_path': str(ROOT), 'node': '测试节点',
                                      'clients': ['browser', 'claude_gui'], 'keep': ['企业会议']})
        self.assertEqual(result['state']['requested_node'], '测试节点')
        self.assertEqual(result['state']['scope'], {'clients': ['browser', 'claude_gui'], 'keep': ['企业会议']})
        self.assertIn('Claude 桌面端', result['prompt'])
        self.assertIn('企业会议', result['prompt'])
        self.assertIn('指定节点：测试节点', result['prompt'])
        scope = (Path(result['state']['handoff_path']).parent / 'scope.md').read_text(encoding='utf-8')
        self.assertIn('指定节点：测试节点', scope)
        self.assertEqual(self.call('status')['state']['requested_node'], '测试节点')

    def test_handoff_same_draft_keeps_plan_but_changed_scope_invalidates_it(self):
        before = self.ready()['state']
        same = self.call('handoff', {'kit_path': str(ROOT), 'node': '测试节点',
                                    'clients': ['codex_gui'], 'keep': ['视频会议']})['state']
        self.assertEqual(same['plan']['id'], before['plan']['id'])
        changed = self.call('handoff', {'kit_path': str(ROOT), 'keep': ['企业 VPN']})['state']
        self.assertIsNone(changed['plan'])
        self.assertEqual(changed['stage'], 'prepare')
        self.assertEqual(changed['scope'], {'clients': ['codex_gui'], 'keep': ['企业 VPN']})
        self.assertEqual(changed['requested_node'], '测试节点')
        self.assertIsNone(self.call('status')['state']['plan'])

    def test_handoff_changed_node_invalidates_plan_and_rejects_unknown_node(self):
        source = copy.deepcopy(BASE)
        source['proxies'].append(dict(source['proxies'][0], name='另一个节点'))
        self.source.write_bytes(c.encode(source))
        self.ready()
        result = self.call('handoff', {'kit_path': str(ROOT), 'node': '另一个节点'})
        self.assertIsNone(result['state']['plan'])
        self.assertEqual(result['state']['requested_node'], '另一个节点')
        invalid = self.call('handoff', {'kit_path': str(ROOT), 'node': '未知节点'}, good=False)
        self.assertEqual(invalid['error'], 'SCOPE_REQUIRED')
        self.assertEqual(invalid['state']['requested_node'], '另一个节点')
        cleared = self.call('handoff', {'kit_path': str(ROOT), 'node': ''})
        self.assertEqual(cleared['state']['requested_node'], '')

    def test_blocked_prepare_retains_chosen_node_for_legacy_handoff(self):
        source = copy.deepcopy(BASE)
        source['rules'].insert(-1, 'DOMAIN,customer.test,DIRECT')
        self.source.write_bytes(c.encode(source))
        self.select()
        self.call('collect')
        failed = self.call('prepare', {'node': '测试节点', 'clients': ['claude_cli'], 'keep': ['视频会议']}, good=False)
        self.assertEqual(failed['error'], 'DIRECT_REVIEW_REQUIRED')
        self.assertEqual(failed['state']['requested_node'], '测试节点')
        result = self.call('handoff', {'kit_path': str(ROOT)})
        self.assertIn('指定节点：测试节点', result['prompt'])
        self.assertIn('Claude CLI', result['prompt'])
        self.assertIsNone(result['state']['plan'])

    def test_handoff_development_engine_uses_current_python_and_fixed_backend(self):
        with mock.patch.object(b.sys, 'frozen', False, create=True),\
             mock.patch.object(c, 'main', side_effect=AssertionError('handoff must not execute CLI')):
            result = self.call('handoff', {'kit_path': str(ROOT)})
        folder = Path(result['state']['handoff_path']).parent
        manifest = json.loads((folder / 'desktop-engine.private.json').read_text(encoding='utf-8'))
        command = [sys.executable, str(Path(b.__file__).resolve())]
        self.assertEqual(manifest['engine_command'], command)
        self.assertEqual(manifest['cli_prefix'], command + ['--cli'])
        self.assertEqual(manifest['kit_version'], c.VERSION)
        self.assertIn('开发模式', result['prompt'])
        self.assertIn('无需安装系统 Python', result['prompt'])
        self.assertIn('先只运行 --cli --version', result['prompt'])
        self.assertIn('不拼接 shell 命令', result['prompt'])
        self.assertIn('不授予新的修改或联网权限', result['prompt'])
        for command_text in ('pip install', 'brew install', 'winget install', '安装系统 Python 后'):
            self.assertNotIn(command_text, result['prompt'])

    def test_handoff_frozen_engine_uses_only_its_own_executable(self):
        executable = str(self.root / 'app with spaces' / 'claude-check-backend.exe')
        with mock.patch.object(b.sys, 'frozen', True, create=True),\
             mock.patch.object(b.sys, 'executable', executable),\
             mock.patch.object(c, 'main', side_effect=AssertionError('handoff must not execute CLI')):
            result = self.call('handoff', {'kit_path': str(ROOT)})
        folder = Path(result['state']['handoff_path']).parent
        manifest = json.loads((folder / 'desktop-engine.private.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['engine_command'], [executable])
        self.assertEqual(manifest['cli_prefix'], [executable, '--cli'])
        self.assertEqual(manifest['kit_version'], c.VERSION)
        self.assertIn('桌面包已内置运行时', result['prompt'])
        self.assertIn('无需安装系统 Python', result['prompt'])
        self.assertIn('替代文档中的 python <Skill>/scripts/claude_setup.py', result['prompt'])
        self.assertNotIn('开发模式', result['prompt'])

    def test_handoff_rejects_caller_supplied_engine_or_command(self):
        for field in ('engine_command', 'cli_prefix', 'engine', 'command'):
            result = self.call('handoff', {'kit_path': str(ROOT), field: ['untrusted-program']}, good=False)
            self.assertEqual(result['error'], 'INVALID_REQUEST')
        self.assertFalse(self.workspace.exists())

    def test_public_report_does_not_include_source_path_or_plan_details(self):
        self.ready()
        report = self.call('get_report')
        text = Path(report['state']['report_path']).read_text(encoding='utf-8')
        self.assertNotIn(str(self.source), text)
        self.assertNotIn('测试节点', text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn('192.0.2.10', text)

    def test_tampered_session_is_rejected_without_echo(self):
        self.ready()
        session = self.workspace / 'session.private.json'
        raw = json.loads(session.read_text(encoding='utf-8'))
        raw['config']['name'] = 'password=' + SECRET
        session.write_bytes(c.encode(raw))
        self.assertEqual(self.call('status', good=False)['error'], 'SESSION_INVALID')

    def write_public_report(self, **updates):
        report = {'schema': 'claude-readiness-run/1', 'kind': 'network-check',
                  'checked_at': '2026-10-28T12:00:00+08:00',
                  'rows': [{'id': 'synthetic', 'title': '合成检查记录', 'status': '已完成',
                            'reason': '这是客户选择的合成离线记录。', 'next_step': '仍需核对当前目标与实际状态。'}]}
        report.update(updates)
        path = self.root / 'public-report.json'
        path.write_bytes(c.encode(report))
        return path, report

    def test_import_report_projects_only_safe_rows_and_does_not_advance(self):
        path, _ = self.write_public_report(stage='deliver', allow_network=True, approved=True)
        result = self.call('import_report', {'path': str(path)})
        self.assertEqual(result['state']['stage'], 'prepare')
        self.assertIsNone(result['state']['plan'])
        self.assertEqual(result['state']['report_source'], {
            'label': '客户选择的检查报告', 'checked_at': '2026-10-28T12:00:00+08:00', 'imported': True})
        self.assertEqual(result['state']['checks'][0]['status'], '未完成')
        self.assertIn('不恢复授权', result['state']['checks'][0]['reason'])
        self.assertEqual(result['state']['checks'][1]['status'], '已完成')
        self.assertEqual(set(result['state']['checks'][1]), {'title', 'status', 'reason', 'next_step'})
        self.assertNotIn('allow_network', json.dumps(result))
        self.assertEqual(self.call('get_report')['rows'], result['state']['checks'])
        self.assertEqual(self.call('status')['state']['checks'], result['state']['checks'])

    def test_import_does_not_change_prepared_plan_scope_or_authority(self):
        before = self.ready()['state']
        path, _ = self.write_public_report(approved=True, stage='deliver', network_verified=True,
                                           plan={'ready': True, 'activation_ready': True})
        result = self.call('import_report', {'path': str(path)})['state']
        self.assertEqual(result['stage'], before['stage'])
        self.assertEqual(result['plan'], before['plan'])
        self.assertEqual(result['scope'], before['scope'])
        self.assertFalse(result['plan']['activation_ready'])
        self.assertNotIn('report_path', result)
        # Importing a completed report does not create an export authorization.
        readback = self.call('verify_readback', {'path': str(self.source)}, good=False)
        self.assertEqual(readback['error'], 'PLAN_REQUIRED')

    def test_import_rejects_unsafe_rows_without_echoing_them(self):
        for value in ('<script>alert(1)</script>', 'password=' + SECRET, '192.0.2.10',
                      '/Users/customer/private.conf', '/etc/passwd', r'C:\Users\customer\private.conf',
                      'file:///private/data', '../private.conf', '`run-something`'):
            path, report = self.write_public_report()
            report['rows'][0]['reason'] = value
            path.write_bytes(c.encode(report))
            result = self.call('import_report', {'path': str(path)}, good=False)
            self.assertEqual(result['error'], 'REPORT_INVALID', value)
            self.assertNotIn(value, json.dumps(result))

    def test_import_validates_schema_time_kind_status_and_row_limit(self):
        for updates in ({'schema': 'other'}, {'checked_at': '2026-10-28T12:00:00'},
                        {'checked_at': '2026-99-99T12:00:00Z'}, {'kind': '../command'},
                        {'rows': []}, {'rows': [{}] * 201},
                        {'rows': [{'title': '检查', 'status': 'complete', 'reason': '记录', 'next_step': '核对'}]}):
            path, _ = self.write_public_report(**updates)
            self.assertEqual(self.call('import_report', {'path': str(path)}, good=False)['error'], 'REPORT_INVALID')

    def test_import_ignores_extra_paths_commands_and_never_runs_collect_or_cli(self):
        private_path = str(self.root / 'must-not-read.txt')
        Path(private_path).write_text(SECRET, encoding='utf-8')
        path, report = self.write_public_report(path=private_path, command='launch',
                                               evidence={'file': private_path}, token=SECRET)
        report['rows'][0]['raw_evidence'] = private_path
        path.write_bytes(c.encode(report))
        with mock.patch.object(c, 'collect', side_effect=AssertionError('no collection')),             mock.patch.object(c, 'main', side_effect=AssertionError('no CLI dispatch')),             mock.patch.object(c, 'read_bytes', wraps=c.read_bytes) as reads:
            result = self.call('import_report', {'path': str(path)})
        self.assertNotIn(private_path, json.dumps(result))
        self.assertTrue(all(str(call.args[0]) != private_path for call in reads.call_args_list))
        self.assertEqual(Path(private_path).read_text(encoding='utf-8'), SECRET)

    def test_import_binds_private_copy_and_can_reimport_after_tampering(self):
        path, report = self.write_public_report()
        self.call('import_report', {'path': str(path)})
        # The selected source is only imported once; later changes do not rewrite it.
        path.write_text('{}', encoding='utf-8')
        self.assertTrue(self.call('status')['ok'])
        saved = next(self.workspace.glob('imported-report-*/original.private.json'))
        saved.write_text('{}', encoding='utf-8')
        self.assertEqual(self.call('status', good=False)['error'], 'REPORT_CHANGED')
        path.write_bytes(c.encode(report))
        self.assertTrue(self.call('import_report', {'path': str(path)})['ok'])
        self.assertTrue(self.call('status')['ok'])

    def test_new_collection_clears_imported_display_source(self):
        self.select()
        path, _ = self.write_public_report()
        self.call('import_report', {'path': str(path)})
        state = self.call('collect')['state']
        self.assertNotIn('report_source', state)
        self.assertTrue(all(item['status'] == '未完成' for item in state['checks']))
        self.assertNotIn('report_source', self.call('status')['state'])

    def inherited_windows_directory(self):
        """Only a synthetic temp subtree gets a deliberately broader inherited ACL."""
        parent = self.root / 'synthetic-downloads-parent'
        parent.mkdir()
        w, kernel, advapi = b.recovery._windows()
        sid = b.recovery._win_sid()
        text = ('O:' + sid + 'D:P(A;OICI;FA;;;' + sid +
                ')(A;OICI;FA;;;SY)(A;OICI;FR;;;WD)')
        descriptor = ctypes.c_void_p()
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.ULONG)]
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
        self.assertTrue(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            text, 1, ctypes.byref(descriptor), None))
        try:
            advapi.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p]
            advapi.SetFileSecurityW.restype = w.BOOL
            self.assertTrue(advapi.SetFileSecurityW(str(parent), 4 | 0x80000000, descriptor))
        finally:
            kernel.LocalFree(descriptor)
        directory = parent / 'ordinary-inherited-downloads'
        directory.mkdir()
        self.assertFalse(b.recovery._win_acl_summary(directory)['private'])
        self.assertFalse(b.recovery._win_acl_summary(directory)['dacl_protected'])
        return directory

    @unittest.skipUnless(os.name == 'nt', 'native Windows inherited directory and protected file ACL')
    def test_windows_exports_private_file_into_ordinary_inherited_directory(self):
        state = self.ready()['state']
        directory = self.inherited_windows_directory()
        before = b.recovery._win_security(directory)
        target = directory / 'export.json'
        self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']})
        self.assertEqual(target.read_bytes(), self.plan_path(state).read_bytes())
        acl = b.recovery._win_acl_summary(target)
        for key in ('owner_is_current', 'dacl_present', 'dacl_nonnull', 'dacl_protected',
                    'only_allowed_principals', 'current_user_full_access'):
            self.assertTrue(acl[key], key)
        self.assertEqual(acl['ace_count'], 2)
        self.assertEqual(b.recovery._win_security(directory), before)
        self.assertEqual(list(directory.glob('.claude-recovery-*.tmp')), [])

    @unittest.skipUnless(os.name == 'nt', 'native Windows no-overwrite rename race')
    def test_windows_export_race_never_overwrites_concurrent_file(self):
        state = self.ready()['state']
        directory = self.inherited_windows_directory()
        before = b.recovery._win_security(directory)
        target = directory / 'raced.json'
        rename = os.rename
        def concurrent_writer(source, destination):
            self.assertEqual(Path(destination), target)
            target.write_bytes(b'concurrent customer file')
            return rename(source, destination)
        with mock.patch.object(b.os, 'rename', side_effect=concurrent_writer):
            result = self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']}, good=False)
        self.assertEqual(result['error'], 'EXPORT_UNSAFE')
        self.assertEqual(target.read_bytes(), b'concurrent customer file')
        self.assertEqual(b.recovery._win_security(directory), before)
        self.assertEqual(list(directory.glob('.claude-recovery-*.tmp')), [])

    @unittest.skipUnless(os.name == 'nt', 'native Windows inherited-directory existing target')
    def test_windows_export_existing_file_is_never_replaced(self):
        state = self.ready()['state']
        directory = self.inherited_windows_directory()
        target = directory / 'exists.json'
        target.write_bytes(b'original customer file')
        with mock.patch.object(b.recovery, '_win_private_stage', side_effect=AssertionError('must reject before staging')):
            result = self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']}, good=False)
        self.assertEqual(result['error'], 'EXPORT_UNSAFE')
        self.assertEqual(target.read_bytes(), b'original customer file')

    def test_lock_is_exclusive_and_reusable_after_release(self):
        self.call('status')
        fd = b.acquire_lock(self.workspace)
        try:
            self.assertEqual(self.call('status', good=False)['error'], 'BUSY')
        finally:
            os.close(fd)
        self.assertTrue(self.call('status')['ok'])

    def test_successful_readback_is_invalidated_when_file_changes(self):
        state = self.ready()['state']
        target = self.root / 'export.json'
        self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']})
        self.call('verify_readback', {'path': str(target)})
        target.write_text('{}', encoding='utf-8')
        result = self.call('status', good=False)
        self.assertEqual(result['error'], 'PLAN_CHANGED')
        self.assertIsNone(result['state']['plan'])

    def test_report_tampering_never_returns_injected_rows(self):
        self.ready()
        review = next(self.workspace.glob('collection-*/review.json'))
        content = json.loads(review.read_text(encoding='utf-8'))
        content['items'][0]['reason'] = SECRET
        review.write_bytes(c.encode(content))
        self.assertEqual(self.call('get_report', good=False)['error'], 'SESSION_INVALID')

    def test_normalized_source_can_be_exported_and_read_back(self):
        normalized = b.domestic_policy.build_semantics(c, copy.deepcopy(BASE), 'json', '测试节点', 'AI-ONLY')
        self.source.write_bytes(c.encode(normalized))
        state = self.ready()['state']
        target = self.root / 'export.json'
        self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']})
        result = self.call('verify_readback', {'path': str(target)})
        self.assertEqual(result['state']['stage'], 'verify')

    def test_yaml_nodes_and_candidate_roundtrip(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML not present in this interpreter')
        self.source = self.root / 'source.yaml'
        self.source.write_text(yaml.safe_dump(BASE, allow_unicode=True), encoding='utf-8')
        state = self.ready()['state']
        self.assertEqual(state['config']['format'], 'yaml')
        target = self.root / 'export.yaml'
        self.call('confirm_export', {'destination': str(target), 'plan_id': state['plan']['id']})
        self.assertEqual(self.call('verify_readback', {'path': str(target)})['state']['stage'], 'verify')

    def test_cli_json_single_response_and_cli_forwarding(self):
        run = subprocess.run([sys.executable, str(ROOT / 'desktop/backend.py'), '--workspace', str(self.workspace)],
                             input=json.dumps({'action': 'status', 'payload': {}}), capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(len(run.stdout.splitlines()), 1)
        self.assertTrue(json.loads(run.stdout)['ok'])
        self.assertEqual(run.stderr, '')
        with mock.patch.object(c, 'main', return_value=0) as forwarded:
            self.assertEqual(b.main(['--cli', '--help']), 0)
        forwarded.assert_called_once_with(['--help'])


if __name__ == '__main__':
    unittest.main()
