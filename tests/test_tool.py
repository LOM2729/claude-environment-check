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

    def test_shadowrocket_external_rule_is_not_clash_provider(self):
        data = b'[Rule]\nRULE-SET,https://example.test/rules.list,DIRECT\nFINAL,DIRECT\n'
        result = tool.config_summary(data,'shadowrocket')
        self.assertEqual(result['unknown_references'],0)
        self.assertEqual(result['external_rule_source_count'],1)

    def test_unicode_names_in_configuration(self):
        obj = {'proxies':[{'name':'客户节点','type':'http'}],'proxy-groups':[{'name':'Claude专用','proxies':['客户节点']}],'rules':['MATCH,Claude专用']}
        data = json.dumps(obj,ensure_ascii=False).encode('utf-8')
        result=tool.config_summary(data,'json')
        self.assertEqual(result['unknown_references'],0)
        self.assertNotIn('客户节点',json.dumps(result,ensure_ascii=False))

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
        current.write_text(json.dumps(json.loads(candidate.read_text(encoding='utf-8'))))
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
        page=(out/'report.html').read_text(encoding='utf-8');md=(out/'report.md').read_text(encoding='utf-8')
        self.assertNotIn(SECRET,page+md);self.assertNotIn('<script',page)
        self.assertNotIn('src="http',page);self.assertIn('未完成',page)
        self.assertIn('default-src',page);self.assertIn('不代表',md)

    def test_unknown_report_schema_and_target_rejected(self):
        for raw in ({'schema':'other'}, {'schema':'claude-setup-collection/1','platform':'windows','collected_at':'2026-10-20T00:00:00+00:00','target_alias':'<script>'}):
            with self.subTest(raw=raw),self.assertRaises(tool.SetupError):tool.validate_collection(raw)

    def test_synthetic_reports_are_labeled(self):
        with patch.object(tool.platform,'system',return_value='Linux'): data=tool.collect()
        data['evidence']='synthetic_fixture'
        out=self.root/'example';tool.render_report(data,out)
        self.assertIn('合成示例（非设备实测）',(out/'report.md').read_text(encoding='utf-8'))

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


