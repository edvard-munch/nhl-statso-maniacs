import assert from 'node:assert/strict';
import { runBrowser } from './harness.mjs';

const [scenario, target] = process.argv.slice(2);
await runBrowser(scenario, target, async ({page, idle, requests}) => {
  await page.goto(target);
  await idle();
  assert(await page.locator('#ajax-csrf-token [name="csrfmiddlewaretoken"]').inputValue());
  const favorite = page.locator('.js-fav-add').first();
  const favoriteUrl = await favorite.getAttribute('href');
  await favorite.press('Enter');
  // Icon fonts are intentionally excluded from the offline harness; use the keyboard.
  await page.locator(`.js-fav-del[href="${favoriteUrl}"]`).waitFor({state: 'attached'});
  await idle();
  await page.locator(`.js-fav-del[href="${favoriteUrl}"]`).press('Enter');
  await page.locator(`.js-fav-add[href="${favoriteUrl}"]`).waitFor({state: 'attached'});
  await idle();
  const search = new URL('/search/', target);
  search.searchParams.set('q', 'Browser Skater');
  await page.goto(search.href);
  await idle();
  const compare = page.locator('.js-compare-add').first();
  const comparisonUrl = await compare.getAttribute('href');
  await compare.click();
  await page.locator(`.js-compare-del[href="${comparisonUrl}"]`).waitFor();
  await idle();
  await page.locator(`.js-compare-del[href="${comparisonUrl}"]`).click();
  await page.locator(`.js-compare-add[href="${comparisonUrl}"]`).waitFor();
  await idle();
  assert.equal(requests.filter(url => url.pathname.endsWith('/player_favorite/')).length, 2);
  assert.equal(requests.filter(url => url.pathname.endsWith('/player_compare/')).length, 2);

  // Exercise the shared prefilter's external-URL boundary without contacting a service.
  let externalHeaders;
  await page.route('https://csrf-probe.invalid/**', async route => {
    externalHeaders = route.request().headers();
    await route.fulfill({status: 200, contentType: 'application/json', body: '{}',
                         headers: {'Access-Control-Allow-Origin': new URL(target).origin}});
  });
  await page.evaluate(() => new Promise((resolve, reject) => {
    $.ajax({url: 'https://csrf-probe.invalid/check', type: 'POST', dataType: 'json'})
      .done(resolve).fail(() => reject(new Error('CSRF boundary probe failed')));
  }));
  assert(externalHeaders);
  assert.equal(externalHeaders['x-csrftoken'], undefined);
});
