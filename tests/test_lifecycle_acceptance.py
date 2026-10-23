"""Contract tests using temporary synthetic fixtures, never real client evidence."""
import argparse
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import lifecycle_acceptance as lifecycle


CREATED = '2026-10-23T10:00:00+00:00'
NOW = '2026-10-23T11:00:00+00:00'


class LifecycleAcceptance(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / 'current.conf'
        self.original = b'[General]\nipv6 = false\n[Rule]\nFINAL,PROXY\n# private-secret-fixture\n'
        self.config.write_bytes(self.original)
        self.clock = patch.object(c, 'now', return_value=CREATED)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.machine = patch.object(lifecycle.life, 'machine_id', return_value='a' * 64)
        self.machine.start()
        self.addCleanup(self.machine.stop)
        self.execution_platform = patch.object(lifecycle, '_execution_platform', return_value='macos')
        self.execution_platform.start()
        self.addCleanup(self.execution_platform.stop)
        self.created = self.root / 'template'
        lifecycle.template(c, self.config, 'customer-one', 'macos', ['browser', 'codex_gui'], self.created,
                           required_events=list(lifecycle.EVENTS))
        self.input = self.created / 'lifecycle-record.private.json'
        self.record = c.load_json(self.input.read_bytes())
        self.serial = 0

    def new_scope(self, required_events=None):
        self.serial += 1
        self.created = self.root / ('scope-' + str(self.serial))
        lifecycle.template(c, self.config, 'customer-one', 'macos', ['browser', 'codex_gui'], self.created,
                           required_events=required_events)
        self.input = self.created / 'lifecycle-record.private.json'
        self.record = c.load_json(self.input.read_bytes())

    def ref(self, value, suffix='.json'):
        self.serial += 1
        name = 'fixture-' + str(self.serial) + suffix
        raw = c.encode(value) if not isinstance(value, bytes) else value
        (self.created / name).write_bytes(raw)
        return {'file': name, 'sha256': c.sha(raw)}

    def source(self, kind):
        return {'kind': kind, 'artifact': self.ref(b'SYNTHETIC UNIT TEST SOURCE ONLY; 203.0.113.7 secret-fixture', '.bin')}

    def common(self, event, schema):
        return {'schema': schema, 'record_id': self.record['record_id'], 'binding': copy.deepcopy(self.record['binding']),
                'event_id': event['id'], 'event_instance_id': event['instance_id'], 'evidence_mode': 'observed',
                'observed_at': event['ended_at']}

    def perform(self, event_id='normal_use'):
        """Construct declared-observed receipts solely to exercise validation logic."""
        event = next(x for x in self.record['events'] if x['id'] == event_id)
        event.update(state='performed', instance_id='event-' + event_id,
                     started_at='2026-10-23T10:01:00+00:00', ended_at='2026-10-23T10:10:00+00:00')
        r = self.common(event, 'claude-lifecycle-event/1')
        r['source'] = self.source('operator_event_record')
        if event_id == 'normal_use':
            details = {'actual_use_observed': True}
        elif event_id in ('client_update', 'proxy_update'):
            details = {'before_version_sha256': 'b' * 64, 'after_version_sha256': 'c' * 64}
        elif event_id == 'client_restart':
            details = {'client_instances': {client: {'before_sha256': c.sha((client + '-old').encode()), 'after_sha256': c.sha(client.encode())}
                                             for client in self.record['clients']}}
        elif event_id in ('system_restart', 'network_change'):
            details = {'before_identity_sha256': 'b' * 64, 'after_identity_sha256': 'c' * 64}
        elif event_id == 'sleep_wake':
            details = {'sleep_at': '2026-10-23T10:02:00+00:00', 'wake_at': '2026-10-23T10:03:00+00:00'}
        else:
            details = {'healthy_before_at': '2026-10-23T10:02:00+00:00', 'fault_started_at': '2026-10-23T10:03:00+00:00',
                       'fault_ended_at': '2026-10-23T10:04:00+00:00', 'recovered_at': '2026-10-23T10:05:00+00:00',
                       'healthy_before': True, 'fault_observed': True, 'recovery_observed': True,
                       'fault_attempt_observed': True, 'fault_block_outcome': 'blocked',
                       'fault_block_evidence': self.source('packet_metadata'),
                       'fault_clients': {client: {'process_identity_sha256': c.sha(client.encode()), 'healthy_before': True,
                                                  'attempt_observed': True, 'outcome': 'blocked',
                                                  'source': self.source('core_block_log')}
                                         for client in self.record['clients']}}
        r['details'] = details
        event['event_receipt'] = self.ref(r)
        for observation in event['observations']:
            client = observation['client']
            receipt = self.common(event, 'claude-lifecycle-observation/1')
            receipt.update(client=client, process_identity_sha256=c.sha(client.encode()), proofs=[])
            for check, outcome, kind in (
                ('function', 'worked', 'client_observation'),
                ('proxy_path', 'designated_proxy', 'correlated_runtime_flow'),
                ('dns_path', 'through_proxy', 'correlated_dns_flow'),
                ('udp_path', 'blocked', 'packet_metadata'),
                ('ipv6_path', 'disabled_verified', 'native_interface_readback')):
                receipt['proofs'].append({'check': check, 'outcome': outcome, 'source': self.source(kind)})
            observation['receipt'] = self.ref(receipt)
        return event

    def alter_receipt(self, event, callback, observation=0):
        key = event['observations'][observation] if observation is not None else event
        field = 'receipt' if observation is not None else 'event_receipt'
        receipt = c.load_json((self.created / key[field]['file']).read_bytes())
        callback(receipt)
        key[field] = self.ref(receipt)

    def review(self, target='customer-one', platform='macos', now=NOW):
        self.input.write_bytes(c.encode(self.record))
        self.serial += 1
        output = self.root / ('report-' + str(self.serial))
        with patch.object(c, 'now', return_value=now), patch.object(c, 'collect', side_effect=AssertionError('must not collect')), \
                patch.object(c, 'run_fixed', side_effect=AssertionError('must not run native commands')):
            result = lifecycle.accept(c, self.config, self.input, target, platform, output)
        report = c.load_json((output / 'report.json').read_bytes())
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(len(report['rows']), 8)
        self.assertTrue(all(row['status'] in ('已完成', '未完成') for row in report['rows']))
        for row in report['rows']:
            if row['status'] == '未完成':
                self.assertTrue(row['reason'])
                self.assertTrue(row['next_step'])
        for name in ('report.json', 'report.md', 'report.html'):
            public = (output / name).read_text(encoding='utf-8')
            for secret in ('private-secret-fixture', 'secret-fixture', '203.0.113.7', 'customer-one'):
                self.assertNotIn(secret, public)
        return result, report

    def test_template_pending_and_declined_are_incomplete(self):
        self.record['events'][0]['state'] = 'declined'
        result, report = self.review()
        self.assertEqual(result['completed'], 0)
        self.assertIn('未选择', report['rows'][0]['reason'])
        self.assertFalse(result['required_checks_completed'])

    def test_default_delivery_requires_only_normal_and_keeps_seven_followups_pending(self):
        self.new_scope()
        self.assertEqual(self.record['schema'], lifecycle.SCHEMA)
        self.assertEqual(self.record['required_events'], ['normal_use'])
        self.perform()
        result, report = self.review()
        self.assertEqual(result['completed'], 1)
        self.assertTrue(result['required_checks_completed'])
        required_rows = [row for row in report['rows'] if row['required']]
        followup_rows = [row for row in report['rows'] if not row['required']]
        self.assertEqual(len(required_rows), 1)
        self.assertEqual(required_rows[0]['status'], '已完成')
        self.assertEqual(len(followup_rows), 7)
        self.assertTrue(all(row['status'] == '未完成' for row in followup_rows))
        self.assertEqual(report['required_events'], ['normal_use'])
        self.assertEqual(set(report['followup_events']), set(lifecycle.EVENTS) - {'normal_use'})

    def test_explicit_required_event_blocks_until_its_evidence_is_complete(self):
        self.new_scope(['system_restart'])
        self.assertEqual(self.record['required_events'], ['normal_use', 'system_restart'])
        self.perform()
        result, report = self.review()
        self.assertFalse(result['required_checks_completed'])
        restart = next(row for row in report['rows'] if row['id'] == 'lifecycle_system_restart')
        self.assertTrue(restart['required'])
        self.assertEqual(restart['status'], '未完成')
        self.perform('system_restart')
        result, _ = self.review()
        self.assertTrue(result['required_checks_completed'])

    def test_completed_followup_stays_outside_delivery_required_count(self):
        self.new_scope()
        self.perform()
        self.perform('client_update')
        result, report = self.review()
        self.assertEqual(result['completed'], 2)
        self.assertTrue(result['required_checks_completed'])
        self.assertEqual(sum(row['required'] and row['status'] == '已完成' for row in report['rows']), 1)
        update = next(row for row in report['rows'] if row['id'] == 'lifecycle_client_update')
        self.assertFalse(update['required'])
        self.assertEqual(update['status'], '已完成')

    def test_legacy_records_remain_all_required_and_keep_original_receipt_binding(self):
        self.record['schema'] = lifecycle.LEGACY_SCHEMA
        self.record.pop('required_events')
        self.record['binding'].pop('required_events_sha256')
        self.perform()
        result, report = self.review()
        self.assertEqual(result['completed'], 1)
        self.assertFalse(result['required_checks_completed'])
        self.assertTrue(all(row['required'] for row in report['rows']))
        self.assertEqual(report['required_events'], list(lifecycle.EVENTS))
        self.assertEqual(report['followup_events'], [])
        for event in list(lifecycle.EVENTS)[1:]:
            self.perform(event)
        result, _ = self.review()
        self.assertTrue(result['required_checks_completed'])

    def test_required_scope_cannot_silently_change_existing_receipts(self):
        self.new_scope(['system_restart'])
        self.perform()
        self.record['required_events'] = ['normal_use']
        with self.assertRaisesRegex(c.SetupError, 'LIFECYCLE_REQUIRED_EVENTS_BINDING_MISMATCH'):
            self.review()
        # Updating the digest makes the record structurally valid, but previous
        # receipts remain bound to the original full required-event scope.
        self.record['binding']['required_events_sha256'] = c.sha(c.encode(self.record['required_events']))
        result, report = self.review()
        self.assertFalse(result['required_checks_completed'])
        self.assertEqual(result['completed'], 0)
        self.assertEqual(report['rows'][0]['status'], '未完成')

    def test_required_scope_rejects_missing_normal_duplicates_unknown_or_noncanonical(self):
        for value in ([], ['system_restart'], ['normal_use', 'normal_use'], ['normal_use', 'invented'],
                      ['system_restart', 'normal_use'], 'normal_use'):
            self.new_scope()
            self.record['required_events'] = value
            self.record['binding']['required_events_sha256'] = c.sha(c.encode(value))
            with self.assertRaisesRegex(c.SetupError, 'LIFECYCLE_REQUIRED_EVENTS_INVALID'):
                self.review()
        for value in (['system_restart', 'system_restart'], ['unknown']):
            with self.assertRaisesRegex(c.SetupError, 'LIFECYCLE_REQUIRED_EVENTS_INVALID'):
                self.new_scope(value)

    def test_legacy_schema_cannot_add_scope_fields_to_downgrade_old_requirements(self):
        self.record['schema'] = lifecycle.LEGACY_SCHEMA
        with self.assertRaisesRegex(c.SetupError, 'LIFECYCLE_SCHEMA_INVALID'):
            self.review()

    def test_supplied_complete_contract_is_not_automatic_authentication(self):
        for event in lifecycle.EVENTS:
            self.perform(event)
        result, report = self.review()
        self.assertEqual(result['completed'], 8)
        self.assertTrue(result['required_checks_completed'])
        self.assertFalse(report['evidence_authenticity_verified'])
        self.assertFalse(report['runtime_adoption_verified'])
        self.assertEqual(report['network_requests'], 0)

    def test_each_target_platform_keeps_execution_platform_separate(self):
        for target_platform in ('macos', 'windows'):
            with self.subTest(platform=target_platform):
                out = self.root / target_platform
                lifecycle.template(c, self.config, 'customer-one', target_platform, ['claude_cli'], out)
                record = c.load_json((out / 'lifecycle-record.private.json').read_bytes())
                self.assertEqual(record['binding']['target_platform'], target_platform)
                self.assertIn(record['binding']['execution_platform'], ('macos', 'windows', 'linux', 'other'))
                self.assertEqual(record['clients'], ['claude_cli'])
        self.perform()
        for target, target_platform in (('other-customer', 'macos'), ('customer-one', 'windows')):
            result, report = self.review(target, target_platform)
            self.assertEqual(result['completed'], 0)
            self.assertIn('其他目标', report['rows'][0]['reason'])

    def test_cross_platform_preparation_cannot_claim_target_acceptance(self):
        self.record['binding']['target_platform'] = 'windows'
        for event in lifecycle.EVENTS:
            self.perform(event)
        result, report = self.review(platform='windows')
        self.assertEqual(result['completed'], 0)
        self.assertIn('执行平台', report['rows'][0]['reason'])
        # Native-Windows behavior is modeled explicitly; no real Windows host is asserted.
        with patch.object(lifecycle, '_execution_platform', return_value='windows'):
            self.record['binding']['execution_platform'] = 'windows'
            for event in lifecycle.EVENTS:
                self.perform(event)
            result, _ = self.review(platform='windows')
        self.assertEqual(result['completed'], 8)

    def test_changed_configuration_and_execution_machine_invalidate_evidence(self):
        self.perform()
        self.record['binding']['config_sha256'] = 'b' * 64
        result, report = self.review()
        self.assertEqual(result['completed'], 0)
        self.assertIn('配置不同', report['rows'][0]['reason'])
        self.record['binding']['config_sha256'] = c.sha(self.original)
        self.record['binding']['execution_id'] = 'b' * 64
        result, report = self.review()
        self.assertEqual(result['completed'], 0)
        self.assertIn('执行机', report['rows'][0]['reason'])

    def test_expired_future_and_extended_template_invalid(self):
        self.perform()
        for now in ('2026-10-31T11:00:00+00:00', '2026-10-23T09:00:00+00:00'):
            result, _ = self.review(now=now)
            self.assertEqual(result['completed'], 0)
        self.record['expires_at'] = '2026-11-30T10:00:00+00:00'
        with self.assertRaisesRegex(c.SetupError, 'LIFECYCLE_VALIDITY_INVALID'):
            self.review()

    def test_synthetic_static_and_probe_reports_never_runtime_pass(self):
        for mode in ('synthetic', 'static', 'unknown'):
            event = self.perform()
            self.alter_receipt(event, lambda r: r.update(evidence_mode=mode))
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)
        for kind in ('network_report', 'preflight_report', 'recheck_report', 'static', 'synthetic'):
            event = self.perform()
            self.alter_receipt(event, lambda r: r['proofs'][1]['source'].update(kind=kind))
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)

    def test_timeout_no_ipv6_and_no_traffic_never_prove_blocking(self):
        for outcome in ('timeout', 'no_ipv6', 'no_traffic', 'failed', 'unknown'):
            event = self.perform()
            self.alter_receipt(event, lambda r: r['proofs'][3].update(outcome=outcome))
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)

    def test_other_client_event_record_or_future_observation_cannot_substitute(self):
        for field, value in (('client', 'claude_gui'), ('event_id', 'system_restart'), ('record_id', 'old-record'),
                             ('observed_at', '2026-10-23T12:00:00+00:00')):
            event = self.perform()
            self.alter_receipt(event, lambda r: r.update({field: value}))
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)

    def test_same_process_evidence_cannot_pass_for_two_clients(self):
        event = self.perform()
        self.alter_receipt(event, lambda r: r.update(process_identity_sha256=c.sha(b'browser')), observation=1)
        result, _ = self.review()
        self.assertEqual(result['completed'], 0)

    def test_missing_event_and_missing_artifact_stay_incomplete(self):
        event = self.perform()
        event['event_receipt'] = None
        result, _ = self.review()
        self.assertEqual(result['completed'], 0)
        event = self.perform()
        receipt = c.load_json((self.created / event['observations'][0]['receipt']['file']).read_bytes())
        (self.created / receipt['proofs'][0]['source']['artifact']['file']).unlink()
        result, _ = self.review()
        self.assertEqual(result['completed'], 0)

    def test_event_requires_actual_changed_identity(self):
        for event_id, before, after in (('system_restart', 'before_identity_sha256', 'after_identity_sha256'),
                                        ('network_change', 'before_identity_sha256', 'after_identity_sha256'),
                                        ('client_update', 'before_version_sha256', 'after_version_sha256'),
                                        ('proxy_update', 'before_version_sha256', 'after_version_sha256')):
            event = self.perform(event_id)
            self.alter_receipt(event, lambda r: r['details'].update({after: r['details'][before]}), observation=None)
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)

    def test_fault_failure_requires_healthy_baseline_actual_attempt_and_block_evidence(self):
        for field, value in (('healthy_before', False), ('fault_attempt_observed', False), ('fault_observed', False),
                             ('fault_block_outcome', 'timeout'), ('recovery_observed', False)):
            event = self.perform('proxy_fault_recovery')
            self.alter_receipt(event, lambda r: r['details'].update({field: value}), observation=None)
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)

    def test_fault_client_evidence_and_restart_process_cannot_be_inferred_from_recovery(self):
        event = self.perform('proxy_fault_recovery')
        self.alter_receipt(event, lambda r: r['details']['fault_clients']['browser'].update(attempt_observed=False), observation=None)
        result, _ = self.review()
        self.assertEqual(result['completed'], 0)
        event['state'] = 'not_performed'
        event.update(instance_id=None, started_at=None, ended_at=None, event_receipt=None)
        event['observations'] = [{'client': client, 'receipt': None} for client in self.record['clients']]
        event = self.perform('client_restart')
        self.alter_receipt(event, lambda r: r.update(process_identity_sha256='d' * 64))
        result, _ = self.review()
        self.assertEqual(result['completed'], 0)

    def test_configuration_change_during_review_invalidates_all_results(self):
        self.new_scope()
        self.perform()
        original_read = c.read_bytes
        read_count = 0
        def changing_read(path, *args):
            nonlocal read_count
            if Path(path) == self.config:
                read_count += 1
                if read_count > 1:
                    return b'changed-during-review'
            return original_read(path, *args)
        with patch.object(c, 'read_bytes', side_effect=changing_read):
            result, report = self.review()
        self.assertEqual(result['completed'], 0)
        self.assertIn('验收期间', report['rows'][0]['reason'])
        self.assertEqual([row['required'] for row in report['rows']], [True] + [False] * 7)

    def test_source_traversal_changed_bytes_and_symlink_are_not_followed(self):
        for invalid in ('../outside.json', '/tmp/outside.json', 'C:\\secret.json'):
            event = self.perform()
            event['event_receipt']['file'] = invalid
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)
        event = self.perform()
        receipt_path = self.created / event['event_receipt']['file']
        receipt_path.write_bytes(b'changed')
        result, _ = self.review()
        self.assertEqual(result['completed'], 0)
        if hasattr(Path, 'symlink_to'):
            event = self.perform()
            original = self.created / event['event_receipt']['file']
            linked = self.created / 'symlink.json'
            try:
                linked.symlink_to(original)
            except OSError:
                self.skipTest('symlink unavailable on this platform')
            event['event_receipt']['file'] = linked.name
            result, _ = self.review()
            self.assertEqual(result['completed'], 0)

    def test_invalid_event_enum_missing_scope_or_naive_time_rejected(self):
        original = copy.deepcopy(self.record)
        for mutation in (lambda r: r['events'][0].update(state='passed'), lambda r: r.update(clients=[]),
                         lambda r: r.update(created_at='2026-10-23T10:00:00'),
                         lambda r: r['events'][0]['observations'].append({'client': 'terminal', 'receipt': None})):
            self.record = copy.deepcopy(original)
            mutation(self.record)
            with self.assertRaises(c.SetupError):
                self.review()

    def test_command_parser_and_run_use_only_explicit_scope(self):
        parser = argparse.ArgumentParser()
        lifecycle.register_commands(parser.add_subparsers(dest='command', required=True))
        out = self.root / 'cli'
        args = parser.parse_args(['lifecycle-template', '--config', str(self.config), '--target-alias', 'customer-two',
                                  '--platform', 'windows', '--client', 'codex_cli', '--required-event', 'system_restart',
                                  '--required-event', 'proxy_update', '--out', str(out)])
        result = lifecycle.run(c, args)
        self.assertEqual(result['completed'], 0)
        record = c.load_json((out / 'lifecycle-record.private.json').read_bytes())
        self.assertEqual(record['clients'], ['codex_cli'])
        self.assertEqual(record['required_events'], ['normal_use', 'proxy_update', 'system_restart'])


if __name__ == '__main__':
    unittest.main()
