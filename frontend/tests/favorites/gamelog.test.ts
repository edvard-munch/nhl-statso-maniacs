import { expect, it } from 'vitest';
import type { LocationQuery } from 'vue-router';
import { createMemoryHistory } from 'vue-router';
import { createAppRouter } from '../../src/router.js';
import { parseFavoriteGamelogQuery, favoriteGamelogReturn } from '../../src/favorites/gamelog.js';
import { parseGamelogQuery } from '../../src/players/gamelog.js';
it('defaults to skaters and all saved seasons without borrowing the list season', () => {
  expect(parseFavoriteGamelogQuery({})).toEqual({ player_type: 'skater', page: 1, page_size: 50 });
});
it('adds literal name search and global identity ordering while excluding navigation context', () => {
  expect(
    parseFavoriteGamelogQuery({
      player_type: 'goalie',
      search: '  %_Name  ',
      ordering: 'player_name,-date,player_nhl_id',
      save_percentage_min: '0.9',
      shutouts_min: '0',
      saves_isnull: 'false',
      page: '2',
      returnTo: '/favorites?page=2',
    }),
  ).toEqual({
    player_type: 'goalie',
    search: '%_Name',
    ordering: 'player_name,-date,player_nhl_id',
    save_percentage_min: 0.9,
    shutouts_min: 0,
    saves_isnull: false,
    page: 2,
    page_size: 50,
  });
});
it.each<LocationQuery>([
  { player_type: 'both' },
  { player_type: null },
  { player_type: ['skater'] },
  { search: '' },
  { search: ['Name'] },
  { ordering: 'player_name,-player_name' },
  { ordering: ['player_name'] },
  { ordering: 'player__name' },
  { ordering: 'player_nhl_id_min' },
  { player_nhl_id_min: '1' },
  { mode: 'averages' },
  { season_id: '2026-27' },
  { owner_id: '2' },
  { player_type: 'goalie', goals_min: '1' },
  { date_min: '2026-11-12', date_max: '2026-11-10' },
  { page: '0' },
])('rejects unsupported private log queries without broadening scope %j', (query) => {
  expect(() => parseFavoriteGamelogQuery(query)).toThrow();
});
it('keeps identity ordering and name search exclusive to the aggregated contract', () => {
  expect(() => parseGamelogQuery({ ordering: 'player_name' }, 'skater')).toThrow();
  expect(() => parseGamelogQuery({ search: 'Name' }, 'skater')).toThrow();
});
it('validates local private-log return destinations without authorizing a private read', () => {
  const router = createAppRouter(createMemoryHistory());
  const target = '/favorites/gamelog?player_type=goalie&ordering=player_name,-date&page=2';
  expect(favoriteGamelogReturn(target, router)).toBe(target);
  for (const value of [
    'https://evil.example/',
    '//evil.example/',
    '/favorites',
    '/favorites/gamelog?owner_id=2',
    '/favorites/gamelog?mode=totals',
    '/favorites/gamelog?ordering=player_name,-player_name',
  ])
    expect(favoriteGamelogReturn(value, router)).toBeNull();
});
