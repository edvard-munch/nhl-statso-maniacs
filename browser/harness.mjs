import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const root = resolve(import.meta.dirname, '..');

export async function runBrowser(scenario, target, check) {
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
  if (process.env.NHL_BROWSER_SESSION) {
    await context.addCookies([{name: process.env.NHL_BROWSER_COOKIE_NAME, value: process.env.NHL_BROWSER_SESSION,
                              url: origin, httpOnly: true, sameSite: 'Lax'}]);
  }
  const page = await context.newPage();
  page.setDefaultTimeout(timeout);
  const errors = [];
  const requests = [];
  const failedAjax = [];
  const injectedRequests = new Set();
  let pendingFailure = null;
  function failNextAjax(matches) {
    assert.equal(pendingFailure, null, 'Previous failure injection must be consumed');
    const rule = {matches, count: 0};
    pendingFailure = rule;
    return () => assert.equal(rule.count, 1, 'Expected exactly one injected failure');
  }
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.resourceType() === 'xhr') requests.push(new URL(request.url()));
    const url = new URL(request.url());
    const savedMutation = /\/(player_favorite|player_compare)\/$|\/reset_comparison\/[^/]+\/$/;
    if (url.origin === origin && savedMutation.test(url.pathname)) {
      if (request.method() !== 'POST') errors.push(`Saved mutation used ${request.method()}: ${url.pathname}`);
      if (!request.headers()['x-csrftoken']) errors.push(`Missing CSRF header: ${url.pathname}`);
    }
  });
  page.on('response', response => {
    if (response.request().resourceType() === 'xhr' && response.status() >= 400) {
      if (!injectedRequests.delete(response.request())) {
        failedAjax.push({url: response.url(), status: response.status()});
      }
    }
  });
  await context.route('**/*', async route => {
    const request = route.request();
    const url = request.url();
    if (assets.has(url)) return route.fulfill(assets.get(url));
    // Images/fonts are cosmetic; no API or external network access is permitted.
    if (['image', 'font'].includes(request.resourceType())) return route.fulfill({status: 204});
    if (new URL(url).origin === origin) {
      if (request.resourceType() === 'xhr' && pendingFailure?.matches(new URL(url))) {
        const rule = pendingFailure;
        pendingFailure = null;
        rule.count += 1;
        injectedRequests.add(request);
        return route.fulfill({status: 503, contentType: 'application/json',
                              body: JSON.stringify({error: 'Injected browser-test failure'})});
      }
      return route.continue();
    }
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
  async function idle() {
    await page.waitForFunction(() => window.jQuery?.active === 0);
  }
  try {
    await check({page, cell, idle, requests, target, failNextAjax});
    await idle();
    assert.equal(pendingFailure, null, 'Scheduled failure was not exercised');
    assert.equal(injectedRequests.size, 0, 'Injected response was not observed');
    assert.deepEqual(errors, [], 'Browser JavaScript errors');
    assert.deepEqual(failedAjax, [], 'Failed AJAX requests');
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
}
