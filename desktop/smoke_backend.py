"""Smoke test the frozen engine, with synthetic files only and no collection."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT/'desktop/backend-dist/claude-check-backend'/('claude-check-backend.exe' if os.name=='nt' else 'claude-check-backend')
assert EXE.is_file()
version=subprocess.run([str(EXE),'--cli','--version'],capture_output=True,text=True,encoding='utf-8',check=True,timeout=30)
assert (ROOT/'VERSION').read_text().strip() in version.stdout
with tempfile.TemporaryDirectory(prefix='desktop-frozen-smoke-') as temp:
    folder=Path(temp).resolve();workspace=folder/'workspace'
    config=folder/'test.json'
    config.write_text(json.dumps({'mode':'rule','proxies':[{'name':'Sample','type':'http','server':'192.0.2.2','port':8080}], 'rules':['GEOIP,CN,DIRECT','MATCH,Sample']}),encoding='utf-8')
    def call(action,payload):
        result=subprocess.run([str(EXE),'--workspace',str(workspace)],input=json.dumps({'action':action,'payload':payload}),capture_output=True,text=True,encoding='utf-8',timeout=30,check=True)
        value=json.loads(result.stdout);assert value['ok'],value
        return value
    assert call('status',{})['state']['checks']==[]
    state=call('select_config',{'path':str(config)})['state']
    assert state['config']['node_names']==['Sample']
    handoff=call('handoff',{'kit_path':str(ROOT/'desktop/kit')})
    assert handoff['prompt'] and '网络' in handoff['prompt']
    engine=json.loads((Path(handoff['state']['handoff_path']).parent/'desktop-engine.private.json').read_text(encoding='utf-8'))
    assert engine['engine_command']==[str(EXE)] and engine['cli_prefix']==[str(EXE),'--cli']
    assert subprocess.run(engine['cli_prefix']+['--version'],capture_output=True,text=True,check=True).stdout.strip()==engine['kit_version']
    # Both resource files and YAML's frozen import must work without system Python.
    yaml=folder/'test.yaml';yaml.write_text('mode: rule\nproxies:\n  - name: Sample\n    type: http\n    server: 192.0.2.2\n    port: 8080\nrules:\n  - GEOIP,CN,DIRECT\n  - MATCH,Sample\n',encoding='utf-8')
    assert call('select_config',{'path':str(yaml)})['state']['config']['format']=='yaml'
    route=folder/'candidate'
    generated=subprocess.run([str(EXE),'--cli','ai-route','--config',str(config),'--node','Sample','--out',str(route)],capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert generated.returncode==0,generated.stdout+generated.stderr
    assert (route/'candidate.json').is_file()
    collection=folder/'synthetic-collection.json'
    collection.write_text(json.dumps({'schema':'claude-setup-collection/1','platform':'macos','target_alias':'synthetic',
        'collected_at':'2026-10-20T12:00:00+00:00','native':{},'environment':{},'config':None,'browser':None,
        'claude_command_found':False,'evidence':'synthetic_fixture'}),encoding='utf-8')
    report=folder/'report'
    subprocess.run([str(EXE),'--cli','report','--input',str(collection),'--out',str(report)],capture_output=True,text=True,check=True,timeout=30)
    imported=call('import_report',{'path':str(report/'report.json')})
    assert imported['state']['report_source']['imported'] and imported['state']['stage']=='prepare'
    worker=EXE.parent/'_internal/network_checks.py'
    result=subprocess.run([str(EXE),str(worker),'--worker'],input='{}',capture_output=True,text=True,check=True,timeout=30)
    assert json.loads(result.stdout)['outcome']=='invalid_response'
    scope=folder/'scope.md';scope.write_text('仅合成材料；不配置真实网络。',encoding='utf-8')
    checkpoint=subprocess.run([str(EXE),'--cli','workflow-save','--config',str(config),'--scope-file',str(scope),
        '--target-alias','synthetic','--platform','windows' if os.name=='nt' else 'macos','--stage','prepare',
        '--next-step','核对本轮示例','--out',str(folder/'checkpoint')],capture_output=True,text=True,encoding='utf-8',
        env={**os.environ,'PYTHONIOENCODING':'cp1252'},check=True,timeout=30)
    assert json.loads(checkpoint.stdout)['status']=='已完成'
    capabilities=subprocess.run([str(EXE),'--cli','capabilities'],capture_output=True,text=True,encoding='utf-8',check=True,timeout=30)
    declared=json.loads(capabilities.stdout)
    assert len(declared['features'])==7 and not declared['system_changes_performed']
    facts=folder/'facts.json'
    facts.write_text(json.dumps([{'field':'platform','state':'known','value':'macos'},
                                {'field':'priority','state':'known','value':'cost'}]),encoding='utf-8')
    intake=subprocess.run([str(EXE),'--cli','intake-start','--task','compare','--answers',str(facts),
                           '--output',str(folder/'intake.json')],capture_output=True,text=True,encoding='utf-8',check=True,timeout=30)
    assert json.loads(intake.stdout)['status']=='explanation_only'
    tools_intake=call('tool',{'operation':'intake_start','input':{'task':'compare'}})['tool']
    assert tools_intake['question']['field']=='platform'
    assert (EXE.parent/'_internal/browser_webrtc.html').is_file()
    guard_input=folder/'guard-input.json'
    guard_input.write_text(json.dumps({'schema':'clearpath-guard-input/1','scope':'fixture','platform':'windows',
        'policy':'unified-v4','interfaces':['Ethernet'],'core_path':r'C:\Example\mihomo.exe',
        'nodes':[{'address':'192.0.2.10','ports':[443],'protocol':'tcp'}]}),encoding='utf-8')
    guard=subprocess.run([str(EXE),'--cli','guard-plan','--input',str(guard_input),
                          '--output',str(folder/'guard-plan.json')],capture_output=True,text=True,encoding='utf-8',check=True,timeout=30)
    assert not json.loads(guard.stdout)['system_changes']
    assert (EXE.parent/'_internal/system_guard_windows.ps1').is_file()
    # Export a real target-platform entry without opening a terminal or changing policy.
    native_input=folder/'native-guard-input.json'
    native_request=json.loads(guard_input.read_text(encoding='utf-8'))
    if os.name!='nt':
        native_request.update(platform='macos',interfaces=['en0'])
        native_request.pop('core_path')
    native_input.write_text(json.dumps(native_request),encoding='utf-8')
    native_plan=folder/'native-guard-plan.json'
    planned=subprocess.run([str(EXE),'--cli','guard-plan','--input',str(native_input),'--output',str(native_plan)],
                           capture_output=True,text=True,encoding='utf-8',check=True,timeout=30)
    pin=json.loads(planned.stdout)['plan_sha256']
    exported=subprocess.run([str(EXE),'--cli','guard-export','--plan',str(native_plan),'--plan-sha256',pin,
                             '--out',str(folder/'manual-entry')],capture_output=True,text=True,encoding='utf-8',check=True,timeout=30)
    export_result=json.loads(exported.stdout)
    assert export_result['launcher_generated'] and not export_result['system_changes']
    manifest=json.loads((folder/'manual-entry/launch-manifest.private.json').read_text(encoding='utf-8'))
    assert manifest['runtime']['mode']=='frozen' and manifest['authorization_saved'] is False
    assert not manifest['network_verified']
    desktop_guard=call('tool',{'operation':'guard_export','input':{'path':str(native_plan)}})['tool']
    desktop_manifest=json.loads((Path(desktop_guard['folder'])/'launch-manifest.private.json').read_text(encoding='utf-8'))
    assert desktop_manifest['runtime']['mode']=='frozen' and desktop_manifest['authorization_saved'] is False
print('Frozen backend: legacy workflow, seven feature imports, offline intake/guard plans and assets passed; no network or system configuration.')
