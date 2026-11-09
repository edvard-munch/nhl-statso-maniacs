import assert from 'node:assert/strict';
import { runBrowser } from './harness.mjs';

const [, , scenario, target] = process.argv;
await runBrowser(scenario, target, async ({page, idle, cell, requests, failNextAjax}) => {
  await page.clock.install();
  await page.goto(target);
  await idle();
  const endpoint = await page.locator('#game-refresh').getAttribute('data-url');
  const polls = () => requests.filter(url => url.pathname === endpoint).length;
  const saved = await page.locator('#game-freshness').textContent();
  if (scenario === 'refresh-favorite-race') {
    let release;
    let captured;
    const ready = new Promise(resolve => { captured = resolve; });
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**' + endpoint + '*', async route => {
      const response = await route.fetch();
      const data = await response.json();
      captured();
      await gate;
      await route.fulfill({response, json: data});
    }, {times: 1});
    await page.locator('#refresh-now').click();
    await ready;
    await page.locator('#away_fwds .js-fav-del').press('Enter');
    await page.waitForFunction(() => window.jQuery.active === 1);
    await page.clock.runFor(1000);
    await page.locator('#away_fwds .js-fav-add').waitFor({state: 'attached'});
    release();
    await idle();
    assert.equal(await page.locator('#away_fwds .js-fav-add').count(), 1);
    assert.match(await page.locator('#refresh-status').textContent(), /selection changed/);
    await page.locator('#refresh-now').click();
    await idle();
    assert.equal(await page.locator('#away_fwds .js-fav-add').count(), 1);
    return;
  }
  if (scenario === 'refresh-recovery') {
    const original = await page.locator('#away_fwds tbody').innerHTML();
    const consumed = failNextAjax(url => url.pathname === endpoint);
    await page.locator('#refresh-now').click();
    await page.waitForFunction(() => document.querySelector('#refresh-status').textContent.includes('Refresh failed'));
    consumed();
    assert.equal(await page.locator('#away_fwds tbody').innerHTML(), original);
    assert.equal(await page.locator('#game-freshness').textContent(), saved);
    await page.locator('#refresh-now').click();
    await page.waitForFunction(() => document.querySelector('#refresh-status').textContent.includes('Last checked'));
    await idle();
    assert.equal(await page.locator('#game-freshness').textContent(), saved);
    await page.locator('#auto-refresh').uncheck();
    const count = polls();
    await page.clock.fastForward(600000);
    await idle();
    assert.equal(polls(), count, 'Paused pages must not poll');
    await page.locator('#refresh-now').click();
    await idle();
    assert.equal(polls(), count + 1, 'Manual refresh works while paused');
    await page.locator('#auto-refresh').check();
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', {configurable: true, value: true});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const hiddenCount = polls();
    await page.clock.fastForward(600000);
    assert.equal(polls(), hiddenCount, 'Hidden tabs must not poll');
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', {configurable: true, value: false});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await idle();
    assert.equal(polls(), hiddenCount + 1, 'Visible tabs check saved data again');
    return;
  }
  await page.route('**' + endpoint + '*', async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (scenario === 'game-refresh') {
      data.result = 'Updated saved result';
      data.tables.away_fwds = await page.evaluate(html => {
        const body = document.createElement('tbody');
        body.innerHTML = html;
        body.querySelector('tr td:nth-child(6)').textContent = '7';
        return body.innerHTML;
      }, data.tables.away_fwds);
    } else {
      data.games = data.games.replace(/(<a[^>]+>)[^<]+/, '$1Updated scoreboard result');
      data.games += '<p data-game-id="999"><a href="#new-game">New saved game</a></p>';
    }
    await route.fulfill({response, json: data});
  });
  if (scenario === 'game-refresh') {
    await page.locator('#away_fwds th').nth(5).click();
    const sort = await page.evaluate(() => JSON.stringify(document.getElementById('away_fwds').config.sortList));
    await page.locator('#away_fwds tbody a.name').focus();
    const href = await page.locator('#away_fwds tbody a.name').getAttribute('href');
    await page.clock.fastForward(60000);
    await cell('away_fwds', 6, '7');
    await idle();
    assert.equal(await page.locator('#game-result').textContent(), 'Updated saved result');
    assert.equal(await page.evaluate(() => JSON.stringify(document.getElementById('away_fwds').config.sortList)), sort);
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute('href')), href);
  } else {
    const selected = await page.locator('.curr-day').getAttribute('href');
    await page.clock.fastForward(60000);
    await page.waitForFunction(() => document.querySelector('#scoreboard-games').textContent.includes('New saved game'));
    await idle();
    assert.equal(await page.locator('.curr-day').getAttribute('href'), selected);
    assert.equal(page.url(), target, 'Polling never changes selected day');
    assert.match(await page.locator('#scoreboard-games').textContent(), /Updated scoreboard result/);
  }
  assert.equal(polls(), 1);
});
