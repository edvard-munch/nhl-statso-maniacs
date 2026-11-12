import { createMemoryHistory } from 'vue-router';
import { createAppRouter } from '../../src/router.js';
import { profileReturn, gamelogReturn } from '../../src/players/gamelog.js';
import { expect, it } from 'vitest';
import type { LocationQuery } from 'vue-router';
import { parseGamelogQuery, gameStatisticLabel } from '../../src/players/gamelog.js';
import { goalieGameStats, skaterGameStats } from '../fixtures/gamelog.js';
it('omits season by default: all saved dates rather than the latest profile season', () => {
  expect(parseGamelogQuery({}, 'skater')).toEqual({ page: 1, page_size: 50 });
});
it('keeps zero, signed bounds, boolean missing filters and explicit season/date/order selections', () => {
  expect(
    parseGamelogQuery(
      {
        season_id: '20262027',
        date_min: '2026-10-01',
        date_max: '2026-11-12',
        team: 'TOR,BUF',
        opponent: 'MTL',
        pp_toi_seconds_min: '0',
        plus_minus_min: '-1',
        hits_isnull: 'false',
        ordering: '-date,game_id',
        page: '2',
        page_size: '25',
        returnTo: '/players/skater/8480001',
      },
      'skater',
    ),
  ).toEqual({
    season_id: '20262027',
    date_min: '2026-10-01',
    date_max: '2026-11-12',
    team: 'TOR,BUF',
    opponent: 'MTL',
    pp_toi_seconds_min: 0,
    plus_minus_min: -1,
    hits_isnull: false,
    ordering: '-date,game_id',
    page: 2,
    page_size: 25,
  });
});
it.each<LocationQuery>([
  { season_id: '2026-27' },
  { season_id: '20262028' },
  { date_min: '2026-02-30' },
  { date_min: '2026-11-12', date_max: '2026-11-10' },
  { page: '0' },
  { page_size: '101' },
  { ordering: 'date,-date' },
  { ordering: '-goals_against' },
  { team: 'TOR,TOR' },
  { opponent: 'MTL,' },
  { goals_min: 'Infinity' },
  { pp_toi_seconds_min: '2', pp_toi_seconds_max: '1' },
  { hits_isnull: 'yes' },
  { mode: 'averages' },
  { date_min: ['2026-11-12'] },
  { search: 'Name' },
])('rejects invalid or inappropriate gamelog query state %j', (query) => {
  expect(() => parseGamelogQuery(query, 'skater')).toThrow();
});
it('keeps goalie decision for ordering only and rejects skater statistics', () => {
  expect(
    parseGamelogQuery(
      { ordering: '-decision,save_percentage', save_percentage_min: '0.9' },
      'goalie',
    ),
  ).toMatchObject({ ordering: '-decision,save_percentage', save_percentage_min: 0.9 });
  expect(() => parseGamelogQuery({ goals_min: '1' }, 'goalie')).toThrow();
  expect(() => parseGamelogQuery({ decision_min: '1' }, 'goalie')).toThrow();
});
it('formats actual game durations, genuine zeros and unknowns without season arithmetic', () => {
  const stats = skaterGameStats();
  expect(gameStatisticLabel(stats, 'toi_seconds')).toBe('12:34');
  expect(gameStatisticLabel(stats, 'pp_toi_seconds')).toBe('00:00');
  expect(gameStatisticLabel(stats, 'sh_toi_seconds')).toBe('01:35');
  expect(gameStatisticLabel(stats, 'goals')).toBe('0');
  expect(gameStatisticLabel(stats, 'hits')).toBe('—');
  expect(gameStatisticLabel(goalieGameStats(), 'save_percentage')).toBe('90.6%');
  expect(gameStatisticLabel(goalieGameStats(), 'decision')).toBe('L');
});

it('validates typed profile and gamelog return context without accepting external or unrelated destinations', () => {
  const router = createAppRouter(createMemoryHistory());
  const path = { player_type: 'skater' as const, nhl_id: 8480001 };
  const profile = '/players/skater/8480001?season_id=20262027&mode=averages&history_page=2';
  expect(profileReturn(profile, router, path)).toBe(profile);
  for (const value of [
    'https://evil.example/',
    '//evil.example/',
    '/players/goalie/8480001',
    '/players/skater/8480002',
    '/players/skater/8480001?unknown=1',
  ])
    expect(profileReturn(value, router, path)).toBe('/players/skater/8480001');
  const log = '/players/skater/8480001/gamelog?season_id=20262027&page=2&pp_toi_seconds_min=0';
  expect(gamelogReturn(log, router)).toBe(log);
  for (const value of [
    'https://evil.example/',
    '/games',
    profile,
    '/players/unknown/8480001/gamelog',
    '/players/skater/8480001/gamelog?unknown=1',
  ])
    expect(gamelogReturn(value, router)).toBeNull();
});
