'use strict';
(() => {
  const view = document.querySelector('#view-tools');
  const one = selector => view.querySelector(selector);
  const all = selector => [...view.querySelectorAll(selector)];
  const selector = one('#tool-selector');
  const buttons = all('[data-tool]');
  const results = new Map();
  const tickets = new Map();
  const tasks = {setup:'配置',diagnose:'排障',cleanup:'清理',compare:'比较路线',maintenance:'更新或修复',
    hardening:'系统防护',remote:'远端部署',billing:'账单与权益',subscribe:'订阅准备'};
  const values = {first:'首次准备',returning:'重新准备',existing:'已有订阅',macos:'macOS',windows:'Windows',linux:'Linux',
    local:'本机',vm:'虚拟机',vps:'VPS',native:'原生系统',wsl:'WSL',vm_guest:'虚拟机客机',remote:'远端',
    browser:'浏览器',desktop:'Claude Desktop',code:'Claude Code',ide_code:'IDE 中的 Claude Code',mixed:'多种客户端',
    simplicity:'省事',isolation:'隔离',cost:'成本',performance:'性能',available:'已准备',none:'暂时没有',
    absent:'尚未导入',imported:'已导入',effective:'已确认生效',dns:'DNS',connection:'连接',tls:'TLS',login:'登录',
    permission:'权限',rate_limit:'限额',service_error:'服务异常',billing:'账单',unclear:'还不清楚',
    cache:'缓存',history:'历史',configuration:'配置',uninstall:'卸载',site:'指定站点',profile:'指定浏览器资料',
    client_root:'客户端配置根',update:'更新',reinstall:'重装',repair:'修复',web:'网页',apple:'Apple',google:'Google',
    api:'API',other:'其他',missing_entitlement:'权益未到账',duplicate_charge:'重复扣款',plan_mismatch:'套餐不符',
    renewal:'续费',free:'Free',pro:'Pro',max:'Max',undecided:'尚未决定'};
  let busy = false;
  let intake;
  let browser;
  let reveal = false;
  let timer;

  function options(select, entries) {
    select.replaceChildren(...entries.map(([value,label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      return option;
    }));
  }

  function controls() {
    const active = browser && !browser.finished;
    const available = {
      intake_answer:!!intake?.question, intake_copy:!!intake,
      browser_start:!active, browser_stop:!!active, browser_copy:!!active && browser.can_copy === true,
      native_plan:!!one('#native-policy').value, reveal_tool:reveal,
      ...Object.fromEntries(['cleanup_apply','cleanup_reconcile','cleanup_restore','native_apply','native_rollback']
        .map(action => [action,tickets.has(action)])),
    };
    for (const button of buttons) button.disabled = busy || available[button.dataset.tool] === false;
  }

  function render() {
    const current = selector.value;
    for (const panel of all('[data-tool-panel]')) panel.hidden = panel.dataset.toolPanel !== current;
    const result = results.get(current) || {};
    const message = one('#tool-message');
    message.textContent = result.message || '';
    message.hidden = !result.message;
    const details = one('#tool-details');
    details.replaceChildren(...(result.details || []).map(text => {
      const item = document.createElement('li');
      item.textContent = text;
      return item;
    }));
    details.hidden = !details.childElementCount;
    controls();
  }

  function inputs(action, button) {
    if (action === 'intake_start') return {task:one('#intake-task').value};
    if (action === 'intake_answer' || action === 'intake_copy') {
      const {token, revision} = intake;
      return action === 'intake_copy' ? {token, revision} : {token, revision, value:one('#intake-value').value};
    }
    if (action === 'cleanup_plan') return {kind:one('#cleanup-kind').value};
    if (action === 'native_plan') return {kind:one('#native-kind').value,domain:one('#native-domain').value.trim().toLowerCase(),policy:one('#native-policy').value};
    if (action === 'copy_plan_request') return {kind:button.dataset.plan};
    if (tickets.has(action)) return {token:tickets.get(action)};
    return {};
  }

  function scheduleBrowser() {
    clearTimeout(timer);
    if (browser && !browser.finished) timer = setTimeout(() => {
      if (!busy && !view.hidden && selector.value === 'browser') run('browser_status');
      else scheduleBrowser();
    }, 1000);
  }

  function accept(action, result, panel) {
    if (action.startsWith('intake_') && result.token) {
      intake = result;
      one('#intake-question').hidden = !intake.question;
      if (intake.question) {
        one('#intake-prompt').textContent = intake.question.prompt;
        options(one('#intake-value'), [...intake.question.options.map(v => [v,values[v] || v]),['','暂不确定']]);
      }
    }
    if (action.startsWith('browser_') && typeof result.finished === 'boolean') browser = result;
    if (result.policies) options(one('#native-policy'), result.policies.map(v => [v,v]));
    if (action.startsWith('cleanup_') || (action.startsWith('native_') && action !== 'native_inspect')) {
      const prefix = action.split('_')[0] + '_';
      for (const key of tickets.keys()) if (key.startsWith(prefix)) tickets.delete(key);
      for (const key of result.next || []) if (key.startsWith(prefix) && result.token) tickets.set(key,result.token);
    }
    if (result.can_reveal) reveal = true;
    results.set(panel, result);
  }

  async function run(action, button) {
    if (busy) return;
    const panel = selector.value;
    busy = true;
    controls();
    try {
      const response = await window.desktop.tool(action, inputs(action,button));
      if (response.ok && !response.cancelled) accept(action,response.tool,panel);
      else if (response.error !== 'BUSY') {
        if (!response.cancelled && action === 'native_inspect') options(one('#native-policy'), []);
        if (!response.cancelled && tickets.has(action)) tickets.delete(action);
        const previous = results.get(panel);
        results.set(panel, {message:response.message || response.tool?.message, details:previous?.details});
      }
    } catch {
      results.set(panel,{message:'专项操作未完成，请核对选项或读取最新记录。'});
    } finally {
      busy = false;
      render();
      scheduleBrowser();
    }
  }

  options(one('#intake-task'), Object.entries(tasks));
  selector.addEventListener('change', render);
  for (const button of buttons) {
    if (button.dataset.tool !== 'native_plan') button.addEventListener('click', () => run(button.dataset.tool,button));
  }
  one('#native-rule').addEventListener('submit', event => {
    event.preventDefault();
    if (one('[data-tool="native_plan"]').disabled === false) run('native_plan');
  });
  render();
})();
