"""Offline intake scenarios; no local environment, network or authorization effects."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c
import intake_flow as intake


def fact(field, value=None, state='known', source='user'):
    return {'field': field, 'state': state, 'value': value, 'source': source}


class IntakeScenarios(unittest.TestCase):
    def test_cleanup_bypasses_subscription_and_route_questions(self):
        s = intake.start(c, 'cleanup')
        s = intake.answer(c, s, [fact('platform', 'macos'), fact('client', 'browser'),
                                 fact('cleanup_category', 'cache'), fact('cleanup_scope', 'profile')])
        out = intake.assess(c, s)
        self.assertEqual(out['status'], 'ready_for_plan')
        self.assertIsNone(out['next_question'])
        self.assertEqual(out['references'], ['browser-cleanup.md'])
        self.assertFalse(out['action_authorized'])
        self.assertFalse(out['actions_executed'])

    def test_compare_is_explanation_only_and_never_requires_device_or_proxy(self):
        s = intake.answer(c, intake.start(c, 'compare'),
                          [fact('platform', 'macos'), fact('priority', 'isolation')])
        out = intake.assess(c, s)
        self.assertEqual(out['status'], 'explanation_only')
        self.assertEqual(out['missing_fields'], [])
        self.assertEqual(out['network_requests'], 0)

    def test_missing_comparison_preferences_still_allow_conditional_explanation(self):
        s = intake.answer(c, intake.start(c, 'compare'),
                          [fact('platform', None, 'unknown'), fact('priority', None, 'declined')])
        out = intake.assess(c, s)
        self.assertTrue(out['explanation_available'])
        self.assertIsNone(out['next_question'])
        self.assertFalse(out['action_authorized'])
        self.assertEqual(out['references'], ['deployment-routes.md'])

    def test_known_answers_are_reused_and_unknown_is_not_asked_again(self):
        s = intake.start(c, 'diagnose')
        s = intake.answer(c, s, [fact('platform', 'windows'), fact('client', 'code'),
                                 fact('issue', None, 'unknown'), fact('namespace', 'wsl')])
        out = intake.assess(c, s)
        self.assertIsNone(out['next_question'])
        self.assertEqual(out['status'], 'needs_review')
        self.assertEqual(out['blocked_fields'], ['issue'])
        self.assertFalse(out['authorization_restored'])

    def test_declined_route_is_not_accepted_or_repeated(self):
        s = intake.answer(c, intake.start(c, 'hardening'),
                          [fact('platform', 'macos'), fact('route', None, 'declined'),
                           fact('proxy', 'available'), fact('configuration', 'effective')])
        out = intake.assess(c, s)
        self.assertIsNone(out['next_question'])
        self.assertIn('route', out['blocked_fields'])
        self.assertEqual(out['status'], 'needs_review')

    def test_bad_batch_is_atomic_and_sensitive_values_are_rejected(self):
        s = intake.start(c, 'setup'); before = copy.deepcopy(s)
        for answers in ([fact('platform', 'macos'), fact('route', 'https://private.example')],
                        [fact('platform', 'macos'), fact('platform', 'windows')],
                        [fact('target_ref', '192.0.2.1')],
                        [{'field': 'proxy', 'state': 'known', 'value': 'available', 'authorized': True}]):
            with self.assertRaises(c.SetupError):
                intake.answer(c, s, answers)
            self.assertEqual(s, before)

    def test_route_change_invalidates_dependent_facts_without_erasing_history(self):
        s = intake.answer(c, intake.start(c, 'setup'),
                          [fact('platform', 'macos'), fact('route', 'local'),
                           fact('target_ref', 'target-a'), fact('configuration', 'effective')])
        conflict = intake.answer(c, s, [fact('route', 'vm')])
        self.assertEqual(conflict['facts']['route']['state'], 'conflict')
        self.assertIn('target_binding', conflict['invalidated'])
        changed = intake.answer(c, s, [fact('route', 'vm')], accept_changes=True)
        self.assertEqual(changed['facts']['route']['value'], 'vm')
        self.assertEqual(changed['facts']['target_ref']['state'], 'stale')
        self.assertTrue(changed['history'])
        self.assertEqual(s['facts']['route']['value'], 'local')

    def test_explicit_batch_rebinds_current_facts_only(self):
        s = intake.answer(c, intake.start(c, 'setup'),
                          [fact('route', 'local'), fact('platform', 'macos'), fact('target_ref', 'target-a')])
        s = intake.answer(c, s, [fact('route', 'vps'), fact('platform', 'linux'),
                                 fact('target_ref', 'target-b')], accept_changes=True)
        self.assertEqual(s['facts']['platform']['state'], 'known')
        self.assertEqual(s['facts']['platform']['value'], 'linux')
        self.assertIn('dependent_plans', s['invalidated'])

    def test_billing_incident_does_not_turn_into_network_setup(self):
        s = intake.answer(c, intake.start(c, 'billing'),
                          [fact('payment_channel', 'apple'), fact('billing_issue', 'missing_entitlement')])
        out = intake.assess(c, s)
        self.assertEqual(out['status'], 'ready_for_plan')
        self.assertEqual(out['references'], ['billing-checks.md'])
        self.assertNotIn('route', out['missing_fields'])

    def test_remote_local_route_is_not_reported_ready(self):
        s = intake.answer(c, intake.start(c, 'remote'),
                          [fact('platform', 'linux'), fact('route', 'local'), fact('configuration', 'effective')])
        self.assertEqual(intake.assess(c, s)['status'], 'needs_review')

    def test_native_windows_and_wsl_are_not_silently_conflated(self):
        s = intake.answer(c, intake.start(c, 'diagnose'),
                          [fact('platform', 'windows'), fact('client', 'code'), fact('issue', 'connection')])
        self.assertEqual(intake.assess(c, s)['next_question']['field'], 'namespace')

    def test_cli_roundtrip_only_uses_explicit_synthetic_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            answers = root / 'answers.json'
            answers.write_text(json.dumps([fact('platform', 'macos'), fact('priority', 'cost')]))
            # Use direct module contract until central CLI integration lands.
            args = type('Args', (), {'command': 'intake-start', 'task': 'compare',
                                    'answers': str(answers), 'output': str(root / 'state.json')})()
            out = intake.run(c, args)
            self.assertEqual(out['status'], 'explanation_only')
            state = json.loads((root / 'state.json').read_text())
            self.assertFalse(state['authorization_restored'])
            with self.assertRaises(c.SetupError):
                intake.run(c, args)


if __name__ == '__main__':
    unittest.main()
