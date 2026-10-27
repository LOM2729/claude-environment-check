'use strict';

// Renderer accepts only saved state and the fixed preload actions below.
// Missing values remain incomplete; navigating never changes workflow state.
(() => {
  const stages = ['prepare', 'confirm', 'configure', 'verify', 'deliver'];
  const labels = { prepare: '准备', confirm: '确认', configure: '配置', verify: '验证', deliver: '交付', results: '检查结果', help: '使用说明', recovery: '恢复资料' };
  const allowedActions = new Set(['status', 'choose_config', 'choose_report', 'collect', 'prepare', 'export_candidate', 'choose_readback', 'handoff', 'reveal_workspace']);
  const actionMessages = { status: '正在读取已保存的进度…', choose_config: '请在文件窗口选择现有配置…', choose_report: '请选择本机已有的检查报告 JSON 文件…', collect: '正在进行本地只读检查…', prepare: '正在准备本轮方案…', export_candidate: '请确认方案并选择新文件的保存位置…', choose_readback: '请选择从实际客户端重新导出的配置…', handoff: '正在生成并复制续做提示词…', reveal_workspace: '正在打开本机材料目录…' };
  const successMessages = { status: '已读取保存的进度。未重新扫描或联网。', choose_config: '已读取配置，请选择本次使用的节点。', choose_report: '已导入历史报告，未执行当前环境检查。', collect: '本地只读检查已返回，请查看检查结果。', prepare: '方案已返回，请查看就绪状态与未完成项。', export_candidate: '导出操作已返回，请按提示继续。', choose_readback: '文件核对已返回，实际网络仍需单独验证。', handoff: '续做提示词已复制。请粘贴到 Codex 中继续。', reveal_workspace: '已打开材料目录。' };
  let state = {};
  let view = 'prepare';
  let busy = false;
  let draftDirty = false;
  let selectedNode = '';
  let selectedClients = [];
  let selectedKeep = [];
  const $ = (selector) => document.querySelector(selector);
  const all = (selector) => Array.from(document.querySelectorAll(selector));
  const string = (value, fallback = '') => typeof value === 'string' ? value : fallback;
  const strings = (value) => Array.isArray(value) ? value.filter((item) => typeof item === 'string') : [];
  const object = (value) => value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  const plan = () => object(state.plan);
  const config = () => object(state.config);
  const stageIndex = () => Math.max(0, stages.indexOf(state.stage));
  const hasPlan = () => Boolean(plan() && string(plan().id));
  const canConfigure = () => hasPlan() && stageIndex() >= 2;
  const nodeNames = () => [...new Set(strings(config()?.node_names))];
  const setText = (selector, value) => { $(selector).textContent = value; };

  function canView(target) {
    if (target === 'confirm') return hasPlan();
    if (target === 'configure' || target === 'verify' || target === 'deliver') return canConfigure();
    return Object.hasOwn(labels, target);
  }

  function showView(target, focus = true) {
    if (!canView(target)) return;
    view = target;
    all('.view').forEach((section) => { section.hidden = section.id !== `view-${view}`; });
    all('[data-view]').forEach((button) => {
      button.removeAttribute('aria-current');
      if (button.dataset.view === view && button.closest('.sidebar')) button.setAttribute('aria-current', stages.includes(view) ? 'step' : 'page');
    });
    setText('#breadcrumb', `${stages.includes(view) ? '配置向导' : '资料与帮助'} / ${labels[view]}`);
    if (focus) {
      $('#main').scrollTop = 0;
      $('#main').focus({ preventScroll: true });
    }
  }

  function checkedValues(name) {
    return all(`input[name="${name}"]:checked`).map((input) => input.value);
  }

  function syncDraft() {
    selectedNode = $('#node-select').value;
    selectedClients = checkedValues('clients');
    selectedKeep = checkedValues('keep');
    draftDirty = true;
    updateControls();
  }

  function displayChoices(name, values) {
    const known = all(`input[name="${name}"]`);
    return values.map((value) => {
      const input = known.find((item) => item.value === value);
      return input ? input.parentElement.querySelector('span').textContent : value;
    }).join('、');
  }

  function updateControls() {
    all('button').forEach((button) => {
      let enabled = true;
      if (button.dataset.view) enabled = canView(button.dataset.view);
      const action = button.dataset.action;
      if (action === 'prepare') enabled = Boolean(config() && selectedNode && selectedClients.length);
      if (action === 'export_candidate') enabled = hasPlan() && plan().ready === true && !draftDirty;
      if (action === 'choose_readback') enabled = canConfigure();
      button.disabled = busy || !enabled;
    });
    all('input').forEach((input) => { input.disabled = busy; });
    $('#node-select').disabled = busy || nodeNames().length === 0;
    $('#main').setAttribute('aria-busy', String(busy));
    const ready = Boolean(config() && selectedNode && selectedClients.length);
    setText('#prepare-guidance', ready ? (draftDirty && hasPlan() ? '选择已变更，请重新准备方案后再导出。' : '准备方案不会修改当前网络。') : '选择配置、节点和客户端后，即可准备方案。');
  }

  function make(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function normalizedChecks() {
    return Array.isArray(state.checks) ? state.checks.filter((item) => object(item)).map((item) => ({
      title: string(item.title, '检查项目'),
      done: item.status === '已完成',
      reason: string(item.reason, item.status === '已完成' ? '已记录完成结果。' : '尚未取得本项的完成证据。'),
      next: string(item.next_step, item.status === '已完成' ? '' : '复制续做提示词，在 Codex 中核实本项。'),
    })) : [];
  }

  function renderChecks() {
    const checks = normalizedChecks();
    const imported = object(state.report_source)?.imported === true;
    all('[data-checks]').forEach((container) => {
      container.replaceChildren();
      if (imported) container.append(make('p', 'report-note', '导入的历史报告，仅供参考；不是当前环境实测。'));
      if (!checks.length) {
        const empty = make('div', 'empty-state');
        empty.append(make('strong', '', '还没有检查结果'), make('p', '', '从“准备”开始，点击“开始只读检查”。未检查的项目不代表已完成。'));
        container.append(empty);
      }
      checks.forEach((check) => {
        const item = make('article', 'check-item');
        const heading = make('div', 'check-heading');
        heading.append(make('h2', '', check.title), make('span', `status-badge ${check.done ? 'done' : 'pending'}`, check.done ? '已完成' : '未完成'));
        item.append(heading, make('p', '', check.reason));
        if (check.next) item.append(make('p', 'next-step', `下一步：${check.next}`));
        container.append(item);
      });
    });
    const done = checks.filter((check) => check.done).length;
    setText('#done-count', String(done));
    setText('#pending-count', String(checks.length - done));
    setText('#delivery-summary', imported ? '以下统计来自历史报告，不能证明当前环境已完成验证。' : checks.length ? (done === checks.length ? '已保存项目均记录为已完成。完成范围以各项检查记录为准。' : '仍有未完成项目。请按下方下一步继续，保留本轮材料。') : '尚无检查记录。先完成本地准备。');
  }

  function renderState(nextState, resetDraft = false) {
    const previousConfigName = string(config()?.name);
    state = object(nextState) || {};
    const currentConfig = config();
    const currentPlan = plan();
    const scope = object(state.scope) || {};
    if (resetDraft || !draftDirty || previousConfigName !== string(currentConfig?.name)) {
      selectedClients = strings(scope.clients);
      selectedKeep = strings(scope.keep);
      selectedNode = string(currentPlan?.node, string(state.requested_node, string(scope.node, string(state.node, selectedNode))));
      draftDirty = false;
    }
    const names = nodeNames();
    if (!names.includes(selectedNode)) selectedNode = names.length === 1 ? names[0] : '';
    const select = $('#node-select');
    select.replaceChildren();
    select.append(make('option', '', names.length ? '请选择一个具体节点' : '先选择含节点的配置文件'));
    select.firstElementChild.value = '';
    names.forEach((name) => {
      const option = make('option', '', name);
      option.value = name;
      select.append(option);
    });
    select.value = selectedNode;
    all('input[name="clients"]').forEach((input) => { input.checked = selectedClients.includes(input.value); });
    all('input[name="keep"]').forEach((input) => { input.checked = selectedKeep.includes(input.value); });
    setText('#config-name', string(currentConfig?.name, '还没有选择配置'));
    setText('#config-detail', currentConfig ? `${string(currentConfig.format, '配置文件')} · 识别到 ${names.length} 个节点` : '从代理客户端导出文本配置，再选择文件。');
    const ready = currentPlan?.ready === true;
    setText('#plan-status', ready ? '方案已就绪' : '未完成');
    $('#plan-status').className = `status-badge ${ready ? 'done' : 'pending'}`;
    setText('#plan-name', string(currentPlan?.candidate_name, hasPlan() ? '本轮候选配置' : '尚未准备方案'));
    const summary = currentPlan?.summary;
    setText('#plan-summary', typeof summary === 'string' ? summary : Array.isArray(summary) ? strings(summary).join('\n') : object(summary) ? JSON.stringify(summary, null, 2) : hasPlan() ? '请核对下方候选策略。完整差异与准备结果保存在本机材料目录。' : '先返回准备，选择配置并生成方案。');
    const activationReady = currentPlan?.activation_ready === true;
    const activationReason = strings(currentPlan?.activation_blockers).join('；') || '应用额外行为仍需核对。先复制提示词，让 Codex 继续核实本机情况。';
    $('#plan-activation').hidden = activationReady;
    setText('#activation-reason', activationReason);
    setText('#configure-activation-title', activationReady ? '请按已确认的具体方案手动导入' : '候选已准备，尚不能直接启用');
    setText('#configure-activation-reason', activationReady ? '文件准备结果不替代实际导入和网络核验。需要重启时，由你手动操作。' : activationReason);
    setText('#plan-node', string(currentPlan?.node, string(scope.node, selectedNode)) || '尚无节点记录');
    setText('#plan-keep', displayChoices('keep', strings(scope.keep)) || '未选择额外业务；既有规则仍需核对保留。');
    const updated = string(state.updated_at);
    const parsed = updated ? new Date(updated) : null;
    const dateLabel = parsed && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleString('zh-CN', { hour12: false }) : '';
    const reportSource = object(state.report_source);
    if (reportSource?.imported === true) {
      const reportDate = string(reportSource.checked_at) ? new Date(reportSource.checked_at) : null;
      const reportTime = reportDate && !Number.isNaN(reportDate.getTime()) ? reportDate.toLocaleString('zh-CN', { hour12: false }) : '报告未提供有效检查时间';
      const reportLabel = string(reportSource.label, '历史报告');
      setText('#checked-at', `${reportLabel} · 检查时间：${reportTime}`);
    } else {
      setText('#checked-at', dateLabel ? `保存时间：${dateLabel}。这是已保存的结果。` : '尚无已保存的检查时间。');
    }
    setText('#saved-state', dateLabel ? `进度保存于 ${dateLabel}` : '尚无已保存进度');
    renderChecks();
    if (!canView(view)) showView('prepare', false);
    updateControls();
  }

  function clearErrors() {
    all('[data-error-for]').forEach((element) => { element.textContent = ''; element.hidden = true; });
  }

  function showError(message) {
    const element = $(`[data-error-for="${view}"]`);
    if (element) {
      element.textContent = message;
      element.hidden = false;
      element.scrollIntoView({ block: 'nearest' });
    }
    setText('#feedback', '本次操作未完成，请查看下方提示。');
  }

  async function invoke(action) {
    if (busy || !allowedActions.has(action)) return;
    clearErrors();
    if (!window.desktop || typeof window.desktop.invoke !== 'function') {
      showError('未连接桌面应用。请从 Claude 环境检测应用打开本页。');
      return;
    }
    let payload = {};
    if (action === 'prepare' || action === 'handoff') {
      if (action === 'prepare' && (!config() || !selectedNode || !selectedClients.length)) {
        showError('请先选择配置、一个节点和至少一个客户端。');
        return;
      }
      payload = { node: selectedNode, clients: [...selectedClients], keep: [...selectedKeep] };
    }
    if (action === 'export_candidate') {
      if (!hasPlan() || plan().ready !== true || draftDirty) {
        showError('方案尚未就绪或选择已变更。请返回准备，重新生成方案。');
        return;
      }
      payload = { plan_id: plan().id };
    }
    if (action === 'choose_readback' && !canConfigure()) {
      showError('请先准备并导出本轮配置，再核对实际客户端导出的文件。');
      return;
    }
    busy = true;
    updateControls();
    $('#feedback').classList.add('busy');
    setText('#feedback', actionMessages[action]);
    try {
      const response = await window.desktop.invoke(action, payload);
      const returnedState = object(response?.state);
      if (returnedState && (Object.hasOwn(returnedState, 'stage') || Object.hasOwn(returnedState, 'config'))) {
        renderState(returnedState, response.ok === true && response.cancelled !== true && response.canceled !== true && ['choose_config', 'prepare', 'handoff'].includes(action));
      }
      if (!response || response.ok !== true) {
        const error = object(response?.error);
        throw new Error(string(response?.message, string(error?.message, string(response?.error, '操作未完成，请检查输入后重试。'))));
      }
      if (response.cancelled === true || response.canceled === true) {
        setText('#feedback', string(response.message, '已取消，当前配置未改变。'));
        return;
      }
      if (action === 'status' && view === 'prepare' && canView(state.stage)) showView(state.stage, false);
      if (action === 'prepare' && hasPlan()) showView('confirm');
      if (action === 'export_candidate' && canConfigure()) showView('configure');
      if (action === 'choose_readback' && canConfigure()) showView('verify');
      if (action === 'choose_report') showView('results');
      setText('#feedback', string(response.message, successMessages[action]));
    } catch (error) {
      showError(error instanceof Error ? error.message : '操作未完成，请重试。');
    } finally {
      busy = false;
      $('#feedback').classList.remove('busy');
      updateControls();
    }
  }

  all('[data-view]').forEach((button) => button.addEventListener('click', () => { if (!busy) showView(button.dataset.view); }));
  all('[data-action]').forEach((button) => button.addEventListener('click', () => invoke(button.dataset.action)));
  all('input').forEach((input) => input.addEventListener('change', syncDraft));
  $('#node-select').addEventListener('change', syncDraft);
  renderState({});
  invoke('status');
})();
