import type { LocationQuery, Router } from 'vue-router';
import type { TeamsListQuery, TeamPlayersListQuery } from '../api/index.js';
import { safeReturnLocation } from '../auth/returnLocation.js';
import { parseGameId } from '../games/presentation.js';
import {
  FIRST_PAGE,
  PAGE_SIZE,
  METADATA_PAGE_SIZE,
  parseCatalogueQuery,
} from '../players/catalogue.js';

const MAX_TEAM_NHL_ID = 2 ** 31 - 1; // Existing API/database integer bound.
const POSITIVE_INTEGER = /^[1-9]\d*$/;
const DIRECTORY_FIELDS = new Set([
  'search',
  'conference',
  'division',
  'ordering',
  'page',
  'page_size',
]);
export const TEAM_ORDER_FIELDS = ['name', 'abbr', 'nhl_id', 'conference', 'division'];
export const TEAM_PAGE_SIZES = [25, 50, 100];
export function parseTeamId(value: unknown): number | null {
  const id = parseGameId(value);
  return id !== null && id <= MAX_TEAM_NHL_ID ? id : null;
}
export function parseTeamsQuery(raw: LocationQuery): TeamsListQuery {
  const query: Record<string, string | number> = { page: FIRST_PAGE, page_size: PAGE_SIZE };
  for (const [key, value] of Object.entries(raw)) {
    if (!DIRECTORY_FIELDS.has(key) || typeof value !== 'string' || !value.trim())
      throw new Error('The Teams URL contains an unsupported, repeated or empty filter.');
    if (key === 'page' || key === 'page_size') {
      const number = Number(value);
      if (
        !POSITIVE_INTEGER.test(value) ||
        !Number.isSafeInteger(number) ||
        (key === 'page_size' && number > METADATA_PAGE_SIZE)
      )
        throw new Error('Choose a positive page and page size (maximum 100).');
      query[key] = number;
    } else query[key] = key === 'search' ? value.trim() : value;
  }
  for (const field of ['conference', 'division', 'ordering']) {
    if (query[field] === undefined) continue;
    const values = String(query[field]).split(',');
    const keys = field === 'ordering' ? values.map((value) => value.replace(/^-/, '')) : values;
    if (
      values.some((value) => !value || value.trim() !== value) ||
      new Set(keys).size !== keys.length ||
      (field === 'ordering' && keys.some((value) => !TEAM_ORDER_FIELDS.includes(value)))
    )
      throw new Error('Choose distinct supported conference, division and ordering values.');
  }
  return query as TeamsListQuery;
}
export function parseTeamPlayersQuery(raw: LocationQuery): TeamPlayersListQuery {
  if ('team' in raw) throw new Error('The team is selected by the URL, not a team filter.');
  if (raw.returnTo !== undefined && (typeof raw.returnTo !== 'string' || !raw.returnTo))
    throw new Error('Choose a single nonempty return destination.');
  const filters = { ...raw };
  delete filters.returnTo;
  return parseCatalogueQuery(filters);
}
export function teamsReturn(value: unknown, router: Router): string {
  const target = router.resolve(safeReturnLocation(value, router));
  if (target.name !== 'teams') return '/teams';
  try {
    parseTeamsQuery(target.query);
    return target.fullPath;
  } catch {
    return '/teams';
  }
}
/** A profile may return to a validated team table as well as the public catalogue. */
export function teamSourceReturn(value: unknown, router: Router): string | null {
  const target = router.resolve(safeReturnLocation(value, router));
  if (target.name !== 'team-detail' || parseTeamId(target.params.nhlId) === null) return null;
  try {
    parseTeamPlayersQuery(target.query);
    return target.fullPath;
  } catch {
    return null;
  }
}
export function externalWebsite(value: string): string | null {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
