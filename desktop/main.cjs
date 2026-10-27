'use strict';
const { app, BrowserWindow, ipcMain, protocol, dialog, clipboard, shell } = require('electron');
const path = require('node:path');
const {fileURLToPath} = require('node:url');
const fs = require('node:fs');
const bridge = require('./bridge.cjs');
protocol.registerSchemesAsPrivileged([{scheme:'app',privileges:{standard:true,secure:true,supportFetchAPI:true}}]);
let win, busy=false;
const executable=()=> app.isPackaged ? [path.join(process.resourcesPath,'backend',process.platform==='win32'?'claude-check-backend.exe':'claude-check-backend'),[]] : [process.env.CLAUDE_KIT_PYTHON || 'python3',[path.join(__dirname,'backend.py')]];
const root=()=>path.join(app.getPath('userData'),'workspace');
async function call(action,payload={}) {
  const [command,prefix]=executable();
  return bridge.worker(command,prefix,root(),action,payload);
}
async function operate(action,payload) {
  if(action==='choose_config'||action==='choose_readback'||action==='choose_report') {
    const selected=await dialog.showOpenDialog(win,{title:action==='choose_report'?'选择已有检查报告 JSON':action==='choose_config'?'选择代理客户端导出的配置':'选择客户端实际导出的配置',properties:['openFile'],filters:[{name:'代理配置',extensions:action==='choose_report'?['json']:['yaml','yml','json','conf']}]});
    if(selected.canceled)return {...await call('status'),cancelled:true,message:'已取消，当前配置未改变。'};
    return call(action==='choose_report'?'import_report':action==='choose_config'?'select_config':'verify_readback',{path:selected.filePaths[0]});
  }
  if(action==='export_candidate') {
    const current=await call('status');
    if(!current.ok)return current;
    if(!current.state.plan?.ready||current.state.plan.id!==payload.plan_id)return {ok:false,error:'PLAN_CHANGED',message:'方案已变化，请重新准备',state:current.state};
    const plan=current.state.plan;
    const confirm=await dialog.showMessageBox(win,{type:'question',title:'确认导出本次候选',message:'仅导出新的配置文件',detail:'原配置不会被覆盖，也不会自动导入、重启代理或更改系统设置。\n'+(plan.activation_ready===false?'应用行为仍有待核对项。导出后先交给 Codex 继续核验，不要直接启用。\n':'导入前仍需确认客户端设置和当前控制通道。\n')+JSON.stringify(plan.summary,null,2).slice(0,2500),buttons:['返回核对','确认并选择保存位置'],defaultId:0,cancelId:0,noLink:true});
    if(confirm.response!==1)return {...current,cancelled:true,message:'已取消导出。'};
    const picked=await dialog.showSaveDialog(win,{title:'另存新的候选配置（不覆盖现有文件）',defaultPath:path.join(app.getPath('downloads'),plan.candidate_name||'Claude-candidate.conf')});
    if(picked.canceled||!picked.filePath)return {...current,cancelled:true,message:'已取消保存。'};
    if(fs.existsSync(picked.filePath))throw Error('所选文件已存在，请选择新的文件名');
    return call('confirm_export',{destination:picked.filePath,plan_id:payload.plan_id});
  }
  if(action==='handoff') {
    const result=await call('handoff',{...payload,kit_path:app.isPackaged?path.join(process.resourcesPath,'kit'):path.resolve(__dirname,'..')});
    if(result.ok&&typeof result.prompt==='string')clipboard.writeText(result.prompt);
    return result;
  }
  if(action==='reveal_workspace') {
    const result=await call('status');
    if(fs.existsSync(root()))await shell.openPath(root());
    return result;
  }
  return call(action,payload);
}
const primary=app.requestSingleInstanceLock();
if(!primary)app.quit();
app.on('second-instance',()=>{if(win){if(win.isMinimized())win.restore();win.focus();}});
if(primary)app.whenReady().then(async()=>{
  protocol.handle('app',request=>{try{const url=bridge.bundledAsset(request.url,path.join(__dirname,'ui'));const file=fileURLToPath(url);return new Response(fs.readFileSync(file),{headers:{'Content-Type':file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.js')?'text/javascript; charset=utf-8':'text/css; charset=utf-8'}});}catch{return new Response('Not found',{status:404});}});
  win=new BrowserWindow({width:1100,height:790,minWidth:820,minHeight:620,title:'Claude 环境检测',backgroundColor:'#f4f7f8',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true,webviewTag:false}});
  win.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  win.webContents.session.setPermissionCheckHandler(()=>false);
  win.webContents.session.webRequest.onBeforeRequest((details,callback)=>callback({cancel:!details.url.startsWith('app://ui/')}));
  win.webContents.on('will-navigate',event=>event.preventDefault());
  win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  win.webContents.on('will-attach-webview',event=>event.preventDefault());
  ipcMain.handle('desktop:action',async(event,action,payload)=>{
    if(!bridge.validSender(event,win))throw Error('不允许的请求来源');
    bridge.validate(action,payload);
    if(busy)return {ok:false,error:'BUSY',message:'上一项操作尚未结束',state:{}};
    busy=true;
    try{return await operate(action,payload);}catch(error){return {ok:false,error:'DESKTOP_OPERATION_FAILED',message:error.message,state:{}};}finally{busy=false;}
  });
  await win.loadURL('app://ui/index.html');
});
app.on('window-all-closed',()=>app.quit());
