'use strict';
const { contextBridge, ipcRenderer } = require('electron');
const allowed=new Set(['status','choose_config','collect','prepare','export_candidate','choose_readback','choose_report','handoff','reveal_workspace']);
const tools=new Set(['intake_start','intake_answer','intake_copy','browser_start','browser_status','browser_stop','browser_copy',
  'update_check','cleanup_plan','cleanup_apply','cleanup_reconcile','cleanup_restore','cleanup_latest','native_inspect',
  'native_plan','native_apply','native_rollback','native_latest','guard_export','remote_export','copy_plan_request','reveal_tool']);
contextBridge.exposeInMainWorld('desktop',Object.freeze({invoke:(action,payload={})=>{
  if(!allowed.has(action))return Promise.reject(new Error('不支持的操作'));
  return ipcRenderer.invoke('desktop:action',action,payload);
},tool:(operation,input={})=>{
  if(!tools.has(operation))return Promise.reject(new Error('不支持的专项工具'));
  return ipcRenderer.invoke('desktop:tool',operation,input);
}}));
