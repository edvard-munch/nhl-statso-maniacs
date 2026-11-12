import { expect, it } from 'vitest';
import type { LocationQuery } from 'vue-router';
import { createMemoryHistory } from 'vue-router';
import { createAppRouter } from '../../src/router.js';
import {
  parseTeamId,
  parseTeamsQuery,
  parseTeamPlayersQuery,
  teamsReturn,
  teamSourceReturn,
  externalWebsite,
} from '../../src/teams/navigation.js';
it('preserves directory search, exact named filters, ordering and typed pagination', () => {
  expect(
    parseTeamsQuery({
      search: '  BUF ',
      conference: 'Eastern,Western',
      division: 'Atlantic',
      ordering: '-name,nhl_id',
      page: '2',
      page_size: '25',
    }),
  ).toEqual({
    search: 'BUF',
    conference: 'Eastern,Western',
    division: 'Atlantic',
    ordering: '-name,nhl_id',
    page: 2,
    page_size: 25,
  });
});
it.each<LocationQuery>([
  { season_id: '20262027' },
  { page: '0' },
  { page_size: '101' },
  { page: ['1', '2'] },
  { search: '' },
  { division: 'Atlantic,' },
  { conference: 'Eastern,Eastern' },
  { ordering: 'name,-name' },
  { ordering: '-points' },
])('rejects malformed directory queries %j', (query) =>
  expect(() => parseTeamsQuery(query)).toThrow(),
);
it('uses catalogue selection rules but removes context and rejects a team selector', () => {
  expect(
    parseTeamPlayersQuery({
      season_id: '20262027',
      mode: 'averages',
      goals_min: '0.5',
      returnTo: '/teams?page=2',
    }),
  ).toMatchObject({ season_id: '20262027', mode: 'averages', goals_min: '0.5' });
  expect(parseTeamPlayersQuery({ returnTo: '/teams' })).not.toHaveProperty('returnTo');
  const invalid: LocationQuery[] = [
    { team: 'BUF' },
    { player_type: 'goalie', mode: 'averages' },
    { player_type: 'goalie', points_min: '1' },
    { returnTo: ['/teams', '/players'] },
  ];
  for (const query of invalid) expect(() => parseTeamPlayersQuery(query)).toThrow();
});
it.each(['0', '-1', '1.5', '2147483648', 'bad', ['7']])('rejects invalid team IDs %j', (value) =>
  expect(parseTeamId(value)).toBeNull(),
);
it('accepts bounded positive team identity', () => expect(parseTeamId('7')).toBe(7));
it('accepts only validated local team return context', () => {
  const router = createAppRouter(createMemoryHistory());
  const directory = '/teams?conference=Eastern&page=2';
  const detail = '/teams/7?season_id=20262027&mode=averages&page=2';
  expect(teamsReturn(directory, router)).toBe(directory);
  expect(teamSourceReturn(detail, router)).toBe(detail);
  for (const value of [
    'https://evil.example/',
    '//evil.example/',
    '/players',
    '/teams?season_id=20262027',
  ])
    expect(teamsReturn(value, router)).toBe('/teams');
  for (const value of [
    'https://evil.example/',
    '/teams/0',
    '/teams/7?team=MTL',
    '/teams/7?mode=bad',
    '/players',
  ])
    expect(teamSourceReturn(value, router)).toBeNull();
});
it('links saved HTTP websites without treating arbitrary schemes or embedded credentials as links', () => {
  expect(externalWebsite('https://example.com/team')).toBe('https://example.com/team');
  for (const value of [
    '',
    'javascript:alert(1)',
    '//example.com',
    'https://user:secret@example.com',
  ])
    expect(externalWebsite(value)).toBeNull();
});
