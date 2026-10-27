'use strict';
const { contextBridge, ipcRenderer } = require('electron');
const allowed=new Set(['status','choose_config','collect','prepare','export_candidate','choose_readback','choose_report','handoff','reveal_workspace']);
contextBridge.exposeInMainWorld('desktop',Object.freeze({invoke:(action,payload={})=>{
  if(!allowed.has(action))return Promise.reject(new Error('不支持的操作'));
  return ipcRenderer.invoke('desktop:action',action,payload);
}}));
