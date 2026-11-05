import assert from 'node:assert/strict';
import { runBrowser } from './harness.mjs';

const [scenario, target] = process.argv.slice(2);
await runBrowser(scenario, target, async ({page, cell, idle, requests}) => {
  const kind = scenario.endsWith('skater') ? 'skaters' : 'goalies';
  const opposite = kind === 'skaters' ? 'goalies' : 'skaters';
  const final = scenario.startsWith('final-');
  await page.goto(`${target}?season=20252026`);
  await idle();
  if (kind === 'goalies' && !final) {
    await page.locator('#js_goalies_switch').click();
    await idle();
  }
  await page.locator(`#js_switch_to_${kind}_season_tot`).click();
  await cell(`js_${kind}_total_table`, 14, kind === 'skaters' ? '20' : '—');
  await idle();
  // Icons are cosmetic in this offline harness; Enter exercises the actual link.
  await page.locator(`#js_${kind}_total_table .js-fav-del`).press('Enter');
  await idle();
  if (final) {
    await page.getByRole('heading', {name: 'You have no favorite players yet!'}).waitFor();
    assert.equal(await page.locator('.comparison-button:visible').count(), 0);
    assert.equal(await page.locator('#js_skaters_block:visible, #js_goalies_block:visible').count(), 0);
    assert.equal(await page.getByRole('link', {name: 'Browse for some great players here'}).getAttribute('href'), '/players/');
  } else {
    await page.locator(`#js_${opposite}_block`).waitFor({state: 'visible'});
    assert.equal(await page.locator(`#js_${kind}_switch`).isVisible(), false);
    assert.equal(await page.locator(`#js_${kind}_block`).isVisible(), false);
    assert.match(await page.locator(`#js_${opposite}_switch`).innerText(), /\(1\)/);
    await page.locator(`#js_switch_to_${opposite}_season_tot`).click();
    await cell(`js_${opposite}_total_table`, 14, opposite === 'skaters' ? '20' : '—');
  }
  await idle();
  assert.equal(await page.locator('#saved-players-season').inputValue(), '20252026');
  assert.equal(new URL(page.url()).searchParams.get('season'), '20252026');
  const mutations = requests.filter(url => url.pathname.includes('/player_favorite'));
  assert(mutations.length > 0);
  assert(mutations.every(url => url.searchParams.get('season') === '20252026'));
  // A fresh render must retain the same state, not resurrect a deleted favorite.
  await page.reload();
  await idle();
  if (final) await page.getByRole('heading', {name: 'You have no favorite players yet!'}).waitFor();
  else assert.equal(await page.locator(`#js_${kind}_switch`).count(), 0);
});
