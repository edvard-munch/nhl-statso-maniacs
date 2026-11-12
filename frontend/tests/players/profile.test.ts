import { expect, it } from 'vitest';
import type { LocationQuery } from 'vue-router';
import { createMemoryHistory } from 'vue-router';
import { createAppRouter } from '../../src/router.js';
import {
  parsePlayerIdentity,
  parseProfileQuery,
  profileStatisticLabel,
  catalogueReturn,
} from '../../src/players/profile.js';
import { profileStats } from '../fixtures/profile.js';

it.each([
  ['skater', '0'],
  ['skater', '2147483648'],
  ['goalie', '1.5'],
  ['unknown', '8480001'],
  ['skater', ['8480001']],
  ['skater', '9007199254740993'],
])('rejects invalid typed identities (%s, %j)', (type, id) => {
  expect(parsePlayerIdentity(type, id)).toBeNull();
});
it('keeps typed identity explicit even when model IDs overlap', () => {
  expect(parsePlayerIdentity('skater', '8480001')).toEqual({
    player_type: 'skater',
    nhl_id: 8480001,
  });
  expect(parsePlayerIdentity('goalie', '8480001')).toEqual({
    player_type: 'goalie',
    nhl_id: 8480001,
  });
});
it('keeps navigation/history context out of the API query', () => {
  expect(
    parseProfileQuery(
      { season_id: '20272028', mode: 'averages', history_page: '2', returnTo: '/players?team=BUF' },
      'skater',
    ),
  ).toEqual({ query: { season_id: '20272028', mode: 'averages' }, page: 2 });
});
it.each<LocationQuery>([
  { season_id: '2026-27' },
  { season_id: '20262028' },
  { mode: ['totals'] },
  { history_page: '0' },
  { history_page: '' },
  { search: 'a' },
])('rejects malformed profile selections %j', (query) => {
  expect(() => parseProfileQuery(query, 'skater')).toThrow();
});
it('rejects goalie averages', () =>
  expect(() => parseProfileQuery({ mode: 'averages' }, 'goalie')).toThrow());
it('accepts only valid public catalogue return URLs', () => {
  const router = createAppRouter(createMemoryHistory());
  expect(catalogueReturn('/players?season_id=20262027&page=2&team=BUF', router)).toBe(
    '/players?season_id=20262027&page=2&team=BUF',
  );
  for (const value of [
    'https://evil.example/',
    '//evil.example/',
    '/login',
    '/players/skater/8480001',
    '/players?unknown=1',
    '/players?team=BUF&team=COL',
  ])
    expect(catalogueReturn(value, router)).toBe('/players');
});
it('preserves zero, nullable games, duration and saved career-average precision', () => {
  expect(profileStatisticLabel(null, 'games')).toBe('—');
  expect(profileStatisticLabel(profileStats({ games: null, goals: 0 }), 'games')).toBe('—');
  expect(profileStatisticLabel(profileStats({ goals: 0 }), 'goals')).toBe('0');
  expect(
    profileStatisticLabel(profileStats({ kind: 'skater_averages', points: 1.234 }), 'points'),
  ).toBe('1.234');
  expect(profileStatisticLabel(profileStats(), 'avg_pp_toi_seconds')).toBe('00:00');
});
