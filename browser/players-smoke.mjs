import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const [scenario, target] = process.argv.slice(2);
const root = resolve(import.meta.dirname, '..');
const origin = new URL(target).origin;
const manifest = JSON.parse(readFileSync(resolve(root, 'browser/assets.json'), 'utf8'));
const assets = new Map(manifest.map(asset => {
  const body = readFileSync(resolve(root, '.browser-cache/assets', asset.file));
  assert.equal(createHash('sha256').update(body).digest('hex'), asset.sha256, asset.url);
  return [asset.url, {body, contentType: asset.file.endsWith('.css') ? 'text/css' : 'application/javascript'}];
}));
const timeout = 15000;
const browser = await chromium.launch({headless: true, channel: 'chromium'});
const context = await browser.newContext({serviceWorkers: 'block'});
const page = await context.newPage();
page.setDefaultTimeout(timeout);
const errors = [];
const requests = [];
const failedAjax = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (new URL(request.url()).pathname.startsWith('/ajax_players/')) requests.push(new URL(request.url()));
});
page.on('response', response => {
  if (new URL(response.url()).pathname.startsWith('/ajax_players/') && !response.ok()) failedAjax.push(response.status());
});
await context.route('**/*', async route => {
  const request = route.request();
  const url = request.url();
  if (assets.has(url)) return route.fulfill(assets.get(url));
  // Images/fonts are cosmetic; no API or external network access is permitted.
  if (['image', 'font'].includes(request.resourceType())) return route.fulfill({status: 204});
  if (new URL(url).origin === origin) return route.continue();
  if (request.resourceType() === 'stylesheet') return route.fulfill({status: 200, contentType: 'text/css', body: ''});
  errors.push(`Unexpected external browser request: ${url}`);
  return route.abort();
});
await context.tracing.start({screenshots: true, snapshots: true});
async function cell(table, column, expected) {
  const selector = `#${table} tbody tr:first-child td:nth-child(${column})`;
  await page.waitForFunction(({selector, expected}) => document.querySelector(selector)?.textContent.trim() === expected,
                            {selector, expected});
}
try {
  await page.goto(`${target}?season=20262027`);
  await cell('skaters_table', 14, '2');
  await page.waitForFunction(() => window.jQuery?.active === 0);
  assert.match(await page.locator('#skaters_table tbody').innerText(), /Browser Skater/);
  if (scenario === 'season') {
    await page.locator('#players-season').selectOption('20252026');
    await page.getByRole('button', {name: 'Show season'}).click();
    await cell('skaters_table', 14, '20');
    assert.equal(new URL(page.url()).searchParams.get('season'), '20252026');
    assert(requests.some(url => url.searchParams.get('season') === '20252026'));
  } else if (scenario === 'modes') {
    await page.locator('#js_avg_stats').click();
    await cell('skaters_table', 14, '0.2');
    await page.locator('#js_total_stats').click();
    await cell('skaters_table', 14, '2');
    await page.locator('#js_gls_stats').click();
    await page.locator('#goalies_table').waitFor({state: 'visible'});
    await cell('goalies_table', 14, '2');
    assert(requests.some(url => url.pathname.includes('/avg/')));
    assert(requests.some(url => url.pathname.includes('/gls/')));
    assert(requests.every(url => url.searchParams.get('season') === '20262027'));
  } else if (scenario === 'empty') {
    await page.goto(`${target}?season=20272028`);
    await page.locator('#skaters-empty').waitFor({state: 'visible'});
    assert.match(await page.locator('#skaters-empty').innerText(), /2027-28/);
    assert.equal(await page.locator('#skaters_table tbody tr').count(), 0);
    await page.locator('#js_gls_stats').click();
    await page.locator('#goalies-empty').waitFor({state: 'visible'});
    assert.equal(await page.locator('#goalies_table tbody tr').count(), 0);
  } else throw new Error(`Unknown scenario ${scenario}`);
  await page.waitForFunction(() => window.jQuery?.active === 0);
  assert.deepEqual(errors, [], 'Browser JavaScript errors');
  assert.deepEqual(failedAjax, [], 'Failed Players AJAX requests');
  await context.tracing.stop();
} catch (error) {
  const artifacts = resolve(root, 'browser-artifacts');
  mkdirSync(artifacts, {recursive: true});
  await page.screenshot({path: resolve(artifacts, `${scenario}.png`), fullPage: true});
  await context.tracing.stop({path: resolve(artifacts, `${scenario}.zip`)});
  throw error;
} finally {
  await browser.close();
}
