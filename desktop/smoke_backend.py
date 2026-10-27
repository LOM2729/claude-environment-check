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
print('Frozen backend: CLI version, JSON/YAML, snapshots, handoff and offline candidate passed; no network or system configuration.')
