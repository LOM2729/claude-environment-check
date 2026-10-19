import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('claude_setup', ROOT / 'src/claude_setup.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

SECRET = 'PRIVATE_SENTINEL_NEVER_IN_REPORT'
BASE = {'proxies': [{'name': 'private-node', 'type': 'http', 'server': '192.0.2.42', 'port': 1234, 'password': SECRET}],
        'proxy-groups': [{'name': 'Claude', 'type': 'select', 'proxies': ['private-node']}],
        'rules': ['DOMAIN-SUFFIX,claude.ai,Claude', 'MATCH,DIRECT'],
        'dns': {'enable': True, 'ipv6': False}, 'mode': 'rule'}


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, name, data):
        p = self.root / name
        p.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return p

    def plan(self, fmt='json'):
        if fmt == 'json':
            before = tool.encode(BASE)
            changed = json.loads(json.dumps(BASE))
            changed['rules'].insert(1, 'DOMAIN-SUFFIX,anthropic.com,Claude')
            after = tool.encode(changed)
            ext = 'json'
        elif fmt == 'yaml':
            before = b'# keep me\nmode: rule\nrules:\n  - MATCH,DIRECT\n'
            after = b'# keep me\nmode: rule\nrules:\n  - DOMAIN-SUFFIX,claude.ai,DIRECT\n  - MATCH,DIRECT\n'
            ext = 'yaml'
        else:
            before = b'[General]\nipv6 = false\n[Rule]\nFINAL,DIRECT\n'
            after = b'[General]\nipv6 = false\n[Rule]\nDOMAIN-SUFFIX,claude.ai,DIRECT\nFINAL,DIRECT\n'
            ext = 'conf'
        current = self.file('active.' + ext, before)
        candidate = self.file('candidate.' + ext, after)
        out = self.root / 'plan'
        summary = tool.prepare_plan(current, candidate, fmt, out)
        return current, candidate, out, summary


