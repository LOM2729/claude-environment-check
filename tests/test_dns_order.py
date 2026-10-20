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
import network_checks as net
import readiness_lifecycle as life
import dns_readiness as ready

STATE = {'values': {'timezone': 'Asia/Singapore', 'languages': ['zh-Hans'], 'https_proxy_enabled': True}, 'dns_identity_sha256': 'a' * 64}


class DNSOrder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'active.json'; self.config.write_text('{}', encoding='utf-8')
        self.receipt = self.root / 'ready.json'
        self.native = patch.object(life, 'native_state', return_value=copy.deepcopy(STATE)); self.native.start()
        self.service = net.template('http://127.0.0.1:7890', 'service')

    def tearDown(self):
        self.native.stop(); self.temp.cleanup()

    def record(self):
        return ready.record(c, self.config, None, self.receipt, True, True, True, '已读回配置，并在本机连接记录中核对测试解析器和代理路径。', proxy='http://127.0.0.1:7890')

    def test_default_template_has_no_ai_queries(self):
        plan = net.template('http://127.0.0.1:7890')
        self.assertEqual(plan['phase'], 'bootstrap')
        net.validate_plan(c, plan)
        self.assertNotIn('claude.ai', json.dumps(plan))
        self.assertNotIn('chatgpt.com', json.dumps(plan))

    def test_bootstrap_rejects_ai_in_any_probe_before_all_requests(self):
        for kind in ('dns', 'stun', 'https', 'egress'):
            plan = net.template('http://127.0.0.1:7890')
            if kind in ('https', 'egress'):
                check = dict(self.service['checks'][0], type=kind, url='https://API.Claude.AI./')
                if kind == 'egress': check['response_format'] = 'trace'
            else:
                check = {'id': 'hidden_ai', 'type': kind, 'required': False, 'host': 'api.openai.com', 'family': 'ipv4', 'port': 3478}
            plan['checks'].append(check)
            with patch.object(net, 'isolated_probe') as probe:
                with self.assertRaises(c.SetupError): net.run_checks(c, plan, True)
                probe.assert_not_called()

    def test_old_and_service_plans_missing_record_send_nothing(self):
        for legacy in (False, True):
            plan = copy.deepcopy(self.service)
            if legacy: del plan['phase']
            with patch.object(net, 'isolated_probe') as probe:
                rows, private = net.run_checks(c, plan, True)
                probe.assert_not_called()
            self.assertEqual(private, [])
            self.assertTrue(all(r['status'] == '未完成' for r in rows))
            self.assertTrue(rows[0]['required'])

    def test_bootstrap_is_allowed_without_record_but_needs_permission(self):
        plan = net.template('http://127.0.0.1:7890')
        with patch.object(net, 'isolated_probe', return_value={'outcome': 'timeout'}) as probe:
            net.run_checks(c, plan, True)
            self.assertEqual(probe.call_count, 2)
            probe.reset_mock()
            with self.assertRaises(c.SetupError): net.run_checks(c, plan, False)
            probe.assert_not_called()

    def test_record_requires_all_real_checks_and_no_network(self):
        with patch.object(net, 'isolated_probe') as probe:
            with self.assertRaises(c.SetupError):
                ready.record(c, self.config, None, self.receipt, True, False, True, '尚未验证')
            self.assertFalse(self.receipt.exists())
            self.record(); probe.assert_not_called()
        self.assertTrue(ready.check(c, self.receipt, self.config)[0])

    def test_current_record_allows_service_but_not_network_permission(self):
        self.record()
        with patch.object(net, 'isolated_probe', return_value={'outcome': 'timeout'}) as probe:
            net.run_checks(c, self.service, True, self.receipt, self.config)
            self.assertEqual(probe.call_count, len(self.service['checks']))
            probe.reset_mock()
            with self.assertRaises(c.SetupError): net.run_checks(c, self.service, False, self.receipt, self.config)
            probe.assert_not_called()

    def test_network_change_blocks_and_timezone_language_do_not(self):
        self.record()
        state = copy.deepcopy(STATE); state['values']['timezone'] = 'Europe/London'; state['values']['languages'] = ['en']
        with patch.object(life, 'native_state', return_value=state):
            self.assertTrue(ready.check(c, self.receipt, self.config)[0])
        state['dns_identity_sha256'] = 'b' * 64
        with patch.object(life, 'native_state', return_value=state):
            self.assertFalse(ready.check(c, self.receipt, self.config)[0])
        self.config.write_text('{"dns":{}}', encoding='utf-8')
        self.assertFalse(ready.check(c, self.receipt, self.config)[0])

    def test_changed_proxy_port_or_mixed_paths_send_nothing(self):
        self.record()
        for mixed in (False, True):
            plan = copy.deepcopy(self.service)
            for item in plan['checks']:
                if item.get('proxy'):
                    item['proxy'] = 'http://127.0.0.1:7891'
                    if mixed: break
            with patch.object(net, 'isolated_probe') as worker:
                rows, _ = net.run_checks(c, plan, True, self.receipt, self.config)
                worker.assert_not_called()
                self.assertEqual(rows[0]['status'], '未完成')

    def test_stale_record_cannot_unlock(self):
        self.record()
        later = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
        with patch.object(c, 'now', return_value=later), patch.object(net, 'isolated_probe') as probe:
            rows, _ = net.run_checks(c, self.service, True, self.receipt, self.config)
            probe.assert_not_called()
            self.assertEqual(rows[0]['outcome'], 'DNS_READY_RECORD_EXPIRED')

    def test_change_between_probes_blocks_remaining_requests(self):
        self.record()
        def probe(item):
            self.config.write_text('{"changed":true}', encoding='utf-8')
            return {'outcome': 'response', 'http_status': 200}
        with patch.object(net, 'isolated_probe', side_effect=probe) as worker:
            rows, private = net.run_checks(c, self.service, True, self.receipt, self.config)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(len(private), 1)
        self.assertTrue(any(r['required'] and r['status'] == '未完成' for r in rows))

    def test_browser_network_change_blocks_but_language_change_does_not(self):
        browser = self.root / 'Preferences'
        browser.write_text(json.dumps({'intl': {'accept_languages': 'zh'}, 'dns_over_https': {'mode': 'secure'}}), encoding='utf-8')
        ready.record(c, self.config, browser, self.receipt, True, True, True, '已完成本机配置读回、解析器路径及代理路径核对。', proxy='http://127.0.0.1:7890')
        browser.write_text(json.dumps({'intl': {'accept_languages': 'en'}, 'dns_over_https': {'mode': 'secure'}}), encoding='utf-8')
        self.assertTrue(ready.check(c, self.receipt, self.config, browser)[0])
        browser.write_text(json.dumps({'dns_over_https': {'mode': 'off'}}), encoding='utf-8')
        self.assertFalse(ready.check(c, self.receipt, self.config, browser)[0])
        self.assertFalse(ready.check(c, self.receipt, self.config)[0])


if __name__ == '__main__': unittest.main()
