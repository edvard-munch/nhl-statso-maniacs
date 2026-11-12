import type { FavoriteGamelogResponse, FavoriteGamelogEntry } from '../../src/api/index.js';
import { gamelog } from './gamelog.js';
import { favorites } from './favorites.js';
export function favoriteGamelog(
  query = new URLSearchParams(),
  owner = 'First',
  overrides: Partial<FavoriteGamelogResponse> = {},
): FavoriteGamelogResponse {
  const source = gamelog(query);
  const goalie = query.get('player_type') === 'goalie';
  const identity = {
    player_type: goalie ? ('goalie' as const) : ('skater' as const),
    nhl_id: 8480001,
    name: `${owner} Saved Player`,
    last_name: 'Player',
    slug: 'saved-player',
    position_abbr: goalie ? 'G' : 'C',
  };
  const entries: FavoriteGamelogEntry[] = source.results.map((entry) => ({
    ...entry,
    player: { ...identity },
  }));
  // Two distinct favorite players share a saved game; neither row is deduplicated.
  entries.splice(1, 0, {
    ...entries[0]!,
    player: { ...identity, nhl_id: 8480002, name: `${owner} Second Player`, last_name: 'Second' },
  });
  return {
    count: entries.length,
    results: entries,
    next: null,
    previous: null,
    meta: {
      player_type: identity.player_type,
      season_id: query.get('season_id'),
      date_min: query.get('date_min'),
      date_max: query.get('date_max'),
      ordering: query.get('ordering') || '-date',
      quota: favorites().meta.quota,
    },
    ...overrides,
  };
}
