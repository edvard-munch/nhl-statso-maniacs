import type { LocationQuery, Router } from 'vue-router';
import type {
  GamelogStatistics,
  PlayerGamelogListQuery,
  PlayerRetrievePath,
} from '../api/index.js';
import { safeReturnLocation } from '../auth/returnLocation.js';
import { numberLabel, savePercentageLabel, toiLabel } from '../games/presentation.js';
import { isScheduleDate } from '../scoreboard/presentation.js';
import { FIRST_PAGE, PAGE_SIZE, METADATA_PAGE_SIZE, FIELD_LABELS, isSeason } from './catalogue.js';
import { parsePlayerIdentity, parseProfileQuery } from './profile.js';

export const SKATER_GAME_FIELDS = [
  'goals',
  'assists',
  'points',
  'plus_minus',
  'penalty_minutes',
  'shots_on_goal',
  'hits',
  'blocked_shots',
  'faceoffs_won',
  'pp_points',
  'sh_points',
  'toi_seconds',
  'pp_toi_seconds',
  'sh_toi_seconds',
] as const;
export const GOALIE_GAME_FIELDS = [
  'decision',
  'toi_seconds',
  'goals_against',
  'saves',
  'shots_against',
  'save_percentage',
  'shutouts',
] as const;
export const GAME_FIELD_LABELS: Record<string, string> = {
  ...FIELD_LABELS,
  date: 'Date',
  game_id: 'Game ID',
  team_abbr: 'Team',
  opponent_abbr: 'Opponent',
  decision: 'Decision',
  goals_against: 'Goals against',
  shots_against: 'Shots against',
  toi_seconds: 'TOI (seconds)',
  pp_toi_seconds: 'PP TOI (seconds)',
  sh_toi_seconds: 'SH TOI (seconds)',
};
export const GAME_PAGE_SIZES = [25, 50, 100];
const BASE_FIELDS = [
  'season_id',
  'date_min',
  'date_max',
  'team',
  'opponent',
  'ordering',
  'page',
  'page_size',
  'returnTo',
];
const POSITIVE_INTEGER = /^[1-9]\d*$/;
const FINITE_NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
export function gameFields(type: string) {
  return type === 'goalie' ? GOALIE_GAME_FIELDS : SKATER_GAME_FIELDS;
}
export function gameNumericFields(type: string) {
  return gameFields(type).filter((field) => field !== 'decision');
}
export function gameOrderingFields(type: string) {
  return ['date', 'game_id', 'team_abbr', 'opponent_abbr', ...gameFields(type)];
}
export function parseGamelogQuery(raw: LocationQuery, type: string): PlayerGamelogListQuery {
  const numeric = gameNumericFields(type);
  const allowed = new Set([
    ...BASE_FIELDS,
    ...numeric.flatMap((field) => [`${field}_min`, `${field}_max`, `${field}_isnull`]),
  ]);
  const query: Record<string, string | number | boolean> = {
    page: FIRST_PAGE,
    page_size: PAGE_SIZE,
  };
  for (const [key, value] of Object.entries(raw)) {
    if (!allowed.has(key) || typeof value !== 'string' || !value.trim())
      throw new Error('The gamelog URL contains an unsupported, repeated or empty selection.');
    if (key === 'returnTo') continue;
    if (key === 'page' || key === 'page_size') {
      const number = Number(value);
      if (
        !POSITIVE_INTEGER.test(value) ||
        !Number.isSafeInteger(number) ||
        (key === 'page_size' && number > METADATA_PAGE_SIZE)
      )
        throw new Error('Choose a positive page and page size (maximum 100).');
      query[key] = number;
    } else query[key] = value;
  }
  if (query.season_id !== undefined && !isSeason(String(query.season_id)))
    throw new Error('Choose a consecutive eight-digit season ID.');
  for (const field of ['date_min', 'date_max'])
    if (query[field] !== undefined && !isScheduleDate(query[field]))
      throw new Error('Choose valid schedule dates.');
  if (query.date_min && query.date_max && query.date_min > query.date_max)
    throw new Error('The first date cannot follow the last date.');
  for (const field of numeric) {
    for (const bound of ['min', 'max']) {
      const key = `${field}_${bound}`;
      if (query[key] === undefined) continue;
      if (!FINITE_NUMBER.test(String(query[key])) || !Number.isFinite(Number(query[key])))
        throw new Error('Numeric bounds must be finite numbers.');
      query[key] = Number(query[key]);
    }
    const key = `${field}_isnull`;
    if (query[key] !== undefined) {
      if (!['true', 'false'].includes(String(query[key])))
        throw new Error('Missing-value filters must be true or false.');
      query[key] = query[key] === 'true';
    }
    if (
      query[`${field}_min`] !== undefined &&
      query[`${field}_max`] !== undefined &&
      Number(query[`${field}_min`]) > Number(query[`${field}_max`])
    )
      throw new Error('Minimum bounds cannot exceed maximum bounds.');
  }
  for (const field of ['team', 'opponent', 'ordering']) {
    if (query[field] === undefined) continue;
    const values = String(query[field]).split(',');
    const keys = field === 'ordering' ? values.map((value) => value.replace(/^-/, '')) : values;
    if (
      values.some((value) => !value || value.trim() !== value) ||
      new Set(keys).size !== keys.length ||
      (field === 'ordering' && keys.some((value) => !gameOrderingFields(type).includes(value)))
    )
      throw new Error('Choose distinct supported team, opponent and ordering values.');
  }
  return query as PlayerGamelogListQuery;
}
export function profileReturn(
  value: unknown,
  router: Router,
  identity: PlayerRetrievePath,
): string {
  const fallback = `/players/${identity.player_type}/${identity.nhl_id}`;
  const safe = safeReturnLocation(value, router);
  const target = router.resolve(safe);
  if (target.name !== 'player-profile') return fallback;
  const path = parsePlayerIdentity(target.params.playerType, target.params.nhlId);
  if (!path || path.player_type !== identity.player_type || path.nhl_id !== identity.nhl_id)
    return fallback;
  try {
    parseProfileQuery(target.query, path.player_type);
    return target.fullPath;
  } catch {
    return fallback;
  }
}
export function gamelogReturn(value: unknown, router: Router): string | null {
  const safe = safeReturnLocation(value, router);
  const target = router.resolve(safe);
  if (target.name !== 'player-gamelog') return null;
  const path = parsePlayerIdentity(target.params.playerType, target.params.nhlId);
  if (!path) return null;
  try {
    parseGamelogQuery(target.query, path.player_type);
    return target.fullPath;
  } catch {
    return null;
  }
}
export function gameStatisticLabel(stats: GamelogStatistics, field: string): string {
  const value = (stats as unknown as Record<string, unknown>)[field];
  if (field === 'decision') return typeof value === 'string' && value ? value : '—';
  if (typeof value !== 'number') return '—';
  if (field.endsWith('_seconds')) return toiLabel(value);
  if (field === 'save_percentage') return savePercentageLabel(value);
  return numberLabel(value);
}
