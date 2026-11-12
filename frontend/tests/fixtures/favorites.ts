import type { FavoritesResponse, FavoritePlayer } from '../../src/api/index.js';
import { player } from './players.js';
import { profileStats } from './profile.js';
export function favorites(
  query = new URLSearchParams(),
  owner = 'First',
  overrides: Partial<FavoritesResponse> = {},
): FavoritesResponse {
  const goalie = query.get('player_type') === 'goalie';
  const averages = query.get('mode') === 'averages';
  const base = player();
  const known: FavoritePlayer = {
    ...base,
    name: `${owner} Saved Player`,
    player_type: goalie ? 'goalie' : 'skater',
    stats: goalie
      ? {
          kind: 'goalie_totals',
          games: 2,
          wins: 0,
          losses: 1,
          ot_losses: null,
          saves: 40,
          shutouts: 0,
          goals_against_average: null,
          save_percentage: 0.915,
        }
      : profileStats(averages ? { kind: 'skater_averages', goals: 0, points: 0.375 } : {}),
  };
  let entries: FavoritePlayer[] = goalie
    ? [known]
    : [
        known,
        {
          ...base,
          nhl_id: 8480002,
          name: `${owner} Missing Player`,
          availability: 'missing',
          stats: null,
          teams: [],
        },
        {
          ...base,
          nhl_id: 8480003,
          name: `${owner} Zero Player`,
          stats: profileStats({ games: 0, goals: 0 }),
          teams: [],
        },
        {
          ...base,
          nhl_id: 8480004,
          name: `${owner} Unverified Player`,
          availability: 'unverified',
          stats: null,
          teams: [],
        },
      ];
  if (query.get('season_id') === '20272028')
    entries = entries.map((entry) => ({
      ...entry,
      availability: 'missing',
      stats: null,
      teams: [],
    }));
  return {
    count: entries.length,
    next: null,
    previous: null,
    results: entries,
    meta: {
      season_id: query.get('season_id') || '20262027',
      player_type: goalie ? 'goalie' : 'skater',
      mode: averages ? 'averages' : 'totals',
      ordering:
        query.get('ordering') || (goalie ? '-wins,last_name,nhl_id' : '-points,last_name,nhl_id'),
      quota: {
        limit: 100,
        skaters_count: 4,
        goalies_count: 1,
        total_count: 5,
        remaining: 95,
        over_limit: false,
      },
    },
    ...overrides,
  };
}
