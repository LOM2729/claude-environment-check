'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { token } = require('./bridge.cjs');

const confirmations = {
  cleanup_apply: ['隔离所选客户端的缓存', '请退出所选客户端和可能写入缓存的后台进程。', '隔离缓存'],
  cleanup_restore: ['恢复已隔离的缓存', '请退出所选客户端和后台进程。已出现的新文件会阻止恢复。', '恢复缓存'],
  native_apply: ['写入所选域名规则', '请退出代理客户端和它的后台进程。完成后需要手动核对实际路由。', '备份并写入'],
  native_rollback: ['恢复原规则文件', '请退出代理客户端和它的后台进程。文件有新改动时会阻止恢复。', '恢复原文件'],
};

function createToolActions({ call, root, kit, window, dialog, clipboard, shell }) {
  const previews = new Map();
  let latestFolder;
  let browser;
  const backend = (operation, input = {}, options) => call('tool', {operation, input}, options);
  const success = (message, fields = {}) => ({ok:true, state:{}, tool:{message, ...fields}});
  const cancelled = () => ({...success('已取消。'), cancelled:true});

  async function confirm(message, detail, label, checkboxLabel) {
    const result = await dialog.showMessageBox(window(), {type:'question', title:message, message, detail,
      buttons:['取消', label], defaultId:0, cancelId:0, noLink:true,
      ...(checkboxLabel ? {checkboxLabel, checkboxChecked:false} : {})});
    return result.response === 1 && (!checkboxLabel || result.checkboxChecked);
  }

  function publish(result) {
    if (!result.ok || !result.tool) return result;
    const {folder, clipboard_text, url, ...tool} = result.tool;
    if (typeof folder === 'string') latestFolder = folder;
    if (typeof clipboard_text === 'string') clipboard.writeText(clipboard_text);
    if (token(tool.token)) {
      for (const action of Object.keys(confirmations)) {
        if (tool.next?.includes(action)) previews.set(action, {token:tool.token, details:tool.details});
      }
    }
    return {...result, tool:{...tool, can_reveal:!!latestFolder}};
  }

  function stop() {
    if (browser && !browser.finished) {
      browser.stopped = true;
      browser.child?.kill();
    }
  }

  async function browserAction(operation) {
    if (operation === 'browser_start') {
      if (browser && !browser.finished) return success('本机检测页已启动。', {finished:false});
      if (!await confirm('启动本机浏览器检测页',
          '检测页在本机临时运行。你点击页面里的检测按钮后，浏览器会连接 stun.cloudflare.com:3478，Cloudflare 能看到该次请求的源 IP。',
          '启动检测页')) return cancelled();
      const preparation = await backend('browser_prepare', {approved:true});
      if (!preparation.ok) return preparation;
      const job = {token:preparation.tool.token, finished:false, stopped:false};
      if (!token(job.token)) throw Error('检测页方案无效');
      browser = job;
      backend('browser_serve', {token:job.token}, {timeout:135000,onChild:child=>{job.child=child;}})
        .then(result=>{job.failure=result.ok ? null : result.message;}, ()=>{job.failure='检测页提前结束。';})
        .finally(()=>{job.finished=true;});
      return publish({...preparation, tool:{...preparation.tool, finished:false}});
    }
    if (!browser) return success('请先启动检测页。', {finished:true});
    if (operation === 'browser_stop') {
      stop();
      return success('检测页正在停止。', {finished:false});
    }
    if (browser.stopped) return success(browser.finished ? '检测页已停止。' : '检测页正在停止。', {finished:browser.finished});
    const result = await backend('browser_status', {token:browser.token});
    if (result.ok && result.tool.finished) return publish(result);
    if (browser.finished) return success(browser.failure || '检测页已结束。', {finished:true, can_reveal:!!latestFolder});
    if (!result.ok) return result;
    const ready = typeof result.tool.url === 'string' &&
      /^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/[A-Za-z0-9_-]{43}\/$/.test(result.tool.url);
    if (operation === 'browser_copy' && ready) {
      clipboard.writeText(result.tool.url);
      return publish({...result, tool:{...result.tool, can_copy:true, message:'已复制，请用平时的浏览器资料打开。'}});
    }
    return publish({...result, tool:{...result.tool, can_copy:ready}});
  }

  async function choose(properties, title, filters) {
    const selection = await dialog.showOpenDialog(window(), {title, properties, filters});
    return selection.canceled ? null : selection.filePaths[0];
  }

  async function operate(operation, input) {
    if (operation.startsWith('browser_')) return browserAction(operation);
    if (operation === 'reveal_tool') {
      if (!latestFolder) return success('请先生成或读取一份材料。');
      try {
        const tools = fs.realpathSync(path.join(root(), 'tools'));
        const folder = fs.realpathSync(latestFolder);
        const relative = path.relative(tools, folder);
        if (!relative || relative === '..' || relative.startsWith('..' + path.sep) ||
            path.isAbsolute(relative) || !fs.statSync(folder).isDirectory() || await shell.openPath(folder)) throw Error();
      } catch {
        throw Error('本机材料目录无法打开');
      }
      return success('已打开最近的材料目录。', {can_reveal:true});
    }
    if (operation === 'copy_plan_request') {
      const command = input.kind === 'guard' ? 'guard-plan' : 'remote-plan';
      clipboard.writeText('请用我们维护的 Claude 环境工具 https://github.com/LOM2729/claude-environment-check ，' +
        '按适用平台 Skill 的 execution-capabilities.md 先向我核对具体目标、影响范围和独立恢复入口，' +
        '然后使用 ' + command + ' 生成供桌面工具选择的私有计划 JSON。当前只准备和审阅计划。');
      return success('已复制，可交给 Codex 准备计划。');
    }
    if (operation === 'intake_copy') input = {...input, kit:kit()};
    if (operation === 'update_check') {
      const selected = await choose(['openDirectory'], '选择已安装的 Claude 环境 Skill 目录');
      if (!selected || !await confirm('核对 Skill 更新', '本轮读取 GitHub 的公开版本和文件清单，并在本机比较所选 Skill 的内容。', '开始核对')) return cancelled();
      input = {path:selected, approved:true};
    }
    if (operation === 'cleanup_plan') {
      const selected = await choose(['openDirectory'], input.kind === 'cli' ?
        '选择 Claude Code 的 .claude 目录' : '选择 Claude Desktop 的 Claude 资料目录');
      if (!selected) return cancelled();
      input = {...input, path:selected};
    }
    if (operation === 'guard_export' || operation === 'remote_export') {
      const selected = await choose(['openFile'], '选择已审阅的计划 JSON', [{name:'JSON 计划',extensions:['json']}]);
      if (!selected) return cancelled();
      input = {path:selected};
    }
    if (Object.hasOwn(confirmations, operation)) {
      const preview = previews.get(operation);
      if (!preview || preview.token !== input.token) throw Error('请先读取最新记录或生成方案');
      const [title, note, label] = confirmations[operation];
      const details = Array.isArray(preview.details) ? preview.details.join('\n').slice(0,3500) : '';
      if (!await confirm(title, [details,note].filter(Boolean).join('\n\n'), label, '我已退出相关客户端和后台进程')) return cancelled();
      previews.delete(operation);
      input = {...input, stopped:true};
    }
    return publish(await backend(operation, input));
  }
  return {operate, stop};
}
module.exports = {createToolActions};
