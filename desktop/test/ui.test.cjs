'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const uiDirectory = path.resolve(__dirname, '..', 'ui');
const html = fs.readFileSync(path.join(uiDirectory, 'index.html'), 'utf8');
const source = fs.readFileSync(path.join(uiDirectory, 'app.js'), 'utf8');
const tick = () => new Promise((resolve) => setImmediate(resolve));

function selectedState() {
  return {
    stage: 'prepare',
    config: { name: 'example.yaml', format: 'yaml', node_names: ['节点 A', '节点 B'] },
    scope: { clients: [], keep: [] },
    checks: [],
  };
}

function preparedState() {
  return {
    ...selectedState(),
    stage: 'confirm',
    scope: { clients: ['browser'], keep: ['远控'] },
    plan: {
      id: 'test-plan',
      node: '节点 A',
      summary: { 说明: '测试用方案' },
      ready: true,
      candidate_name: 'candidate.yaml',
      activation_ready: false,
      activation_blockers: ['测试：仍需核对'],
    },
  };
}

async function setup(t, initial = {}) {
  // HTML is an in-memory string. No URL, usable resources, real preload,
  // browser, Electron window, filesystem configuration or network is loaded.
  const dom = new JSDOM(html, { runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  const calls = [];
  let handler = async () => ({ ok: true, state: initial });
  dom.window.HTMLElement.prototype.scrollIntoView = function () {};
  dom.window.desktop = {
    invoke: async (action, payload) => {
      calls.push({ action, payload });
      return handler(action, payload);
    },
  };
  vm.runInContext(source, dom.getInternalVMContext(), { filename: 'app.js' });
  await tick();
  return {
    window: dom.window,
    q: (selector) => dom.window.document.querySelector(selector),
    calls,
    setHandler(next) { handler = next; },
    async click(selector) {
      dom.window.document.querySelector(selector).click();
      await tick();
    },
  };
}

test('startup only reads saved status and keeps empty workflow steps unavailable', async (t) => {
  const ui = await setup(t);
  assert.deepEqual(ui.calls.map((call) => call.action), ['status']);
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls[0].payload)), {});
  assert.equal(ui.q('[data-action="prepare"]').disabled, true);
  assert.equal(ui.q('[data-view="configure"]').disabled, true);
  assert.equal(ui.q('#view-prepare').hidden, false);
  assert.match(ui.q('#view-results [data-checks]').textContent, /还没有检查结果/);
});

test('configuration text is inert and preparation sends selected scope while locking duplicate actions', async (t) => {
  const selected = selectedState();
  selected.config.name = '<img src=x onerror=alert(1)>';
  const ui = await setup(t, selected);
  assert.equal(ui.q('#config-name').textContent, selected.config.name);
  assert.equal(ui.q('#config-name').children.length, 0);
  ui.q('#node-select').value = '节点 A';
  ui.q('#node-select').dispatchEvent(new ui.window.Event('change'));
  await ui.click('input[value="browser"]');
  await ui.click('input[value="远控"]');
  assert.equal(ui.q('[data-action="prepare"]').disabled, false);

  let resolvePrepare;
  ui.setHandler(() => new Promise((resolve) => { resolvePrepare = resolve; }));
  ui.q('[data-action="prepare"]').click();
  const count = ui.calls.length;
  ui.q('[data-action="collect"]').click();
  assert.equal(ui.calls.length, count);
  assert.equal(ui.q('#main').getAttribute('aria-busy'), 'true');
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.at(-1))), {
    action: 'prepare',
    payload: { node: '节点 A', clients: ['browser'], keep: ['远控'] },
  });
  resolvePrepare({ ok: true, state: preparedState() });
  await tick();
  assert.equal(ui.q('#main').getAttribute('aria-busy'), 'false');
  assert.equal(ui.q('#view-confirm').hidden, false);
});

