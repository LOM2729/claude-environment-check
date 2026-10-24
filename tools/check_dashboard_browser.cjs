// Dev-only local HTML QA with an existing sandboxed Chrome and a fresh profile.
// Requires an existing Playwright installation; never installs a browser.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

async function main() {
  const [input, output, executable] = process.argv.slice(2);
  assert(input && output && executable, 'Usage: node check_dashboard_browser.cjs INPUT.html NEW_OUTPUT_DIR CHROME');
  const url = pathToFileURL(path.resolve(input)).href;
  assert(!fs.existsSync(output), 'Output must be new');
  fs.mkdirSync(output, { mode: 0o700 });
  const browser = await chromium.launch({ executablePath: executable, headless: true, chromiumSandbox: true,
    args: ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run'] });
  const records = [];
  try {
    for (const [name, width, height] of [['desktop', 1440, 1000], ['narrow', 390, 1100]]) {
      const context = await browser.newContext({ viewport: { width, height }, offline: true });
      await context.route('**/*', route => route.request().url() === url ? route.continue() : route.abort());
      const page = await context.newPage();
      const requests = [];
      page.on('request', request => requests.push(request.url()));
      await page.goto(url, { waitUntil: 'load' });
      assert.equal(await page.locator('details[open]').count(), 0);
      const statuses = await page.locator('.status').allTextContents();
      assert(statuses.every(value => value === '已完成' || value === '未完成'));
      assert((await page.locator('body').innerText()).includes('合成示例'));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(output, name + '.png'), fullPage: true });
      // Native keyboard behavior, not a programmatic open-attribute mutation.
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => document.activeElement.tagName), 'SUMMARY');
      const focusOutline = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
      assert.notEqual(focusOutline, 'none');
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('details[open]').count(), 1);
      await page.keyboard.press('Space');
      assert.equal(await page.locator('details[open]').count(), 0);
      for (const summary of await page.locator('details > summary').all()) {
        if (await summary.isVisible()) {
          await summary.focus();
          await page.keyboard.press('Enter');
        }
      }
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert(requests.every(request => request === url), 'Unexpected page resource request');
      await page.screenshot({ path: path.join(output, name + '-expanded.png'), fullPage: true });
      records.push({ name, width, height, keyboard: true, no_horizontal_overflow: true,
                     page_requests: requests.length, external_page_requests: 0 });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({
      scope: 'synthetic local HTML only; no real network or client verification',
      browser: browser.version(), cases: records
    }, null, 2));
    console.log(JSON.stringify(records));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
