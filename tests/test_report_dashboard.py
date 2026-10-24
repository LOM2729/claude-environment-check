"""Offline report behavior, using synthetic records and temporary output only."""
import contextlib
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import readiness_lifecycle as life
import report_dashboard as dashboard


OLD = '2020-01-02T03:04:05+00:00'
GENERATED = '2026-10-24T06:07:08+00:00'
SECRET = 'PRIVATE_DASHBOARD_SENTINEL'
ATTACK = '<img src="https://invalid.example/pixel" onerror="alert(1)"> [链接](javascript:alert(2)) | `code` & "quoted"'


class Element:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    @property
    def text(self):
        return ''.join(child if isinstance(child, str) else child.text for child in self.children)

    def elements(self, tag=None):
        for child in self.children:
            if isinstance(child, Element):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.elements(tag)

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.current = self.root
        self.feed(page)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)

    def cells_with(self, value):
        return [node for node in self.root.elements()
                if node.tag in ('td', 'th') and value in node.text]


def row(title='必需检查', status='未完成', required=True, **extra):
    return dict(title=title, status=status, required=required,
                reason='尚未取得本项实测证据。', next_step='取得明确批准后核验并记录。', **extra)


@contextlib.contextmanager
def forbid_side_effects():
    """Any attempted collection, networking, child process or browser fails loudly."""
    with contextlib.ExitStack() as stack:
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo',
                       'subprocess.Popen', 'subprocess.run', 'os.system', 'os.startfile',
                       'webbrowser.open', 'webbrowser.open_new', 'webbrowser.open_new_tab',
                       'urllib.request.urlopen', 'claude_setup.collect', 'claude_setup.run_fixed',
                       'network_checks.run_checks', 'network_checks.isolated_probe'):
            stack.enter_context(patch(target, create=True, side_effect=AssertionError('Unexpected side effect: ' + target)))
        yield


