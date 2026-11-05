import assert from 'node:assert/strict';
import { runBrowser } from './harness.mjs';

const [scenario, target] = process.argv.slice(2);
await runBrowser(scenario, target, async ({page, cell, idle, requests}) => {
  await page.goto(`${target}?season=20262027`);
  await idle();
  async function submitSeason(season) {
    await page.locator('#saved-players-season').selectOption(season);
    await page.getByRole('button', {name: 'Show season'}).click();
    await page.waitForURL(url => url.searchParams.get('season') === season);
    await idle();
  }
  async function metric(table, label, value) {
    const selector = `#${table} tbody tr`;
    await page.waitForFunction(({selector, label, value}) => {
      const row = [...document.querySelectorAll(selector)].find(row => row.querySelector('th')?.textContent.trim() === label);
      return row?.querySelector('td')?.textContent.trim() === value;
    }, {selector, label, value});
  }
  if (scenario === 'favorites-empty') {
    await page.getByRole('heading', {name: 'You have no favorite players yet!'}).waitFor();
    assert.equal(await page.locator('.comparison-button').count(), 0);
    assert.equal(await page.locator('#js_skaters_total_table, #js_goalies_total_table').count(), 0);
    assert.equal(await page.getByRole('link', {name: 'Browse for some great players here'}).getAttribute('href'), '/players/');
  } else if (scenario === 'favorites-goalie') {
    await page.locator('#js_goalies_block').waitFor({state: 'visible'});
    assert.equal(await page.locator('#js_skaters_switch').count(), 0);
    await page.locator('#js_switch_to_goalies_season_tot').click();
    await cell('js_goalies_total_table', 14, '2');
    assert.match(await page.locator('#js_goalies_total_table tbody').innerText(), /Browser Goalie/);
    await submitSeason('20252026');
    await page.locator('#js_switch_to_goalies_season_tot').click();
    await cell('js_goalies_total_table', 14, '—');
    assert.match(await page.locator('#js_goalies_total_table tbody').innerText(), /No statistics for 2025-26/);
  } else if (scenario === 'favorites-modes') {
    await page.locator('#js_switch_to_skaters_season_tot').click();
    await cell('js_skaters_total_table', 14, '2');
    await idle();
    await page.locator('#js_switch_to_skaters_season_avg').click();
    await cell('js_skaters_total_table', 14, '0.2');
    await submitSeason('20252026');
    await page.locator('#js_switch_to_skaters_season_tot').click();
    await cell('js_skaters_total_table', 14, '20');
    await idle();
    await page.locator('#js_switch_to_skaters_season_avg').click();
    await cell('js_skaters_total_table', 14, '0.25');
  } else if (scenario === 'comparison') {
    await metric('skaters_table', 'Goals', '2');
    await page.locator('[data-player-type="skaters"][data-comparison-mode="season_avg"]').click();
    await metric('skaters_table', 'Goals', '0.20');
    await idle();
    await page.locator('[data-player-type="skaters"][data-comparison-mode="career_tot"]').click();
    await metric('skaters_table', 'Goals', '22');
    await submitSeason('20252026');
    assert.equal(await page.locator('#comparison-content').getAttribute('data-skater-mode'), 'career_tot');
    await metric('skaters_table', 'Goals', '22');
    await page.locator('[data-player-type="skaters"][data-comparison-mode="season_avg"]').click();
    await metric('skaters_table', 'Goals', '0.25');
    await idle();
    await page.locator('#js_goalies_switch').click();
    await page.locator('[data-player-type="goalies"][data-comparison-mode="career_tot"]').click();
    await metric('goalies_table', 'W', '20');
    await idle();
    await page.locator('#goalies_table [data-comparison-remove]').click();
    await page.waitForFunction(() => document.querySelector('#comparison-content').dataset.goaliesCount === '0');
    await page.locator('#skaters_table').waitFor({state: 'visible'});
    await metric('skaters_table', 'Goals', '0.25');
    await idle();
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#js_skaters_block [data-comparison-reset]').click();
    await page.locator('#comparison-empty').waitFor({state: 'visible'});
    assert.equal(await page.locator('#comparison-content').getAttribute('data-skaters-count'), '0');
    assert.equal(await page.locator('#comparison-content').getAttribute('data-goalies-count'), '0');
  } else throw new Error(`Unknown scenario ${scenario}`);
  await idle();
  const seasonRequests = requests.filter(url => !url.pathname.startsWith('/ajax_fav_players_gamelog/'));
  assert(seasonRequests.every(url => ['20262027', '20252026'].includes(url.searchParams.get('season'))), 'Saved-list AJAX must retain selected season');
  if (scenario !== 'favorites-empty') assert(requests.some(url => url.searchParams.get('season') === '20252026'));
});
