'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {JSDOM} = require('jsdom');
const {validateTool} = require('../bridge.cjs');
const {createToolActions} = require('../tools-main.cjs');

const token = 'a'.repeat(32);
const response = tool => ({ok:true,state:{},tool});

test('tool IPC excludes renderer paths, approvals, runtime commands and serve', () => {
  for (const [action,input] of [
    ['cleanup_plan',{kind:'cli',path:'/tmp/other'}], ['cleanup_apply',{token,stopped:true}],
    ['guard_export',{path:'/tmp/plan.json'}], ['intake_copy',{token,revision:0,kit:'/other'}],
    ['browser_start',{approved:true}], ['browser_serve',{token}], ['__proto__',{}],
  ]) assert.throws(() => validateTool(action,input));
  validateTool('cleanup_plan',{kind:'cli'});
  validateTool('cleanup_apply',{token});
  validateTool('browser_start',{});
});

test('cleanup requires actual preview and native stopped-writers confirmation', async () => {
  const calls = [];
  let confirmation = {response:1,checkboxChecked:false};
  const actions = createToolActions({
    call: async (...args) => {
      calls.push(args);
      return response({token,next:['cleanup_apply'],details:['缓存目录'],folder:'/private/material'});
    },
    window:()=>null,
    dialog:{showOpenDialog:async()=>({filePaths:['/selected']}),showMessageBox:async()=>confirmation},
  });
  await assert.rejects(actions.operate('cleanup_apply',{token}),/最新记录/);
  const preview = await actions.operate('cleanup_plan',{kind:'cli'});
  assert.equal(preview.tool.folder,undefined);
  assert.deepEqual(calls.at(-1).slice(0,2),['tool',{operation:'cleanup_plan',input:{kind:'cli',path:'/selected'}}]);
  assert.equal((await actions.operate('cleanup_apply',{token})).cancelled,true);
  assert.equal(calls.length,1);
  confirmation = {response:1,checkboxChecked:true};
  await actions.operate('cleanup_apply',{token});
  assert.deepEqual(calls.at(-1).slice(0,2),['tool',{operation:'cleanup_apply',input:{token,stopped:true}}]);
});

test('browser starts only after consent, copies only loopback, and stops owned child', async () => {
  const calls = [];
  const clipboard = [];
  const url = 'http://127.0.0.1:4444/' + 'x'.repeat(43) + '/';
  let choice = {response:0};
  let stopped = false;
  const actions = createToolActions({
    call: async (_action,{operation},options) => {
      calls.push(operation);
      if (operation === 'browser_prepare') return response({token});
      if (operation === 'browser_status') return response({url,finished:false});
      return new Promise(resolve => options.onChild({kill(){stopped=true;resolve(response({}));}}));
    },
    window:()=>null, dialog:{showMessageBox:async()=>choice}, clipboard:{writeText:text=>clipboard.push(text)},
  });
  assert.equal((await actions.operate('browser_start',{})).cancelled,true);
  assert.deepEqual(calls,[]);
  choice = {response:1};
  await actions.operate('browser_start',{});
  const status = await actions.operate('browser_status',{});
  assert.equal(status.tool.url,undefined);
  assert.deepEqual(clipboard,[]);
  await actions.operate('browser_copy',{});
  assert.deepEqual(clipboard,[url]);
  await actions.operate('browser_stop',{});
  assert.equal(stopped,true);
});

test('special tools stay idle on entry and gate writes on preview tokens', async t => {
  const dir = path.join(__dirname,'../ui');
  const dom = new JSDOM(fs.readFileSync(path.join(dir,'index.html'),'utf8'), {runScripts:'outside-only'});
  t.after(() => dom.window.close());
  const one = selector => dom.window.document.querySelector(selector);
  const calls = [];
  dom.window.desktop = {invoke:async()=>({ok:true,state:{}}),tool:async (action,input) => {
    calls.push([action,JSON.parse(JSON.stringify(input))]);
    return response(action === 'cleanup_plan'
      ? {token,next:['cleanup_apply'],message:'预览',details:['<img src=x>']}
      : {token,next:['cleanup_reconcile'],message:'已隔离'});
  }};
  for (const file of ['app.js','tools.js']) {
    vm.runInContext(fs.readFileSync(path.join(dir,file),'utf8'),dom.getInternalVMContext());
  }
  await new Promise(setImmediate);
  one('[data-view="tools"]').click();
  assert.equal(one('#view-tools').hidden,false);
  const choose = one('#tool-selector');
  choose.value = 'cleanup';
  choose.dispatchEvent(new dom.window.Event('change'));
  const apply = one('[data-tool="cleanup_apply"]');
  assert.equal(apply.disabled,true);
  assert.deepEqual(calls,[]);
  one('[data-tool="cleanup_plan"]').click();
  await new Promise(setImmediate);
  assert.equal(one('#tool-details li').textContent,'<img src=x>');
  assert.equal(one('#tool-details img'),null);
  assert.equal(apply.disabled,false);
  apply.click();
  await new Promise(setImmediate);
  assert.equal(apply.disabled,true);
  assert.equal(one('[data-tool="cleanup_reconcile"]').disabled,false);
  assert.deepEqual(calls,[['cleanup_plan',{kind:'cli'}],['cleanup_apply',{token}]]);
});