class DashboardBehaviorTests(unittest.TestCase):
    def test_customer_questions_keep_original_check_in_folded_details(self):
        data = row('系统与代理 DNS', id='system_dns')
        doc = Document(self.render([data]))
        self.assertTrue(doc.cells_with('DNS 是否泄露'))
        original = [node for node in doc.root.elements('dd') if node.text == '系统与代理 DNS']
        self.assertTrue(original)
        self.assertTrue(any(node.tag == 'details' and 'open' not in node.attrs for node in original[0].ancestors()))
        self.assertIn('未完成', doc.root.text)

    def test_resolver_success_and_unchanged_settings_are_not_leak_tests(self):
        import network_checks as network
        data = network.row({'id': 'system_dns', 'type': 'dns', 'required': True},
                           {'outcome': 'resolved', 'addresses': ['192.0.2.1']})
        self.assertEqual(data['probe_type'], 'dns')
        doc = Document(self.render([data]))
        headings = [node.text for node in doc.root.elements('th') if node.attrs.get('scope') == 'row']
        self.assertEqual(headings, ['DNS 能否解析网站地址'])
        self.assertIn('不能说明 DNS 没有泄露', doc.root.text)
        legacy = dict(data)
        del legacy['probe_type']
        legacy_doc = Document(self.render([legacy]))
        self.assertEqual([node.text for node in legacy_doc.root.elements('th') if node.attrs.get('scope') == 'row'],
                         ['DNS 能否解析网站地址'])
        data = row('系统 DNS 配置复查', status='已完成', id='dns_drift')
        doc = Document(self.render([data]))
        headings = [node.text for node in doc.root.elements('th') if node.attrs.get('scope') == 'row']
        self.assertEqual(headings, ['DNS 设置有没有变化'])
        self.assertIn('不等于没有泄露', doc.root.text)

    def test_egress_question_preserves_measured_scope_and_failed_comparison(self):
        import network_checks as network
        check = {'id': 'probe', 'type': 'egress', 'required': True, 'route': 'proxy', 'expected_ip': '192.0.2.1'}
        for actual, status in (('192.0.2.1', '已完成'), ('192.0.2.2', '未完成')):
            data = network.row(check, {'outcome': 'response', 'ip': actual})
            doc = Document(self.render([data]))
            self.assertTrue(doc.cells_with('出口是否一致'))
            self.assertIn(status, doc.root.text)
            self.assertNotIn(actual, doc.root.text)
            if status == '已完成':
                self.assertIn('只代表这条测试线路', doc.root.text)
            else:
                self.assertIn('还不能确认出口一致', doc.root.text)

    def render(self, rows=None, **kwargs):
        options = dict(title='合成离线检查', checked_at=OLD,
                       generated_at=GENERATED, rows=[row()] if rows is None else rows)
        options.update(kwargs)
        return dashboard.render(**options)

    def assert_passive(self, page):
        doc = Document(page)
        forbidden = {'script', 'iframe', 'frame', 'object', 'embed', 'form', 'input', 'button', 'img', 'audio', 'video', 'link', 'base'}
        for node in doc.root.elements():
            self.assertNotIn(node.tag, forbidden)
            self.assertFalse(any(name.lower().startswith('on') for name in node.attrs))
            self.assertNotIn('src', node.attrs)
            self.assertNotIn('srcdoc', node.attrs)
            self.assertNotIn('action', node.attrs)
            if node.tag == 'a':
                self.assertTrue(node.attrs.get('href', '').startswith('#'))
            if node.tag == 'meta':
                self.assertNotEqual(node.attrs.get('http-equiv', '').lower(), 'refresh')
        policies = [node.attrs.get('content', '') for node in doc.root.elements('meta')
                    if node.attrs.get('http-equiv', '').lower() == 'content-security-policy']
        self.assertTrue(any("default-src 'none'" in value for value in policies))
        styles = ''.join(node.text for node in doc.root.elements('style'))
        self.assertNotRegex(styles.lower(), r'@import|url\s*\(')
        return doc

    def test_required_reasons_and_actions_are_visible_followups_collapsed(self):
        required = row('当前必需项')
        followup = row('重启后复查', required=False)
        doc = self.assert_passive(self.render([required, followup]))
        for text in (required['title'], required['reason'], required['next_step']):
            cells = doc.cells_with(text)
            self.assertTrue(cells, text)
            self.assertTrue(any(all(n.tag != 'details' or 'open' in n.attrs for n in cell.ancestors())
                                for cell in cells), text)
        cells = doc.cells_with(followup['title'])
        self.assertTrue(cells)
        self.assertTrue(any(n.tag == 'details' and 'open' not in n.attrs for n in cells[0].ancestors()))
        self.assertIn('不计入', doc.root.text)

    def test_followup_completion_never_inflates_current_counts(self):
        rows = [row('当前已实测', status='已完成'), row('当前未实测'),
                row('更新后未实测', required=False), row('换网后已实测', '已完成', False)]
        doc = Document(self.render(rows))
        self.assertRegex(doc.root.text, r'已完成\s*1\s*项\s*[／/]\s*共\s*2\s*项[，,]\s*未完成\s*1\s*项')
        for item in rows:
            matches = [node for node in doc.root.elements('tr') if item['title'] in node.text]
            self.assertEqual(len(matches), 1)
            self.assertIn(item['status'], matches[0].text)

    def test_only_two_nonempty_complete_row_states_are_accepted(self):
        for invalid in ('通过', 'pending', '', None, True):
            with self.subTest(status=invalid), self.assertRaises(ValueError):
                self.render([row(status=invalid)])
        for key in ('title', 'reason', 'next_step'):
            for invalid in ('', '  ', None):
                data = row()
                data[key] = invalid
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError):
                    self.render([data])
        for invalid in ('false', 0, 1, None):
            with self.subTest(required=invalid), self.assertRaises(ValueError):
                self.render([row(required=invalid)])

    def test_old_missing_and_invalid_check_times_are_not_replaced_by_generation_time(self):
        for checked_at in (OLD, None, '', 'yesterday', '2026-10-24T06:07:08'):
            with self.subTest(checked_at=checked_at):
                page = self.render(checked_at=checked_at)
                doc = Document(page)
                self.assertIn('页面生成时间', doc.root.text)
                self.assertIn('2026-10-24', doc.root.text)
                if checked_at == OLD:
                    self.assertIn('2020-01-02', doc.root.text)
                else:
                    self.assertIn('未提供有效时间', doc.root.text)
                # Generation metadata must be separate from the check-time value.
                check_nodes = [node for node in doc.root.elements()
                               if '检查时间' in node.text and '页面生成时间' not in node.text]
                self.assertTrue(check_nodes)
                self.assertTrue(any('2026-10-24' not in node.text for node in check_nodes))
        page = self.render(checked_at=None, generated_at=None)
        self.assertNotIn(GENERATED, page)
        self.assertIn('未提供有效时间', Document(page).root.text)

    def test_observation_and_verification_record_are_collapsible(self):
        data = row(observation='合成观测细节', verified_at=OLD)
        doc = Document(self.render([data]))
        details = [node for node in doc.root.elements('details') if '合成观测细节' in node.text]
        self.assertTrue(any('open' not in node.attrs for node in details))
        self.assertIn('2020-01-02', doc.root.text)

    def test_public_text_is_escaped_and_unknown_private_fields_are_not_projected(self):
        data = row(ATTACK, observation=ATTACK, verified_at=OLD,
                   secret=SECRET, evidence={'password': SECRET}, private=SECRET)
        data['reason'] = data['next_step'] = ATTACK
        page = self.render([data], title=ATTACK, time_label=ATTACK,
                           current_label=ATTACK, followup_label=ATTACK,
                           metadata=(('目标别名', ATTACK), ('password', SECRET)),
                           notes=(ATTACK,), excluded=({'title': ATTACK, 'reason': ATTACK, 'secret': SECRET},))
        doc = self.assert_passive(page)
        self.assertNotIn(SECRET, page)
        self.assertIn(ATTACK, doc.root.text)
        self.assertNotIn('<img', page)
        for node in doc.root.elements():
            self.assertFalse(any('invalid.example' in str(value) or 'javascript:' in str(value)
                                 for value in node.attrs.values()))

    def test_render_is_pure_deterministic_and_does_not_mutate_rows(self):
        rows = [row('第二项', '已完成'), row('第一项', observation='合成细节')]
        before = copy.deepcopy(rows)
        with forbid_side_effects(), patch('builtins.open', side_effect=AssertionError('Renderer read a file')), \
                patch.object(dashboard, 'datetime', wraps=dashboard.datetime) as clock:
            clock.now.side_effect = AssertionError('Renderer read the clock')
            clock.utcnow.side_effect = AssertionError('Renderer read the clock')
            clock.today.side_effect = AssertionError('Renderer read the clock')
            first = self.render(rows)
            second = self.render(rows)
            self.render(rows, generated_at=None)
        self.assertEqual(first, second)
        self.assertEqual(rows, before)


