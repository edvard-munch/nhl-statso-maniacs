import type { LocationQuery } from 'vue-router';
import { expect, it } from 'vitest';
import { parseCatalogueQuery, statisticLabel } from '../../src/players/catalogue.js';
import { player } from '../fixtures/players.js';

it('preserves typed season filters, numeric zero, multiple ordering fields and pagination', () => {
  expect(
    parseCatalogueQuery({
      season_id: '20262027',
      team: 'BUF,COL',
      points_min: '0',
      hits_isnull: 'true',
      ordering: '-points,last_name',
      page: '2',
      page_size: '25',
      search: '  Mc  ',
    }),
  ).toEqual({
    season_id: '20262027',
    player_type: 'skater',
    mode: 'totals',
    team: 'BUF,COL',
    points_min: '0',
    hits_isnull: 'true',
    ordering: '-points,last_name',
    page: 2,
    page_size: 25,
    search: 'Mc',
  });
});
it.each<LocationQuery>([
  { season_id: '2026-27' },
  { season_id: '20262028' },
  { player_type: 'goalie', mode: 'averages' },
  { player_type: ['skater', 'goalie'] },
  { player_type: 'goalie', goals_min: '1' },
  { ordering: '-points,points' },
  { ordering: 'bogus' },
  { team: 'BUF,BUF' },
  { page: '0' },
  { page_size: '101' },
  { points_min: 'Infinity' },
  { points_min: '4', points_max: '3' },
  { hits_isnull: 'yes' },
  { search: '' },
  { birth_date_min: '2026-02-30' },
  { unexpected: 'data' },
])('rejects malformed URL state rather than silently broadening the selection: %j', (query) => {
  expect(() => parseCatalogueQuery(query)).toThrow();
});
it('formats actual zero, missing fields and per-game duration distinctly', () => {
  const entry = player();
  expect(statisticLabel(entry, 'goals')).toBe('0');
  expect(statisticLabel(entry, 'hits')).toBe('—');
  expect(statisticLabel(entry, 'avg_toi_seconds')).toBe('10:01');
  expect(statisticLabel(entry, 'avg_pp_toi_seconds')).toBe('00:00');
});
