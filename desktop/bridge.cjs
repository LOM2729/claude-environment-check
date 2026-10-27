'use strict';
const { spawn } = require('node:child_process');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const ACTIONS = new Set(['status','choose_config','collect','prepare','export_candidate','choose_readback','choose_report','handoff','reveal_workspace']);
function validate(action, payload) {
  if (!ACTIONS.has(action) || !payload || Object.getPrototypeOf(payload) !== Object.prototype) throw Error('请求不支持');
  const keys = {prepare:['node','clients','keep'], handoff:['node','clients','keep'], export_candidate:['plan_id']}[action] || [];
  if (Object.keys(payload).some(k => !keys.includes(k))) throw Error('请求包含不支持的字段');
  if (action === 'prepare' || (action === 'handoff' && Object.keys(payload).length)) {
    if (typeof payload.node !== 'string' || (action === 'prepare' && !payload.node) || payload.node.length > 256) throw Error('请选择具体节点');
    if (!Array.isArray(payload.clients) || (action === 'prepare' && !payload.clients.length) || payload.clients.length > 5 || payload.clients.some(v => !['browser','claude_gui','codex_gui','claude_cli','codex_cli'].includes(v))) throw Error('请选择实际使用的客户端');
    if (!Array.isArray(payload.keep) || payload.keep.length > 12 || payload.keep.some(v => typeof v !== 'string' || !v.trim() || v.length > 80)) throw Error('保留项无效');
  }
  if (action === 'export_candidate' && (typeof payload.plan_id !== 'string' || !/^[a-f0-9]{64}$/.test(payload.plan_id))) throw Error('请先准备方案');
}
function validSender(event, win) {
  return !!win && event.sender === win.webContents && event.senderFrame === win.webContents.mainFrame &&
    ['app://ui/index.html','app://ui/index.html#main'].includes(event.senderFrame.url);
}
function worker(command, prefix, workspace, action, payload) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, [...prefix, '--workspace', workspace], {shell:false, windowsHide:true, stdio:['pipe','pipe','pipe'], env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONUTF8:'1'}});
    let data=[], bytes=0, settled=false;
    const finish=(err,value)=>{if(settled)return;settled=true;clearTimeout(timer);err?reject(err):resolve(value);};
    const timer=setTimeout(()=>{child.kill();finish(Error('操作超时，请保留材料并重新核对'));},90000);
    child.stdout.on('data', chunk=>{bytes+=chunk.length;if(bytes>2*1024*1024){child.kill();finish(Error('结果过大，已停止读取'));}else data.push(chunk);});
    // Backend errors are fixed/redacted JSON. Raw stderr can contain private paths.
    child.stderr.on('data', ()=>{});
    child.on('error',()=>finish(Error('检查引擎无法启动，请重新解压完整安装包')));
    child.on('close',code=>{try{const v=JSON.parse(Buffer.concat(data).toString('utf8'));if(typeof v.ok!=='boolean'||!v.state||typeof v.state!=='object')throw Error();finish(null,v);}catch{finish(Error(code===0?'检查结果格式异常':'检查引擎未完成，请保留材料后重试'));}});
    child.stdin.on('error',()=>{});
    child.stdin.end(JSON.stringify({action,payload}));
  });
}
function bundledAsset(url, uiRoot) {
  const u=new URL(url);
  if(u.protocol!=='app:'||u.hostname!=='ui'||u.search||u.hash) throw Error('页面请求被拒绝');
  const names={'/index.html':'index.html','/app.js':'app.js','/styles.css':'styles.css'};
  if(!Object.hasOwn(names,u.pathname)) throw Error('页面资源不存在');
  return pathToFileURL(path.join(uiRoot,names[u.pathname])).href;
}
module.exports={validate,validSender,worker,bundledAsset};
