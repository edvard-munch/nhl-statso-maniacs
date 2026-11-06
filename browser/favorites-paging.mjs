import assert from 'node:assert/strict';
import { runBrowser } from './harness.mjs';

const [scenario, target] = process.argv.slice(2);
await runBrowser(scenario, target, async ({page, idle, cell, requests}) => {
  const kind = scenario.endsWith('skater') ? 'skaters' : 'goalies';
  const label = kind === 'skaters' ? 'Skater' : 'Goalie';
  const tableId = `js_${kind}_total_table`;
  const table = page.locator(`#${tableId}`);
  const filter = page.locator(`.js_external_filter_${kind}_totals`);
  const prefix = `Saved ${label}`;
  const removedName = `${prefix} 25`;
  const pager = page.locator(kind === 'skaters' ? '.pager-skt-tot' : '.pager-gls-tot');
  async function rows(count) {
    await page.waitForFunction(({tableId, count}) =>
      document.querySelectorAll(`#${tableId} tbody tr`).length === count, {tableId, count});
    await idle();
  }
  async function applyFilter(value, count) {
    // Filtering is debounced; unchanged row counts do not prove the request ran.
    const response = page.waitForResponse(response =>
      response.request().resourceType() === 'xhr'
      && new URL(response.url()).pathname.startsWith('/ajax_players/'));
    await filter.fill(value);
    await response;
    await rows(count);
  }
  async function open() {
    await page.goto(`${target}?season=20262027`);
    await idle();
    if (kind === 'goalies') await page.locator('#js_goalies_switch').click();
    await page.locator(`#js_switch_to_${kind}_season_tot`).click();
    await rows(25);
    await cell(tableId, 14, '2'); // Season data, not the conflicting snapshot 999.
    const nameHeader = table.locator('thead tr').first().locator('th').nth(2);
    await nameHeader.click();
    await page.waitForFunction(tableId =>
      document.getElementById(tableId).config.sortList[0]?.[0] === 2, tableId);
    await idle();
    if (await table.evaluate(el => el.config.sortList[0][1]) === 1) {
      await nameHeader.click();
    }
    await page.waitForFunction(tableId =>
      document.querySelector(`#${tableId} tbody tr td:nth-child(3)`)?.textContent.trim()
        === `Saved ${tableId.includes('skaters') ? 'Skater' : 'Goalie'} 00`, tableId);
    await idle();
  }
  await open();
  await applyFilter(scenario.startsWith('filtered') ? removedName : prefix,
                    scenario.startsWith('filtered') ? 1 : 25);
  if (scenario.startsWith('paged')) {
    await pager.locator('button.next').click();
    await rows(1);
  }
  assert.match(await table.locator('tbody').innerText(), new RegExp(removedName));
  const requestStart = requests.length;
  await table.locator('.js-fav-del').press('Enter');
  await page.locator('#favorites-update-message').waitFor({state: 'visible'});
  await rows(scenario.startsWith('filtered') ? 0 : 25);
  assert.equal(await filter.inputValue(), scenario.startsWith('filtered') ? removedName : prefix);
  assert.match(await page.locator(`#js_${kind}_switch`).innerText(), /\(25\)/);
  assert.equal(await page.locator(`#js_${kind}_block`).isVisible(), true);
  assert.equal(await page.locator('#favorites-empty-state').isVisible(), false);
  assert.equal(await page.locator('#saved-players-season').inputValue(), '20262027');
  assert.deepEqual(await table.evaluate(el => el.config.sortList), [[2, 0]]);
  assert.equal(await table.evaluate(el => el.config.pager.page), 0);
  if (scenario.startsWith('filtered')) {
    assert.match(await page.locator(`#${tableId}-status`).innerText(), /No saved players match these filters/);
    assert.equal(await page.locator(`#${tableId}-status`).isVisible(), true);
    await applyFilter('', 25);
    assert.equal(await page.locator(`#${tableId}-status`).isVisible(), false);
  }
  assert.equal(await pager.isVisible(), false);
  assert.equal((await table.locator('tbody tr').first().locator('td').nth(2).innerText()).trim(), `${prefix} 00`);
  assert.equal(await table.locator('tbody tr').filter({hasText: removedName}).count(), 0);
  const updates = requests.slice(requestStart).filter(url => url.pathname.startsWith('/ajax_players/'));
  assert(updates.some(url => url.pathname.includes('/page=1/')));
  assert(updates.every(url => url.searchParams.get('season') === '20262027'));
  // A fresh render confirms deletion persists; browser-local filters are reapplied explicitly.
  await open();
  assert.match(await page.locator(`#js_${kind}_switch`).innerText(), /\(25\)/);
  await applyFilter(removedName, 0);
  assert.equal(await page.locator('#favorites-empty-state').isVisible(), false);
  const mutations = requests.filter(url => url.pathname.endsWith('/player_favorite/'));
  assert.equal(mutations.length, 1);
  assert.equal(mutations[0].searchParams.get('season'), '20262027');
});
