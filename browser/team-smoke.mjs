import assert from 'node:assert/strict';
import { runBrowser } from './harness.mjs';

const [scenario, target] = process.argv.slice(2);
await runBrowser(scenario, target, async ({page, idle, requests}) => {
  const defence = page.locator('#js_defencemen_sect');
  const forwards = page.locator('#js_forwards_sect');
  async function value(table, name, column, expected) {
    await page.waitForFunction(({table, name, column, expected}) => {
      const row = [...document.querySelectorAll(`#${table} tbody tr`)]
        .find(row => row.querySelector('td:nth-child(4)')?.textContent.trim() === name);
      return row?.querySelector(`td:nth-child(${column})`)?.textContent.trim() === expected;
    }, {table, name, column, expected});
  }
  async function click(locator) {
    await locator.click();
    await idle();
    assert.equal(await page.locator('#team-stats-error').isVisible(), false);
  }
  await page.goto(`${target}?season=${scenario === 'team-empty' ? '20272028' : '20262027'}`);
  await idle();
  if (scenario === 'team-layout') {
    await value('tab2', 'Season Defender', 13, '2');
    await value('tab3', 'Traded Forward', 12, '6');
    await value('tab3', 'Traded Forward', 13, '3'); // BUF split, not combined 4 or stale 999.
    await value('tab1', 'Traded Goalie', 13, '2');
    await value('tab1', 'Traded Goalie', 18, '90');
    await click(defence.locator('[data-team-stats]'));
    await value('tab2', 'Season Defender', 13, '0.2');
    await value('tab3', 'Traded Forward', 13, '3'); // The other split is independent.
    await click(forwards.locator('[data-team-stats]'));
    await value('tab3', 'Traded Forward', 13, '0.5');
    await click(defence.locator('[data-team-layout]'));
    assert.equal(await defence.getAttribute('data-position'), 't');
    assert.equal(await forwards.isVisible(), false);
    assert.equal(await page.locator('#tab2 tbody tr').count(), 3);
    await value('tab2', 'Season Defender', 13, '0.2');
    await value('tab2', 'Traded Forward', 13, '0.5');
    await click(defence.locator('[data-team-stats]'));
    await value('tab2', 'Traded Forward', 13, '3');
    await click(defence.locator('[data-team-layout]'));
    assert.equal(await defence.getAttribute('data-position'), 'd');
    assert.equal(await forwards.isVisible(), true);
    assert.equal(await forwards.getAttribute('data-mode'), 'tot');
    assert.equal(await page.locator('#tab2 tbody tr').count(), 1);
    assert.equal(await page.locator('#tab3 tbody tr').count(), 2);
    await value('tab2', 'Season Defender', 13, '2');
    await value('tab3', 'Traded Forward', 13, '3');
    assert(requests.some(url => url.pathname.includes('/avg/t/')));
    assert(requests.some(url => url.pathname.includes('/tot/t/')));
    assert(requests.some(url => url.pathname.includes('/tot/d/')));
    assert(requests.some(url => url.pathname.includes('/tot/f/')));
  } else if (scenario === 'team-season') {
    await page.locator('#team-season').selectOption('20252026');
    await page.getByRole('button', {name: 'Show season'}).click();
    await page.waitForURL(url => url.searchParams.get('season') === '20252026');
    await idle();
    await value('tab2', 'Season Defender', 13, '20');
    await click(defence.locator('[data-team-stats]'));
    await value('tab2', 'Season Defender', 13, '0.25');
    await click(defence.locator('[data-team-layout]'));
    await value('tab2', 'Season Defender', 13, '0.25');
    await value('tab2', 'Historical Only', 13, '0.25');
    await click(defence.locator('[data-team-layout]'));
    assert.equal(await forwards.isVisible(), true);
    await value('tab2', 'Season Defender', 13, '0.25');
    assert.equal(await page.locator('#tab3 tbody tr').count(), 0);
    assert.equal(await forwards.locator('[data-team-empty]').isVisible(), true);
    assert(requests.length >= 4);
  } else if (scenario === 'team-empty') {
    assert.equal(await page.locator('#team-season').inputValue(), '20272028');
    for (const table of ['tab1', 'tab2', 'tab3']) assert.equal(await page.locator(`#${table} tbody tr`).count(), 0);
    await click(defence.locator('[data-team-stats]'));
    await click(forwards.locator('[data-team-stats]'));
    await click(defence.locator('[data-team-layout]'));
    assert.equal(await forwards.isVisible(), false);
    assert.equal(await defence.locator('[data-team-empty]').isVisible(), true);
    assert.match(await defence.locator('[data-team-empty]').innerText(), /2027-28/);
    await click(defence.locator('[data-team-layout]'));
    assert.equal(await forwards.isVisible(), true);
    for (const table of ['tab1', 'tab2', 'tab3']) assert.equal(await page.locator(`#${table} tbody tr`).count(), 0);
  } else throw new Error(`Unknown scenario ${scenario}`);
  const season = scenario === 'team-layout' ? '20262027' : scenario === 'team-season' ? '20252026' : '20272028';
  assert(requests.length > 0);
  assert(requests.every(url => url.pathname.startsWith('/ajax_stats_switcher/') && url.searchParams.get('season') === season));
});