class ReportEntryPointTests(unittest.TestCase):
    assert_passive = DashboardBehaviorTests.assert_passive

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    @staticmethod
    def collection():
        return {'schema': 'claude-setup-collection/1', 'tool_version': c.VERSION,
                'collected_at': OLD, 'target_alias': 'synthetic-client', 'platform': 'macos',
                'native': {}, 'environment': {}, 'claude_command_found': False,
                'config': None, 'browser': None, 'network_requests': 0,
                'evidence': 'synthetic_fixture', 'password': SECRET}

    def test_collection_entry_uses_shared_renderer_without_collection_or_launch(self):
        raw = self.collection()
        before = copy.deepcopy(raw)
        out = self.root / 'collection'
        with forbid_side_effects(), patch.object(dashboard, 'render', wraps=dashboard.render) as render:
            c.render_report(raw, out)
        render.assert_called_once()
        page = (out / 'report.html').read_text(encoding='utf-8')
        doc = self.assert_passive(page)
        self.assertIn('合成示例', doc.root.text)
        self.assertIn('2020-01-02', doc.root.text)
        self.assertIn('页面生成时间', doc.root.text)
        self.assertNotIn(SECRET, page)
        self.assertEqual(raw, before)
        self.assertEqual({p.name for p in out.iterdir()}, {'report.html', 'report.md'})

    def test_lifecycle_kinds_share_renderer_preserve_json_and_keep_private_evidence_private(self):
        rows = [row('当前功能', '已完成'), row('未实测后续', required=False)]
        private = {'credentials': SECRET, 'ip': '203.0.113.77'}
        kinds = ('preflight', 'recheck', 'workflow-save', 'workflow-resume',
                 'lifecycle-acceptance', 'recovery-verify', 'config-recovery')
        for kind in kinds:
            with self.subTest(kind=kind):
                out = self.root / kind
                with forbid_side_effects(), patch.object(c, 'now', return_value=GENERATED), \
                        patch.object(dashboard, 'render', wraps=dashboard.render) as render:
                    result = life.save_report(c, out, kind, rows, private=private)
                render.assert_called_once()
                saved = json.loads((out / 'report.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['rows'], rows)
                self.assertEqual(saved['kind'], kind)
                self.assertEqual(saved['checked_at'], GENERATED)
                self.assertEqual(saved['required_completed'], 1)
                self.assertEqual(saved['required_incomplete'], 0)
                self.assertEqual(saved['followup_incomplete'], 1)
                self.assertTrue(saved['required_checks_completed'])
                self.assertEqual(result['completed'], 1)
                self.assertEqual(result['incomplete'], 1)
                self.assertFalse(result['launch_requested'])
                self.assertFalse(result['runtime_adoption_verified'])
                self.assertFalse(result['system_settings_changed'])
                page = (out / 'report.html').read_text(encoding='utf-8')
                doc = self.assert_passive(page)
                self.assertIn('未实测后续', doc.root.text)
                for sentinel in (SECRET, '203.0.113.77'):
                    self.assertNotIn(sentinel, page)
                    self.assertNotIn(sentinel, (out / 'report.md').read_text(encoding='utf-8'))
                self.assertEqual(json.loads((out / 'evidence.private.json').read_text(encoding='utf-8')), private)

    def test_lifecycle_html_and_markdown_treat_notes_as_literal_text(self):
        data = row(ATTACK)
        data['reason'] = data['next_step'] = ATTACK
        out = self.root / 'escaped'
        with forbid_side_effects():
            life.save_report(c, out, 'preflight', [data])
        page = (out / 'report.html').read_text(encoding='utf-8')
        self.assertIn(ATTACK, self.assert_passive(page).root.text)
        markdown = (out / 'report.md').read_text(encoding='utf-8')
        self.assertNotIn('<img', markdown)
        self.assertNotIn('[链接](javascript:', markdown)
        self.assertNotRegex(markdown, r'(?<!\\)\| `code`')


if __name__ == '__main__':
    unittest.main()