class CompletionReportTests(Workspace):
    def sample(self):
        with patch.object(tool.platform,'system',return_value='Linux'):
            raw=tool.collect(target='sample-client')
        raw['evidence']='synthetic_fixture'
        raw['collected_at']=(tool.dt.datetime.now(tool.dt.timezone.utc)-tool.dt.timedelta(minutes=1)).isoformat()
        digest=tool.sha(tool.encode(raw))
        return raw,digest,tool.review_template(raw,digest)

    def finish(self,item,change='none',decision='not_required'):
        item.update(status='completed',change=change,decision=decision,verified=True,
                    verified_at=tool.now(),evidence='已与客户确认目标并完成本项检查和复测。')

    def test_collection_does_not_automatically_complete_tasks(self):
        raw,digest,review=self.sample()
        raw['native']=tool.project_native(CollectionTests.fake_native(self))
        _,rows=tool.report_rows(raw)
        self.assertEqual(len(rows),len(tool.REPORT_TASKS))
        self.assertEqual({x['status'] for x in rows},{'未完成'})
        self.assertTrue(all(x['reason'] and x['next_step'] for x in rows))

    def test_completed_count_and_unfinished_first(self):
        raw,digest,review=self.sample();self.finish(review['items'][0])
        _,rows=tool.report_rows(raw,review,digest)
        self.assertEqual(rows[-1]['id'],'system_time')
        self.assertEqual(sum(r['status']=='已完成' for r in rows),1)
        self.assertEqual({r['status'] for r in rows},{'已完成','未完成'})
        out=self.root/'report';tool.render_report(raw,out,review,digest)
        md=(out/'report.md').read_text(encoding='utf-8')
        self.assertIn('已完成 1 项／共 14 项，未完成 13 项',md)
        self.assertIn('| 检查项 | 状态 | 结果／未完成原因 | 下一步 |',md)

    def test_unverified_completed_is_rejected(self):
        raw,digest,review=self.sample();self.finish(review['items'][0]);review['items'][0]['verified']=False
        with self.assertRaisesRegex(tool.SetupError,'COMPLETION_EVIDENCE_REQUIRED'):tool.report_rows(raw,review,digest)

    def test_pending_or_declined_cannot_complete(self):
        for decision in ['pending','declined']:
            raw,digest,review=self.sample();self.finish(review['items'][0],decision=decision)
            with self.subTest(decision=decision),self.assertRaisesRegex(tool.SetupError,'CUSTOMER_DECISION_UNRESOLVED'):tool.report_rows(raw,review,digest)

    def test_applied_change_needs_recorded_approval(self):
        raw,digest,review=self.sample();self.finish(review['items'][0],change='applied')
        with self.assertRaisesRegex(tool.SetupError,'APPROVAL_REQUIRED'):tool.report_rows(raw,review,digest)
        review['items'][0]['decision']='approved'
        _,rows=tool.report_rows(raw,review,digest)
        self.assertEqual(rows[-1]['status'],'已完成')

    def test_incomplete_applied_change_also_needs_approval(self):
        for decision in ['declined','pending','not_required']:
            raw,digest,review=self.sample();review['items'][0].update(change='applied',decision=decision)
            with self.subTest(decision=decision),self.assertRaisesRegex(tool.SetupError,'APPROVAL_REQUIRED'):tool.report_rows(raw,review,digest)

    def test_declined_decision_is_visible_even_when_template_reason_retained(self):
        raw,digest,review=self.sample();review['items'][0]['decision']='declined'
        _,rows=tool.report_rows(raw,review,digest)
        self.assertIn('客户选择暂不修改',rows[0]['reason'])

    def test_applied_change_cannot_be_hidden_as_out_of_scope(self):
        raw,digest,review=self.sample();review['items'][0].update(applicable=False,scope_confirmed=True,change='applied',decision='approved')
        with self.assertRaisesRegex(tool.SetupError,'CHANGED_TASK_CANNOT_BE_EXCLUDED'):tool.report_rows(raw,review,digest)

    def test_proposed_change_cannot_complete(self):
        raw,digest,review=self.sample();self.finish(review['items'][0],change='proposed',decision='approved')
        with self.assertRaisesRegex(tool.SetupError,'COMPLETION_EVIDENCE_REQUIRED'):tool.report_rows(raw,review,digest)

    def test_not_applicable_requires_confirmed_scope_and_is_not_a_third_status(self):
        raw,digest,review=self.sample();item=review['items'][-1]
        item.update(applicable=False,reason='客户确认本次不包含故障演练。')
        with self.assertRaisesRegex(tool.SetupError,'SCOPE_CONFIRMATION_REQUIRED'):tool.report_rows(raw,review,digest)
        item['scope_confirmed']=True
        data,rows=tool.report_rows(raw,review,digest)
        self.assertEqual(len(rows),13);self.assertEqual(len(data['excluded']),1)
        self.assertEqual({x['status'] for x in rows},{'未完成'})

    def test_all_excluded_does_not_invent_success_rate(self):
        raw,digest,review=self.sample()
        for item in review['items']:item.update(applicable=False,scope_confirmed=True,reason='客户确认本次仅阅读说明，不执行检查。')
        out=self.root/'empty';tool.render_report(raw,out,review,digest)
        md=(out/'report.md').read_text(encoding='utf-8')
        self.assertIn('已完成 0 项／共 0 项，未完成 0 项',md);self.assertNotIn('100%',md)

    def test_missing_review_items_stay_incomplete(self):
        raw,digest,review=self.sample();review['items']=[]
        _,rows=tool.report_rows(raw,review,digest)
        self.assertEqual(len(rows),14);self.assertTrue(all(x['status']=='未完成' for x in rows))

    def test_stale_collection_or_wrong_target_rejected(self):
        raw,digest,review=self.sample()
        with self.assertRaisesRegex(tool.SetupError,'COLLECTION_MISMATCH'):tool.report_rows(raw,review,'0'*64)
        review['target_alias']='different'
        with self.assertRaisesRegex(tool.SetupError,'TARGET_MISMATCH'):tool.report_rows(raw,review,digest)

    def test_duplicate_ids_and_third_status_rejected(self):
        raw,digest,review=self.sample();review['items'][1]=review['items'][0].copy()
        with self.assertRaisesRegex(tool.SetupError,'DUPLICATE_TASK'):tool.report_rows(raw,review,digest)
        raw,digest,review=self.sample();review['items'][0]['status']='skipped'
        with self.assertRaisesRegex(tool.SetupError,'BINARY_STATUS_REQUIRED'):tool.report_rows(raw,review,digest)

    def test_reason_and_next_step_are_mandatory(self):
        for field in ['reason','next_step']:
            raw,digest,review=self.sample();review['items'][0][field]=''
            with self.subTest(field=field),self.assertRaisesRegex(tool.SetupError,'NOTE_REQUIRED'):tool.report_rows(raw,review,digest)

    def test_completion_requires_evidence_and_current_time(self):
        raw,digest,review=self.sample();self.finish(review['items'][0]);review['items'][0]['evidence']=''
        with self.assertRaisesRegex(tool.SetupError,'NOTE_REQUIRED'):tool.report_rows(raw,review,digest)
        self.finish(review['items'][0]);review['items'][0]['verified_at']='2020-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(tool.SetupError,'VERIFICATION_TIME'):tool.report_rows(raw,review,digest)

    def test_private_notes_rejected_and_html_escaped(self):
        raw,digest,review=self.sample();review['items'][0]['reason']='password=do-not-include'
        with self.assertRaisesRegex(tool.SetupError,'NEEDS_REDACTION'):tool.report_rows(raw,review,digest)
        review['items'][0]['reason']='出口为 2001:db8::1'
        with self.assertRaisesRegex(tool.SetupError,'NEEDS_REDACTION'):tool.report_rows(raw,review,digest)
        review['items'][0]['reason']='<script>alert(1)</script> 尚未修改'
        out=self.root/'escaped';tool.render_report(raw,out,review,digest)
        page=(out/'report.html').read_text(encoding='utf-8')
        self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)

    def test_cli_template_and_review_report(self):
        raw,_,_=self.sample();source=self.file('collection.json',tool.encode(raw));reviewfile=self.root/'review.json'
        with contextlib.redirect_stdout(io.StringIO()):
            code=tool.main(['review-template','--input',str(source),'--output',str(reviewfile)])
        self.assertEqual(code,0)
        review=json.loads(reviewfile.read_text(encoding='utf-8'));self.finish(review['items'][1])
        reviewfile.write_bytes(tool.encode(review))
        with contextlib.redirect_stdout(io.StringIO()):
            code=tool.main(['report','--input',str(source),'--review',str(reviewfile),'--out',str(self.root/'rendered')])
        self.assertEqual(code,0)
        self.assertIn('已完成 1 项',(self.root/'rendered/report.md').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
