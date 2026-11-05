import assert from 'node:assert/strict';
import { runBrowser } from './harness.mjs';

const [scenario, target] = process.argv.slice(2);
await runBrowser(scenario, target, async ({page, cell, requests}) => {
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
});
