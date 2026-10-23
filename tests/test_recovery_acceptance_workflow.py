"""Customer-style CLI workflows, entirely inside private synthetic directories.

Declared observations below exercise the evidence contract only. They do not
constitute target-machine network, restart, fail-closed or Windows-native proof.
"""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'src' / 'claude_setup.py'
NATIVE = platform.system() in ('Darwin', 'Windows')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CustomerRecoveryAcceptanceWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-cli-workflow-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        if os.name != 'nt':
            self.root.chmod(0o700)
        self.counter = 0

    def out(self, label):
        self.counter += 1
        return self.root / (str(self.counter) + '-' + label)

    def run_cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, str(CLI), *map(str, args)],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                timeout=30, check=False)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stderr if expected == 1 else result.stdout)

    def fixtures(self, fmt):
        if fmt == 'conf':
            before = b'[General]\nipv6 = false\n[Rule]\nFINAL,PROXY\n'
            after = b'[General]\nipv6 = false\n[Rule]\nDOMAIN,example.com,REJECT\nFINAL,PROXY\n'
        else:
            before = b'{"mode":"rule","rules":["MATCH,DIRECT"]}\n'
            after = b'{"mode":"rule","rules":["DOMAIN,example.com,REJECT","MATCH,DIRECT"]}\n'
        folder = self.out(fmt)
        folder.mkdir(mode=0o700)
        target, candidate = folder / ('active.' + fmt), folder / ('candidate.' + fmt)
        target.write_bytes(before)
        candidate.write_bytes(after)
        return target, candidate, before, after

    def prepare_and_apply(self, fmt='json'):
        target, candidate, before, after = self.fixtures(fmt)
        plan, operation = self.out('plan'), self.out('apply')
        prepared = self.run_cli('recovery-plan', '--target', target, '--candidate', candidate, '--out', plan)
        self.assertFalse(prepared['config_file_changed'])
        self.assertEqual(target.read_bytes(), before)
        # A pinned plan still does not grant permission to write.
        refused = self.run_cli('recovery-apply', '--plan', plan, '--plan-sha256', prepared['plan_sha256'],
                               '--out', operation, expected=1)
        self.assertIn('CONFIRMATION_REQUIRED', refused['error'])
        self.assertFalse(operation.exists())
        self.assertEqual(target.read_bytes(), before)
        applied = self.run_cli('recovery-apply', '--plan', plan, '--plan-sha256', prepared['plan_sha256'],
                               '--allow-write', '--writer-stopped', '--out', operation)
        self.assertEqual(target.read_bytes(), after)
        self.assertTrue(applied['config_file_changed'])
        self.assertFalse(applied['proxy_reloaded'])
        self.assertFalse(applied['runtime_adoption_verified'])
        self.assertEqual(applied['network_requests'], 0)
        self.check_report(operation)
        return target, before, after, operation, applied

    def check_report(self, folder):
        report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
        self.assertTrue(report['rows'])
        for row in report['rows']:
            self.assertIn(row['status'], ('已完成', '未完成'))
            if row['status'] == '未完成':
                self.assertTrue(row['reason'])
                self.assertTrue(row['next_step'])
        for filename in ('report.json', 'report.md', 'report.html'):
            text = (folder / filename).read_text(encoding='utf-8')
            self.assertNotIn(str(self.root), text)
            self.assertNotIn('example.com', text)
            self.assertNotIn('MATCH,DIRECT', text)
            self.assertNotIn('synthetic-private-content', text)
        return report

    @unittest.skipUnless(NATIVE, 'file replacement is restricted to native macOS/Windows')
    def test_review_write_check_and_restore_both_config_dialects(self):
        for fmt in ('conf', 'json'):
            with self.subTest(format=fmt):
                target, before, _, operation, applied = self.prepare_and_apply(fmt)
                check = self.out('check')
                checked = self.run_cli('recovery-check', '--receipt', operation,
                                       '--receipt-sha256', applied['receipt_sha256'], '--out', check)
                self.assertTrue(checked['safe_automatic_rollback_available'])
                self.check_report(check)
                restored = self.out('rollback')
                result = self.run_cli('recovery-rollback', '--receipt', operation,
                                      '--receipt-sha256', applied['receipt_sha256'], '--allow-write',
                                      '--writer-stopped', '--out', restored)
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(result['status'], '已完成')
                self.assertFalse(result['runtime_adoption_verified'])
                self.assertFalse(result['proxy_reloaded'])
                self.check_report(restored)
                # An old apply receipt cannot repeatedly restore or overwrite.
                denied = self.run_cli('recovery-rollback', '--receipt', operation,
                                      '--receipt-sha256', applied['receipt_sha256'], '--allow-write',
                                      '--writer-stopped', '--out', self.out('repeat'), expected=1)
                self.assertIn('CONFLICT_OR_INCOMPLETE', denied['error'])
                self.assertEqual(target.read_bytes(), before)

    @unittest.skipUnless(NATIVE, 'requires native supported file replacement')
    def test_customer_followup_edit_blocks_automatic_rollback(self):
        target, _, _, operation, applied = self.prepare_and_apply()
        later = b'{"mode":"rule","rules":["DOMAIN,customer.example,DIRECT","MATCH,REJECT"]}\n'
        target.write_bytes(later)
        checked_folder = self.out('after-edit-check')
        checked = self.run_cli('recovery-check', '--receipt', operation,
                               '--receipt-sha256', applied['receipt_sha256'], '--out', checked_folder, expected=2)
        self.assertFalse(checked['safe_automatic_rollback_available'])
        self.assertEqual(checked['recovery_state'], 'subsequent_change_conflict')
        self.check_report(checked_folder)
        self.run_cli('recovery-rollback', '--receipt', operation, '--receipt-sha256',
                     applied['receipt_sha256'], '--allow-write', '--writer-stopped',
                     '--out', self.out('blocked-rollback'), expected=1)
        self.assertEqual(target.read_bytes(), later)

    @unittest.skipUnless(NATIVE, 'requires native supported file replacement')
    def test_missing_final_receipt_is_inspection_only_not_blind_undo(self):
        target, _, after, operation, applied = self.prepare_and_apply()
        # Simulate an interrupted journal finalization using synthetic material.
        (operation / 'receipt.private.json').unlink()
        (operation / 'receipt.sha256').unlink()
        checked_folder = self.out('interrupted-check')
        checked = self.run_cli('recovery-check', '--receipt', operation,
                               '--receipt-sha256', applied['intent_sha256'], '--out', checked_folder, expected=2)
        self.assertEqual(checked['recovery_state'], 'candidate_observed_receipt_incomplete')
        self.assertFalse(checked['safe_automatic_rollback_available'])
        self.check_report(checked_folder)
        self.run_cli('recovery-rollback', '--receipt', operation, '--receipt-sha256',
                     applied['intent_sha256'], '--allow-write', '--writer-stopped',
                     '--out', self.out('incomplete-rollback'), expected=1)
        self.assertEqual(target.read_bytes(), after)

    @unittest.skipUnless(NATIVE, 'requires native supported file replacement')
    def test_edit_after_preview_requires_new_plan_even_with_old_approval_flags(self):
        target, candidate, _, _ = self.fixtures('json')
        plan = self.out('preview')
        prepared = self.run_cli('recovery-plan', '--target', target, '--candidate', candidate, '--out', plan)
        later = b'{"mode":"rule","rules":["DOMAIN,customer.example,REJECT","MATCH,DIRECT"]}\n'
        target.write_bytes(later)
        operation = self.out('stale-preview-apply')
        denied = self.run_cli('recovery-apply', '--plan', plan, '--plan-sha256', prepared['plan_sha256'],
                              '--allow-write', '--writer-stopped', '--out', operation, expected=1)
        self.assertEqual(denied['error'], 'RECOVERY_TARGET_CONFLICT')
        self.assertEqual(target.read_bytes(), later)
        self.assertFalse(operation.exists())

    def source(self, directory, kind):
        self.counter += 1
        name = 'synthetic-' + str(self.counter) + '.bin'
        raw = b'SYNTHETIC CLI CONTRACT FIXTURE ONLY; synthetic-private-content'
        (directory / name).write_bytes(raw)
        return {'kind': kind, 'artifact': {'file': name, 'sha256': sha(raw)}}

    def receipt(self, directory, data):
        self.counter += 1
        name = 'receipt-' + str(self.counter) + '.json'
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
        (directory / name).write_bytes(raw)
        return {'file': name, 'sha256': sha(raw)}

    def declared_normal_use(self, record, directory):
        # These declared-observed test receipts are NOT real device observations.
        event = record['events'][0]
        event.update(state='performed', instance_id='synthetic-normal-use',
                     started_at=record['created_at'],
                     ended_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'))
        common = {'record_id': record['record_id'], 'binding': copy.deepcopy(record['binding']),
                  'event_id': 'normal_use', 'event_instance_id': event['instance_id'],
                  'evidence_mode': 'observed', 'observed_at': event['ended_at']}
        event_receipt = dict(common, schema='claude-lifecycle-event/1',
                             source=self.source(directory, 'operator_event_record'),
                             details={'actual_use_observed': True})
        event['event_receipt'] = self.receipt(directory, event_receipt)
        for item in event['observations']:
            proofs = []
            for check, outcome, kind in (
                    ('function', 'worked', 'client_observation'),
                    ('proxy_path', 'designated_proxy', 'correlated_runtime_flow'),
                    ('dns_path', 'through_proxy', 'correlated_dns_flow'),
                    ('udp_path', 'blocked', 'packet_metadata'),
                    ('ipv6_path', 'disabled_verified', 'native_interface_readback')):
                proofs.append({'check': check, 'outcome': outcome, 'source': self.source(directory, kind)})
            observation = dict(common, schema='claude-lifecycle-observation/1', client=item['client'],
                               process_identity_sha256=sha(item['client'].encode()), proofs=proofs)
            item['receipt'] = self.receipt(directory, observation)

    def test_only_normal_use_completed_does_not_complete_other_lifecycle_events(self):
        for target_platform in ('macos', 'windows'):
            with self.subTest(target_platform=target_platform):
                config, _, _, _ = self.fixtures('json')
                template = self.out('template-' + target_platform)
                self.run_cli('lifecycle-template', '--config', config, '--target-alias', 'synthetic-customer',
                             '--platform', target_platform, '--client', 'codex_gui', '--client', 'browser', '--out', template)
                record_path = template / 'lifecycle-record.private.json'
                record = json.loads(record_path.read_text(encoding='utf-8'))
                self.declared_normal_use(record, template)
                record['events'][3]['state'] = 'declined'
                record_path.write_text(json.dumps(record), encoding='utf-8')
                accepted = self.out('normal-only')
                result = self.run_cli('lifecycle-accept', '--config', config, '--input', record_path,
                                      '--target-alias', 'synthetic-customer', '--platform', target_platform,
                                      '--evidence-dir', template, '--out', accepted, expected=2)
                native_target = {'Darwin': 'macos', 'Windows': 'windows'}.get(platform.system()) == target_platform
                expected_completed = 1 if native_target else 0
                self.assertEqual(result['completed'], expected_completed)
                self.assertEqual(result['incomplete'], 8 - expected_completed)
                self.assertFalse(result['required_checks_completed'])
                report = self.check_report(accepted)
                self.assertFalse(report['continuous_protection'])
                self.assertFalse(report['runtime_adoption_verified'])
                self.assertFalse(report['evidence_authenticity_verified'])
                self.assertEqual(report['network_requests'], 0)
                self.assertEqual(report['rows'][0]['status'], '已完成' if native_target else '未完成')
                self.assertTrue(all(row['status'] == '未完成' for row in report['rows'][1:]))
                if native_target:
                    self.assertIn('未选择', report['rows'][3]['reason'])
                else:
                    self.assertIn('平台', report['rows'][0]['reason'])
                # A later configuration change invalidates even normal-use evidence.
                config.write_bytes(b'{"mode":"direct","rules":["MATCH,DIRECT"]}\n')
                invalidated = self.out('config-drift')
                result = self.run_cli('lifecycle-accept', '--config', config, '--input', record_path,
                                      '--target-alias', 'synthetic-customer', '--platform', target_platform,
                                      '--evidence-dir', template, '--out', invalidated, expected=2)
                self.assertEqual(result['completed'], 0)
                if native_target:
                    self.assertIn('配置不同', self.check_report(invalidated)['rows'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
