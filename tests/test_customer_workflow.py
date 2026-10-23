"""Customer report behavior using synthetic metadata and temporary files only."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import readiness_lifecycle as life


class CustomerWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch.object(c.platform, 'system', return_value='Linux'):
            self.raw = c.collect(target='synthetic-customer')
        self.raw['evidence'] = 'synthetic_fixture'
        self.digest = c.sha(c.encode(self.raw))

    def review(self, mode='automatic', preserved=None):
        return c.review_template(self.raw, self.digest, mode, preserved)

    def test_automatic_preservation_is_not_a_false_completion(self):
        review = self.review()
        data, rows = c.report_rows(self.raw, review, self.digest)
        language = next(r for r in rows if r['id'] == 'system_language')
        self.assertEqual(data['execution_mode'], 'automatic')
        self.assertEqual(language['status'], '未完成')
        self.assertIn('保持', language['next_step'])
        self.assertNotIn('询问', language['next_step'])
        self.assertTrue(all(r['status'] == '未完成' for r in rows))
        out = self.root / 'automatic'
        c.render_report(self.raw, out, review, self.digest)
        for name in ('report.md', 'report.html'):
            text = (out / name).read_text(encoding='utf-8')
            self.assertIn('集中确认', text)
            self.assertNotIn('逐项询问', text)
            self.assertNotIn('是否保留', text)

    def test_approved_item_continues_without_another_question(self):
        review = self.review()
        item = next(r for r in review['items'] if r['id'] == 'system_dns')
        item.update(decision='approved', change='proposed')
        _, rows = c.report_rows(self.raw, review, self.digest)
        row = next(r for r in rows if r['id'] == 'system_dns')
        self.assertIn('已批准', row['next_step'])
        self.assertNotIn('集中确认', row['next_step'])
        self.assertEqual(row['status'], '未完成')
        # A specific diagnostic next step remains useful after approval.
        item['next_step'] = '读回本轮解析器设置，确认尚未解决的响应超时。'
        _, rows = c.report_rows(self.raw, review, self.digest)
        self.assertEqual(next(r for r in rows if r['id'] == 'system_dns')['next_step'], item['next_step'])

    def test_preserved_items_reject_changes_even_when_approved_or_excluded(self):
        for mode in ('automatic', 'individual'):
            for change in ('proposed', 'applied'):
                for applicable in (True, False):
                    with self.subTest(mode=mode, change=change, applicable=applicable):
                        review = self.review(mode, ['browser'])
                        item = next(r for r in review['items'] if r['id'] == 'browser')
                        item.update(change=change, decision='approved', applicable=applicable, scope_confirmed=True)
                        with self.assertRaisesRegex(c.SetupError, 'PRESERVED_ITEM_CANNOT_CHANGE'):
                            c.report_rows(self.raw, review, self.digest)

    def test_preservation_can_complete_only_with_observation(self):
        review = self.review()
        item = next(r for r in review['items'] if r['id'] == 'system_language')
        item.update(status='completed', verified=True, verified_at=c.now(), evidence='已读回核对，本轮显示语言保持原值。')
        _, rows = c.report_rows(self.raw, review, self.digest)
        self.assertEqual(next(r for r in rows if r['id'] == 'system_language')['status'], '已完成')
        item['verified'] = False
        with self.assertRaisesRegex(c.SetupError, 'COMPLETION_EVIDENCE_REQUIRED'):
            c.report_rows(self.raw, review, self.digest)

    def test_invalid_mode_and_preservation_are_not_silently_accepted(self):
        for field, value in (('execution_mode', 'always-apply'), ('preserved_items', []),
                             ('preserved_items', ['system_language', 'system_language']),
                             ('preserved_items', ['unknown'])):
            review = self.review()
            review[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(c.SetupError):
                c.report_rows(self.raw, review, self.digest)
        with self.assertRaisesRegex(c.SetupError, 'COLLECTION_MISMATCH'):
            c.report_rows(self.raw, self.review(), 'a' * 64)

    def test_general_report_separates_followup_and_required_current_work(self):
        review = self.review()
        _, rows = c.report_rows(self.raw, review, self.digest)
        self.assertEqual({r['id'] for r in rows if not r['required']}, set(c.FOLLOWUP_TASKS))
        self.assertEqual(len([r for r in rows if r['required']]), 16)
        c.render_report(self.raw, self.root / 'scoped', review, self.digest)
        text = (self.root / 'scoped/report.md').read_text(encoding='utf-8')
        self.assertIn('本次交付：已完成 0 项／共 16 项，未完成 16 项', text)
        self.assertIn('## 后续复查', text)
        self.assertEqual(text.count('| 未完成 |'), 19)
        # Explicitly requested failure verification cannot disappear into follow-up.
        required = c.review_template(self.raw, self.digest, 'automatic', required_items=['ai_failure'])
        _, rows = c.report_rows(self.raw, required, self.digest)
        self.assertTrue(next(r for r in rows if r['id'] == 'ai_failure')['required'])
        self.assertEqual(len([r for r in rows if r['required']]), 17)
        review['followup_items'].append('system_dns')
        with self.assertRaisesRegex(c.SetupError, 'INVALID_FOLLOWUP_ITEMS'):
            c.report_rows(self.raw, review, self.digest)

    def test_legacy_review_retains_individual_mode_and_evidence_rules(self):
        review = self.review('individual')
        review['schema'] = 'claude-setup-review/1'
        del review['execution_mode'], review['preserved_items']
        data, rows = c.report_rows(self.raw, review, self.digest)
        self.assertEqual(data['execution_mode'], 'individual')
        self.assertTrue(all(row['status'] == '未完成' for row in rows))
        review['items'][0]['status'] = 'completed'
        with self.assertRaisesRegex(c.SetupError, 'COMPLETION_EVIDENCE_REQUIRED'):
            c.report_rows(self.raw, review, self.digest)

    def test_cli_automatic_mode_is_carried_into_report(self):
        source, review, output = self.root / 'collection.json', self.root / 'review.json', self.root / 'report'
        source.write_bytes(c.encode(self.raw))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(c.main(['review-template', '--input', str(source), '--output', str(review),
                                     '--mode', 'automatic', '--preserve', 'browser']), 0, stderr.getvalue())
            self.assertEqual(c.main(['report', '--input', str(source), '--review', str(review), '--out', str(output)]), 0)
        data = json.loads(review.read_text(encoding='utf-8'))
        self.assertEqual(set(data['preserved_items']), {'system_language', 'browser'})
        self.assertIn('集中确认', (output / 'report.html').read_text(encoding='utf-8'))

    def test_lifecycle_delivery_counts_do_not_claim_future_events_passed(self):
        rows = [life.item('normal', '正常使用', True, '本轮供给证据齐全。', '变化后复查。')]
        rows += [life.item('later' + str(n), '后续事件' + str(n), False, '本轮尚未发生。', '事件发生后复查。', False)
                 for n in range(7)]
        result = life.save_report(c, self.root / 'lifecycle', 'lifecycle-acceptance', rows)
        self.assertTrue(result['required_checks_completed'])
        self.assertEqual((result['required_completed'], result['required_incomplete'], result['followup_incomplete']), (1, 0, 7))
        report = json.loads((self.root / 'lifecycle/report.json').read_text(encoding='utf-8'))
        self.assertEqual([r['status'] for r in report['rows'][1:]], ['未完成'] * 7)
        for name in ('report.md', 'report.html'):
            text = (self.root / 'lifecycle' / name).read_text(encoding='utf-8')
            self.assertIn('本次交付：已完成 1 项／共 1 项，未完成 0 项', text)
            self.assertIn('后续复查', text)
        required_later = copy.deepcopy(rows)
        required_later[-1]['required'] = True
        result = life.save_report(c, self.root / 'required-later', 'lifecycle-acceptance', required_later)
        self.assertFalse(result['required_checks_completed'])
        self.assertEqual(result['required_incomplete'], 1)


if __name__ == '__main__':
    unittest.main()