test('ready candidate can be exported but is not represented as activated', async (t) => {
  const ui = await setup(t, preparedState());
  assert.equal(ui.q('[data-action="export_candidate"]').disabled, false);
  assert.equal(ui.q('#plan-node').textContent, '节点 A');
  assert.match(ui.q('#plan-summary').textContent, /测试用方案/);
  assert.equal(ui.q('#plan-activation').hidden, false);
  assert.equal(ui.q('#activation-reason').textContent, '测试：仍需核对');
  assert.equal(ui.q('[data-view="configure"]').disabled, true);

  ui.setHandler(async () => ({ ok: true, state: { ...preparedState(), stage: 'configure' } }));
  await ui.click('[data-action="export_candidate"]');
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.at(-1))), {
    action: 'export_candidate', payload: { plan_id: 'test-plan' },
  });
  assert.equal(ui.q('#view-configure').hidden, false);
  assert.match(ui.q('#configure-activation-title').textContent, /不能直接启用/);
});

test('cancelled export stays on confirmation and a failed operation preserves saved state', async (t) => {
  const prepared = preparedState();
  const ui = await setup(t, prepared);
  ui.setHandler(async () => ({ ok: true, state: prepared, cancelled: true }));
  await ui.click('[data-action="export_candidate"]');
  assert.equal(ui.q('#view-confirm').hidden, false);
  assert.match(ui.q('#feedback').textContent, /取消/);

  ui.setHandler(async () => ({ ok: false, state: {}, error: 'ERROR_CODE', message: '具体错误说明' }));
  await ui.click('[data-action="export_candidate"]');
  assert.equal(ui.q('[data-error-for="confirm"]').textContent, '具体错误说明');
  assert.equal(ui.q('[data-error-for="confirm"]').hidden, false);
  assert.equal(ui.q('#plan-node').textContent, '节点 A');
  assert.equal(ui.q('[data-action="export_candidate"]').disabled, false);
});

test('readback matching does not mark unknown DNS validation as completed', async (t) => {
  const exported = { ...preparedState(), stage: 'configure' };
  const ui = await setup(t, exported);
  ui.setHandler(async () => ({
    ok: true,
    state: {
      ...exported,
      stage: 'verify',
      checks: [
        { title: '配置文件匹配', status: '已完成', reason: '文件比对完成' },
        { title: 'DNS 运行核验', status: '未知', next_step: '等待实际核验' },
      ],
    },
  }));
  await ui.click('#view-configure [data-action="choose_readback"]');
  assert.equal(ui.q('#view-verify').hidden, false);
  assert.equal(ui.q('#done-count').textContent, '1');
  assert.equal(ui.q('#pending-count').textContent, '1');
  assert.match(ui.q('#view-verify [data-checks]').textContent, /未完成/);
  assert.match(ui.q('#view-verify [data-checks]').textContent, /等待实际核验/);
});

test('changing selected scope disables exporting the previous plan', async (t) => {
  const ui = await setup(t, preparedState());
  await ui.click('[data-view="prepare"]');
  await ui.click('input[value="claude_gui"]');
  assert.equal(ui.q('[data-action="export_candidate"]').disabled, true);
  const count = ui.calls.length;
  await ui.click('[data-action="export_candidate"]');
  assert.equal(ui.calls.length, count);
  assert.match(ui.q('#prepare-guidance').textContent, /重新准备方案/);
});

