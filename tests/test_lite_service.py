"""Local synthetic export invariants, without a real client or external requests."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c
import domestic_policy as d
from lite.service import Service, error_message

BASE = {'mode': 'rule', 'proxies': [
    {'name': 'Transit', 'type': 'http', 'server': '192.0.2.1', 'port': 8080},
    {'name': 'Exit', 'type': 'socks5', 'server': '203.0.113.1', 'port': 1080,
     'username': 'synthetic-user', 'password': 'synthetic-not-real', 'dialer-proxy': 'Transit'}],
    'rules': ['DOMAIN,customer.test,DIRECT', 'MATCH,Exit']}
SNAPSHOT = {d.VIDEO: {'type': 'inline', 'behavior': 'domain', 'payload': ['+.bilibili.com']},
            d.CN: {'type': 'inline', 'behavior': 'domain', 'payload': ['+.baidu.com']}}


class LiteService(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'original.json'; self.original = c.encode(BASE)
        self.source.write_bytes(self.original)
        self.service = Service(self.root / 'private')
        self.service.load(self.source, probe_runtime=False)
        self.snapshot = patch.object(d, 'snapshot', return_value=SNAPSHOT)
        self.snapshot.start(); self.addCleanup(self.snapshot.stop)

    def test_export_preserves_source_chain_and_manual_state_is_not_verified(self):
        self.service.prepare('Exit', True)
        dest = self.root / 'new.yaml'
        receipt = self.service.export(dest, {'DNS': '人工核对未见异常'})
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(c.parse_config(dest.read_bytes(), 'yaml')['proxies'], BASE['proxies'])
        self.assertFalse(receipt['runtime_verified'])
        self.assertFalse(receipt['manual_results_independently_verified'])
        self.assertFalse(receipt['proxy_or_system_changes'])
        self.assertEqual(receipt['manual_checks']['WebRTC'], '未记录')
        with self.assertRaises(c.SetupError):
            self.service.export(dest)

    def test_source_drift_invalidates_prepare(self):
        self.source.write_bytes(self.original + b' ')
        with self.assertRaisesRegex(c.SetupError, 'LITE_SOURCE_CHANGED'):
            self.service.prepare('Exit', True)

    def test_assistance_request_is_recorded_without_claiming_a_pass(self):
        self.service.prepare('Exit', True)
        receipt=self.service.export(self.root/'needs-help.yaml',{'DNS':'人工请求协助'})
        self.assertEqual(receipt['manual_checks']['DNS'],'人工请求协助')
        self.assertFalse(receipt['manual_results_independently_verified'])
        self.assertFalse(receipt['runtime_verified'])

    def test_candidate_drift_and_invalid_manual_result_never_export(self):
        prepared = self.service.prepare('Exit', True)
        dest = self.root / 'new.yaml'
        with self.assertRaisesRegex(c.SetupError, 'LITE_MANUAL_RESULT_INVALID'):
            self.service.export(dest, {'DNS': 'auto-verified'})
        self.assertFalse(dest.exists())
        Path(prepared['candidate_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(c.SetupError, 'LITE_CANDIDATE_CHANGED'):
            self.service.export(dest)
        self.assertFalse(dest.exists())

    def test_existing_output_and_source_are_never_overwritten(self):
        self.service.prepare('Exit', True)
        dest = self.root / 'existing.yaml'; dest.write_bytes(b'keep')
        with self.assertRaises(c.SetupError): self.service.export(dest)
        self.assertEqual(dest.read_bytes(), b'keep')
        with self.assertRaises(c.SetupError): self.service.export(self.source)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_failed_new_input_invalidates_old_candidate_and_summary_is_redacted(self):
        self.service.prepare('Exit', True)
        summary = self.service.support_summary('CHAIN_REFERENCE_MISSING')
        text = str(summary)
        for secret in ('synthetic-user', 'synthetic-not-real', str(self.source), 'Transit', '203.0.113.1'):
            self.assertNotIn(secret, text)
        self.assertFalse(summary['private_configuration_included'])
        bad = self.root / 'broken.json'; bad.write_bytes(b'invalid')
        with self.assertRaises(c.SetupError):self.service.load(bad, probe_runtime=False)
        self.assertIsNone(self.service.source)
        self.assertIsNone(self.service.prepared)
        with self.assertRaises(c.SetupError):self.service.export(self.root / 'new.yaml')

    def test_source_links_refused_and_errors_do_not_echo_private_text(self):
        link = self.root / 'link.json'
        try:link.symlink_to(self.source)
        except OSError:self.skipTest('symlink unavailable')
        with self.assertRaises(c.SetupError):self.service.load(link, probe_runtime=False)
        self.assertNotIn('secret', error_message(ValueError('secret /private/path')))

    def test_unresolved_exit_is_not_replaced_with_a_transit(self):
        obj = copy.deepcopy(BASE)
        obj['proxies'][1]['dialer-proxy'] = 'Provider Transit'
        obj['proxy-groups'] = [{'name': 'Provider Transit', 'type': 'select', 'use': ['remote']}]
        obj['proxy-providers'] = {'remote': {'type': 'http', 'url': 'https://provider.invalid/sub'}}
        self.source.write_bytes(c.encode(obj))
        info = self.service.load(self.source, probe_runtime=False)
        self.assertIsNone(info['selected_node'])
        self.assertFalse(next(n for n in info['inspection']['nodes'] if n['name'] == 'Exit')['selectable'])
        with self.assertRaises(c.SetupError):self.service.prepare('Exit', True)


if __name__ == '__main__':unittest.main()
