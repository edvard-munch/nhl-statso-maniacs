import type { LocationQuery, Router } from 'vue-router';
import type { PlayerRetrievePath, PlayerRetrieveQuery, ProfileStatistics } from '../api/index.js';
import { safeReturnLocation } from '../auth/returnLocation.js';
import { parseGameId, numberLabel, savePercentageLabel, toiLabel } from '../games/presentation.js';
import { parsePage } from '../scoreboard/presentation.js';
import { isSeason, parseCatalogueQuery } from './catalogue.js';

const MAX_PLAYER_NHL_ID = 2 ** 31 - 1; // Existing backend typed-identity bound.
const PROFILE_QUERY_FIELDS = new Set(['season_id', 'mode', 'history_page', 'returnTo']);
export const HISTORY_PAGE_SIZE = 25;
export function parsePlayerIdentity(type: unknown, value: unknown): PlayerRetrievePath | null {
  const id = parseGameId(value);
  return (type === 'skater' || type === 'goalie') && id !== null && id <= MAX_PLAYER_NHL_ID
    ? { player_type: type, nhl_id: id }
    : null;
}
export function parseProfileQuery(raw: LocationQuery, type: string) {
  for (const [key, value] of Object.entries(raw)) {
    if (!PROFILE_QUERY_FIELDS.has(key) || typeof value !== 'string' || !value)
      throw new Error('The profile URL contains an unsupported, repeated or empty selection.');
  }
  const mode = raw.mode ?? 'totals';
  if ((mode !== 'totals' && mode !== 'averages') || (type === 'goalie' && mode !== 'totals'))
    throw new Error('Choose skater totals/averages or goalie totals.');
  const season = raw.season_id;
  if (season !== undefined && (typeof season !== 'string' || !isSeason(season)))
    throw new Error('Choose a consecutive eight-digit season ID.');
  const page = parsePage(raw.history_page);
  if (page === null) throw new Error('Choose a positive history page number.');
  const query: PlayerRetrieveQuery = {
    mode,
    ...(typeof season === 'string' ? { season_id: season } : {}),
  };
  return { query, page };
}
/** Only a validated public catalogue is a profile return destination. */
export function catalogueReturn(value: unknown, router: Router): string {
  const safe = safeReturnLocation(value, router);
  const destination = router.resolve(safe);
  if (destination.name !== 'players') return '/players';
  try {
    parseCatalogueQuery(destination.query);
    return destination.fullPath;
  } catch {
    return '/players';
  }
}
export function profileStatisticLabel(stats: ProfileStatistics | null, field: string): string {
  const value = (stats as unknown as Record<string, unknown> | null)?.[field];
  if (typeof value !== 'number') return '—';
  if (field.startsWith('avg_')) return toiLabel(value);
  if (field === 'save_percentage') return savePercentageLabel(value);
  return numberLabel(value);
}