test('handoff saves current draft and applies returned scope with invalidated plan', async (t) => {
  const ui = await setup(t, preparedState());
  await ui.click('[data-view="prepare"]');
  ui.q('#node-select').value = '节点 B';
  ui.q('#node-select').dispatchEvent(new ui.window.Event('change'));
  await ui.click('input[value="claude_gui"]');
  await ui.click('input[value="会议"]');
  const saved = {
    ...selectedState(),
    plan: null,
    requested_node: '节点 B',
    scope: { clients: ['browser', 'claude_gui'], keep: ['会议', '远控'] },
  };
  ui.setHandler(async () => ({ ok: true, state: saved }));
  await ui.click('[data-view="confirm"]');
  await ui.click('#view-confirm [data-action="handoff"]');
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.at(-1))), {
    action: 'handoff',
    payload: { node: '节点 B', clients: ['browser', 'claude_gui'], keep: ['会议', '远控'] },
  });
  assert.equal(ui.q('#view-prepare').hidden, false);
  assert.equal(ui.q('#node-select').value, '节点 B');
  assert.equal(ui.q('input[value="claude_gui"]').checked, true);
  assert.equal(ui.q('input[value="会议"]').checked, true);
  assert.equal(ui.q('[data-action="export_candidate"]').disabled, true);
  assert.equal(ui.q('[data-view="confirm"]').disabled, true);

  const reopened = await setup(t, saved);
  assert.equal(reopened.q('#node-select').value, '节点 B');
  const unknown = await setup(t, { ...saved, requested_node: '不在配置中的节点' });
  assert.equal(unknown.q('#node-select').value, '');
  assert.equal(unknown.q('[data-action="prepare"]').disabled, true);
});

test('importing a completed historical report does not unlock export or advance workflow', async (t) => {
  const prepared = preparedState();
  prepared.plan.ready = false;
  const ui = await setup(t, prepared);
  const historical = {
    ...prepared,
    report_source: { label: '已保存报告.json', checked_at: '2026-10-27T09:30:00Z', imported: true },
    checks: [{ title: '历史文件核对', status: '已完成', reason: '历史报告记录' }],
  };
  await ui.click('[data-view="results"]');
  ui.setHandler(async () => ({ ok: true, state: historical }));
  await ui.click('[data-action="choose_report"]');
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.at(-1))), { action: 'choose_report', payload: {} });
  assert.deepEqual(ui.calls.map((call) => call.action), ['status', 'choose_report']);
  assert.equal(ui.q('#view-results').hidden, false);
  assert.match(ui.q('#view-results [data-checks]').textContent, /导入的历史报告，仅供参考；不是当前环境实测/);
  assert.match(ui.q('#checked-at').textContent, /已保存报告\.json.*检查时间：.*2026/);
  assert.equal(ui.q('#done-count').textContent, '1');
  assert.equal(ui.q('[data-action="export_candidate"]').disabled, true);
  assert.equal(ui.q('[data-view="configure"]').disabled, true);
  assert.equal(ui.q('[data-view="deliver"]').disabled, true);
  assert.match(ui.q('#delivery-summary').textContent, /不能证明当前环境/);
});

test('missing plan cannot enter configured workflow and nonboolean readiness stays incomplete', async (t) => {
  const invalid = await setup(t, { stage: 'deliver', plan: null });
  assert.equal(invalid.q('#view-prepare').hidden, false);
  assert.equal(invalid.q('[data-view="configure"]').disabled, true);

  const missing = await setup(t, {
    stage: 'confirm', config: null,
    plan: { id: 'x', ready: 'true' },
    checks: [null, {}, 'bad'],
  });
  assert.equal(missing.q('[data-action="export_candidate"]').disabled, true);
  assert.equal(missing.q('#pending-count').textContent, '1');
  assert.equal(missing.q('#plan-activation').hidden, false);
});

test('local document has unique references and renderer has no active HTML or network sinks', async (t) => {
  const ui = await setup(t);
  const elements = [...ui.window.document.querySelectorAll('[id]')];
  const ids = elements.map((element) => element.id);
  assert.equal(ids.length, new Set(ids).size);
  for (const element of ui.window.document.querySelectorAll('[aria-labelledby]')) {
    for (const id of element.getAttribute('aria-labelledby').split(/\s+/)) {
      assert(ui.window.document.getElementById(id), `Missing accessible label ${id}`);
    }
  }
  const policy = ui.q('meta[http-equiv="Content-Security-Policy"]').content;
  assert.match(policy, /default-src 'none'/);
  assert.match(policy, /connect-src 'none'/);
  assert.doesNotMatch(source, /innerHTML|outerHTML|eval\(|fetch\(|XMLHttpRequest/);
});