class FileSafetyTests(Workspace):
    def test_no_overwrite(self):
        p = self.file('existing', 'original')
        with self.assertRaises(tool.SetupError): tool.write_new(p, b'new')
        self.assertEqual(p.read_bytes(), b'original')

    def test_symlink_read_refused(self):
        p = self.file('real', 'secret')
        link = self.root / 'link'
        try: link.symlink_to(p)
        except OSError: self.skipTest('symlink unavailable to current Windows user')
        with self.assertRaisesRegex(tool.SetupError, 'REGULAR'): tool.read_bytes(link)

    def test_directory_read_refused(self):
        with self.assertRaisesRegex(tool.SetupError, 'REGULAR'): tool.read_bytes(self.root)

    def test_size_bound(self):
        p = self.file('large', b'12345')
        with self.assertRaisesRegex(tool.SetupError, 'TOO_LARGE'): tool.read_bytes(p, 4)

    def test_invalid_encoding_and_null(self):
        for data in (b'\xff', b'{}\x00'):
            with self.subTest(data=data), self.assertRaises(tool.SetupError): tool.parse_config(data, 'json')

    def test_duplicate_json_key_and_nonfinite_rejected(self):
        for data in (b'{"rules":[],"rules":[]}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(data=data), self.assertRaises(tool.SetupError): tool.parse_config(data, 'json')


class ConfigTests(Workspace):
    def test_config_projection_is_not_private_config(self):
        result = tool.config_summary(tool.encode(BASE), 'json')
        text = json.dumps(result)
        for secret in (SECRET, '192.0.2.42', 'private-node', 'claude.ai'):
            self.assertNotIn(secret, text)
        self.assertEqual(result['rule_count'], 2)
        self.assertEqual(result['unknown_references'], 0)
        self.assertEqual(result['parse_status'], 'parsed_not_core_validated')

    def test_unresolved_references_and_shadowing(self):
        config = {'rules': ['MATCH,DIRECT', 'DOMAIN,claude.ai,missing']}
        result = tool.config_summary(tool.encode(config), 'json')
        self.assertEqual(result['unknown_references'], 1)
        self.assertEqual(result['rules_after_catchall'], 1)

    def test_cycles_and_duplicates(self):
        cfg = {'proxy-groups': [{'name':'a','proxies':['b']},{'name':'b','proxies':['a']}, {'name':'a','proxies':['b']}]}
        result = tool.config_summary(tool.encode(cfg),'json')
        self.assertEqual(result['duplicate_names'],1)
        self.assertGreater(result['cyclic_groups'],0)

    def test_provider_reference(self):
        cfg = {'proxy-groups': [{'name':'a','use':['missing']}], 'rules':['MATCH,a']}
        self.assertEqual(tool.config_summary(tool.encode(cfg),'json')['unknown_references'],1)

    def test_rule_provider_reference(self):
        cfg = {'rules': ['RULE-SET,missing,DIRECT', 'MATCH,DIRECT']}
        self.assertEqual(tool.config_summary(tool.encode(cfg),'json')['unknown_references'],1)
        cfg['rule-providers']={'missing':{'type':'file','path':'private-file'}}
        self.assertEqual(tool.config_summary(tool.encode(cfg),'json')['unknown_references'],0)

    def test_body_rewrite_and_mitm_are_projected(self):
        cfg = b'[Body Rewrite]\nhttps://example.invalid response-jq .\n[MITM]\nhostname = example.invalid\n[Rule]\nFINAL,DIRECT\n'
        result=tool.config_summary(cfg,'shadowrocket')
        self.assertTrue(result['rewrite_present']);self.assertTrue(result['mitm_present'])
        self.assertFalse(result['scripts_present'])

    def test_yaml_rejects_duplicate_alias_and_unsafe_tag(self):
        for data in (b'rules: []\nrules: []\n', b'a: &x [1]\nb: *x\n', b'!!python/object/apply:os.system ["echo secret"]'):
            with self.subTest(data=data), self.assertRaises(tool.SetupError): tool.parse_config(data, 'yaml')

    def test_yaml_missing_dependency_has_fixed_error(self):
        with patch.dict(sys.modules, {'yaml': None}):
            with self.assertRaisesRegex(tool.SetupError, 'YAML_DEPENDENCY_MISSING'): tool.parse_config(b'mode: rule', 'yaml')

    def test_shadowrocket_group_and_rules(self):
        data = b'[Proxy]\nnode = http, 192.0.2.1, 8080\n[Proxy Group]\nClaude = select, node\n[Rule]\nDOMAIN-SUFFIX,claude.ai,Claude\nFINAL,DIRECT\n'
        result = tool.config_summary(data,'shadowrocket')
        self.assertEqual(result['unknown_references'],0)
        self.assertEqual(result['group_count'],1)

    def test_extension_is_labeled(self):
        result = tool.config_summary(b'prepend: ["DOMAIN,claude.ai,DIRECT"]\nappend: []\ndelete: []\n','yaml')
        self.assertEqual(result['kind'],'rules_extension')

    def test_script_and_tls_flags(self):
        result = tool.config_summary(b'{"script":{},"proxies":[{"name":"p","skip-cert-verify":true}]}','json')
        self.assertTrue(result['scripts_present'])
        self.assertTrue(result['tls_verification_disabled'])


class PlanTests(Workspace):
    def test_plan_never_modifies_source(self):
        current, candidate, out, summary = self.plan()
        self.assertEqual(current.read_bytes(),tool.encode(BASE))
        self.assertEqual((out/'original.bin').read_bytes(), current.read_bytes())
        self.assertEqual((out/'candidate.bin').read_bytes(), candidate.read_bytes())
        self.assertNotIn(SECRET,json.dumps(summary))
        self.assertFalse(summary['apply_supported'])

    def test_no_change_does_not_create_plan(self):
        one=self.file('one.json',b'{}'); two=self.file('two.json',b'{}'); out=self.root/'out'
        with self.assertRaisesRegex(tool.SetupError,'NO_CHANGE'): tool.prepare_plan(one,two,'json',out)
        self.assertFalse(out.exists())

    def test_invalid_candidate_does_not_create_plan(self):
        one=self.file('one.json',b'{}'); two=self.file('two.json',b'{private-secret'); out=self.root/'out'
        with self.assertRaises(tool.SetupError): tool.prepare_plan(one,two,'json',out)
        self.assertFalse(out.exists())

    def test_unchanged_is_not_success(self):
        current,_,out,_=self.plan()
        self.assertEqual(tool.verify_readback(out,current)['status'],'unchanged_original')

    def test_exact_readback_does_not_claim_runtime_pass(self):
        current,candidate,out,_=self.plan()
        current.write_bytes(candidate.read_bytes())
        result=tool.verify_readback(out,current)
        self.assertEqual(result['status'],'candidate_bytes_match')
        self.assertFalse(result['network_verified'])
        self.assertEqual(result['application_loaded'],'not_verified')

    def test_wrong_target_rejected_export_explicitly_labeled(self):
        _,candidate,out,_=self.plan()
        with self.assertRaisesRegex(tool.SetupError,'TARGET_MISMATCH'): tool.verify_readback(out,candidate)
        result=tool.verify_readback(out,candidate,exported=True)
        self.assertEqual(result['evidence'],'caller_supplied_export')

    def test_config_changed_after_plan_conflict(self):
        current,_,out,_=self.plan()
        current.write_text('{"rules":["MATCH,REJECT"]}')
        self.assertEqual(tool.verify_readback(out,current)['status'],'unexpected_content_conflict')

    def test_comment_loss_not_silently_accepted(self):
        current,candidate,out,_=self.plan('yaml')
        current.write_bytes(candidate.read_bytes().replace(b'# keep me\n', b''))
        self.assertEqual(tool.verify_readback(out,current)['status'],'formatting_or_comments_changed_review_required')

    def test_formatting_changes_require_review(self):
        current,candidate,out,_=self.plan()
        current.write_text(json.dumps(json.loads(candidate.read_text())))
        self.assertEqual(tool.verify_readback(out,current)['status'],'formatting_or_comments_changed_review_required')

    def test_shadowrocket_readback(self):
        current,candidate,out,_=self.plan('shadowrocket')
        current.write_bytes(candidate.read_bytes())
        self.assertEqual(tool.verify_readback(out,current)['status'],'candidate_bytes_match')

    def test_tampered_plan_and_snapshot(self):
        current,_,out,_=self.plan()
        p=out/'plan.json'; original=p.read_bytes(); p.write_bytes(original+b' ')
        with self.assertRaisesRegex(tool.SetupError,'PLAN_INTEGRITY'):tool.verify_readback(out,current)
        p.write_bytes(original); (out/'candidate.bin').write_bytes(b'{}')
        with self.assertRaisesRegex(tool.SetupError,'SNAPSHOT_INTEGRITY'):tool.verify_readback(out,current)


class CollectionTests(Workspace):
    def fake_native(self):
        return {'timezone':'Asia/Singapore','system_version':'15.0','languages':['zh-CN','en-US'],
                'http_proxy_enabled':True,'dns_v4_count':2,'dns_v6_count':1,'ipv6_interface_count':3,
                'password':SECRET,'hostname':SECRET,'dns_addresses':['192.0.2.42']}

    def test_projection_drops_unexpected_fields(self):
        result=tool.project_native(self.fake_native())
        self.assertNotIn(SECRET,json.dumps(result));self.assertNotIn('192.0.2.42',json.dumps(result))
        self.assertEqual(result['dns_v4_count'],2)

    def test_bad_native_types_unknown(self):
        result=tool.project_native({'dns_v4_count':True,'http_proxy_enabled':'true','languages':['<script>','en-US'],'timezone':'<script>'})
        self.assertIsNone(result['dns_v4_count']);self.assertIsNone(result['http_proxy_enabled'])
        self.assertEqual(result['languages'],['en-US']);self.assertIsNone(result['timezone'])

    def test_collect_env_values_not_saved_no_network(self):
        with patch.object(tool.platform,'system',return_value='Darwin'),patch.object(tool,'mac_native',return_value=tool.project_native(self.fake_native())),patch.dict(os.environ,{'ANTHROPIC_API_KEY':SECRET,'HTTPS_PROXY':''}):
            data=tool.collect()
        self.assertNotIn(SECRET,json.dumps(data))
        self.assertEqual(data['environment']['ANTHROPIC_API_KEY'],'present')
        self.assertEqual(data['environment']['HTTPS_PROXY'],'empty')
        self.assertEqual(data['network_requests'],0)

    def test_wsl_not_misreported_as_windows(self):
        with patch.object(tool.platform,'system',return_value='Linux'),patch.object(tool.platform,'release',return_value='microsoft-standard-WSL2'):
            data=tool.collect()
        self.assertEqual(data['platform'],'wsl');self.assertIsNone(data['native']['dns_v4_count'])

    def test_mac_parse_native_output_without_addresses(self):
        samples={'sw_vers':'15.0','AppleLocale':'zh_CN','AppleLanguages':'(\n    "zh-Hans-CN",\n    en\n)',
                 '--proxy':'HTTPEnable : 1\nHTTPProxy : 192.0.2.42\nHTTPSEnable : 0',
                 '--dns':'nameserver[0] : 192.0.2.42\nnameserver[1] : 2001:db8::1',
                 'ifconfig':'utun4: flags=1\n inet6 fe80::1\n inet 127.0.0.1',
                 '-getusingnetworktime':'You need administrator access to run this tool.', 'Active':'1'}
        def execute(argv,timeout=6):
            return next((v for k,v in samples.items() if any(k in x for x in argv)),None)
        with patch.object(tool,'run_fixed',side_effect=execute): result=tool.mac_native()
        self.assertEqual(result['dns_v4_count'],1); self.assertEqual(result['dns_v6_count'],1)
        self.assertEqual(result['http_proxy_enabled'],True)
        self.assertIsNone(result['auto_time_enabled'])
        self.assertNotIn('192.0.2.42',json.dumps(result))

    def test_browser_file_projects_only_selected_preferences(self):
        p=self.file('Preferences',json.dumps({'intl':{'accept_languages':'zh-CN,en-US'},'dns_over_https':{'mode':'secure','templates':SECRET},'webrtc':{'ip_handling_policy':'disable_non_proxied_udp'},'account_info':[SECRET]}))
        result=tool.browser_preferences(p)
        self.assertNotIn(SECRET,json.dumps(result));self.assertEqual(result['doh_mode'],'secure')

    def test_bad_config_keeps_collection_and_fixed_error(self):
        p=self.file('private.json','{'+SECRET)
        with patch.object(tool.platform,'system',return_value='Linux'):data=tool.collect(config=p)
        self.assertEqual(data['config_error'],'INVALID_JSON');self.assertNotIn(SECRET,json.dumps(data))

    def test_bad_config_field_keeps_other_collection(self):
        for value in (None,1,'wrong'):
            p=self.file('private.json',json.dumps({'proxies':value}))
            with patch.object(tool.platform,'system',return_value='Linux'):data=tool.collect(config=p)
            self.assertEqual(data['config_error'],'INVALID_PROXY_DECLARATION')
            self.assertEqual(data['network_requests'],0)

    def test_report_is_offline_and_no_false_pass(self):
        with patch.object(tool.platform,'system',return_value='Windows'),patch.object(tool,'windows_native',return_value=tool.project_native(self.fake_native())):data=tool.collect()
        data['password']=SECRET;data['native']['extra']=SECRET
        out=self.root/'reports';tool.render_report(data,out)
        page=(out/'report.html').read_text();md=(out/'report.md').read_text()
        self.assertNotIn(SECRET,page+md);self.assertNotIn('<script',page)
        self.assertNotIn('src="http',page);self.assertIn('未执行',page)
        self.assertIn('default-src',page);self.assertIn('不代表',md)

    def test_unknown_report_schema_and_target_rejected(self):
        for raw in ({'schema':'other'}, {'schema':'claude-setup-collection/1','platform':'windows','collected_at':'2026-10-20T00:00:00+00:00','target_alias':'<script>'}):
            with self.subTest(raw=raw),self.assertRaises(tool.SetupError):tool.validate_collection(raw)

    def test_synthetic_reports_are_labeled(self):
        with patch.object(tool.platform,'system',return_value='Linux'): data=tool.collect()
        data['evidence']='synthetic_fixture'
        out=self.root/'example';tool.render_report(data,out)
        self.assertIn('合成示例（非设备实测）',(out/'report.md').read_text())

    def test_cli_errors_do_not_echo_private_input(self):
        p=self.file('private.json','{'+SECRET)
        stdout,stderr=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            code=tool.main(['report','--input',str(p),'--out',str(self.root/'report')])
        self.assertEqual(code,1);self.assertNotIn(SECRET,stderr.getvalue());self.assertNotIn(str(p),stderr.getvalue())

    @unittest.skipUnless(sys.platform=='win32','Windows native collector runs in Windows CI / target device')
    def test_windows_native_real(self):
        result=tool.windows_native()
        self.assertIsNotNone(result['timezone'])
        self.assertIsNotNone(result['system_version'])
        self.assertEqual(set(result),set(tool.project_native({})))


if __name__=='__main__':unittest.main()
