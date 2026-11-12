import type { LocationQuery, Router } from 'vue-router';
import type { MeFavoritesGamelogListQuery } from '../api/index.js';
import { safeReturnLocation } from '../auth/returnLocation.js';
import { gameOrderingFields, parseGamelogQuery } from '../players/gamelog.js';
export const FAVORITE_PLAYER_ORDER_FIELDS = ['player_name', 'player_last_name', 'player_nhl_id'];
export const FAVORITE_GAME_LABELS: Record<string, string> = {
  player_name: 'Player name',
  player_last_name: 'Player last name',
  player_nhl_id: 'Player NHL ID',
};
export function favoriteGameOrderingFields(type: string) {
  return [...FAVORITE_PLAYER_ORDER_FIELDS, ...gameOrderingFields(type)];
}
export function parseFavoriteGamelogQuery(raw: LocationQuery): MeFavoritesGamelogListQuery {
  const type = raw.player_type === undefined ? 'skater' : raw.player_type;
  if (type !== 'skater' && type !== 'goalie') throw new Error('Choose skater or goalie Favorites.');
  const common = { ...raw };
  delete common.player_type;
  delete common.search;
  delete common.ordering;
  const query = parseGamelogQuery(common, type);
  const search = raw.search;
  if (search !== undefined && (typeof search !== 'string' || !search.trim()))
    throw new Error('Choose a single nonempty player-name search.');
  const ordering = raw.ordering;
  if (ordering !== undefined) {
    if (typeof ordering !== 'string' || !ordering)
      throw new Error('Choose a single named ordering.');
    const keys = ordering.split(',').map((value) => value.replace(/^-/, ''));
    if (
      keys.some((key) => !favoriteGameOrderingFields(type).includes(key)) ||
      new Set(keys).size !== keys.length
    )
      throw new Error('Choose distinct supported player/game ordering fields.');
  }
  return {
    ...query,
    player_type: type,
    ...(typeof search === 'string' ? { search: search.trim() } : {}),
    ...(typeof ordering === 'string' ? { ordering } : {}),
  };
}
export function favoriteGamelogReturn(value: unknown, router: Router): string | null {
  const target = router.resolve(safeReturnLocation(value, router));
  if (target.name !== 'favorite-gamelog') return null;
  try {
    parseFavoriteGamelogQuery(target.query);
    return target.fullPath;
  } catch {
    return null;
  }
}
