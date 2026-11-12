import type { LocationQuery } from 'vue-router';
import type { CataloguePlayer, PlayersListQuery } from '../api/index.js';
import { numberLabel, savePercentageLabel, toiLabel } from '../games/presentation.js';

export const FIRST_PAGE = 1;
export const PAGE_SIZE = 50;
export const METADATA_PAGE_SIZE = 100;
export const BIOGRAPHY_FIELDS = [
  'age',
  'height_cm',
  'weight_kg',
  'weight_lb',
  'draft_year',
  'draft_number',
] as const;
export const SKATER_FIELDS = [
  'games',
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
  'avg_toi_seconds',
  'avg_pp_toi_seconds',
  'avg_sh_toi_seconds',
] as const;
export const GOALIE_FIELDS = [
  'games',
  'wins',
  'losses',
  'ot_losses',
  'saves',
  'shutouts',
  'goals_against_average',
  'save_percentage',
] as const;
const IDENTITY_ORDER_FIELDS = [
  'name',
  'last_name',
  'nhl_id',
  'position_abbr',
  'nation_abbr',
  'birth_date',
];
const BASE_FIELDS = [
  'season_id',
  'player_type',
  'mode',
  'search',
  'team',
  'nation',
  'position',
  'rookie',
  'birth_date_min',
  'birth_date_max',
  'ordering',
  'page',
  'page_size',
];
const POSITIVE_INTEGER = /^[1-9]\d*$/;
const FINITE_NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
export const FIELD_LABELS: Record<string, string> = {
  games: 'GP',
  goals: 'Goals',
  assists: 'Assists',
  points: 'Points',
  plus_minus: '+/−',
  penalty_minutes: 'PIM',
  shots_on_goal: 'SOG',
  hits: 'Hits',
  blocked_shots: 'Blocks',
  faceoffs_won: 'Faceoffs won',
  pp_points: 'PP points',
  sh_points: 'SH points',
  avg_toi_seconds: 'Average TOI (seconds)',
  avg_pp_toi_seconds: 'Average PP TOI (seconds)',
  avg_sh_toi_seconds: 'Average SH TOI (seconds)',
  wins: 'Wins',
  losses: 'Losses',
  ot_losses: 'OT losses',
  saves: 'Saves',
  shutouts: 'Shutouts',
  goals_against_average: 'GAA',
  save_percentage: 'Save fraction (0–1)',
  age: 'Age',
  height_cm: 'Height (cm)',
  weight_kg: 'Weight (kg)',
  weight_lb: 'Weight (lb)',
  draft_year: 'Draft year',
  draft_number: 'Draft number',
  name: 'Name',
  last_name: 'Last name',
  nhl_id: 'NHL ID',
  position_abbr: 'Position',
  nation_abbr: 'Nation',
  birth_date: 'Birth date',
};
export function numericFields(type: string) {
  return [...BIOGRAPHY_FIELDS, ...(type === 'goalie' ? GOALIE_FIELDS : SKATER_FIELDS)];
}
export function orderFields(type: string) {
  return [...IDENTITY_ORDER_FIELDS, ...numericFields(type)];
}
export function seasonLabel(value: string) {
  return `${value.slice(0, 4)}–${value.slice(6)}`;
}
export function isSeason(value: string) {
  return /^\d{8}$/.test(value) && Number(value.slice(4)) === Number(value.slice(0, 4)) + 1;
}
function isDate(value: string) {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  );
}
/** Reject malformed navigation rather than quietly displaying a different population. */
export function parseCatalogueQuery(raw: LocationQuery): PlayersListQuery {
  const type = raw.player_type ?? 'skater';
  const mode = raw.mode ?? 'totals';
  if (
    !['skater', 'goalie'].includes(String(type)) ||
    !['totals', 'averages'].includes(String(mode)) ||
    (type === 'goalie' && mode !== 'totals')
  )
    throw new Error('Choose skater totals/averages or goalie totals.');
  const numeric = numericFields(String(type));
  const allowed = new Set([
    ...BASE_FIELDS,
    ...numeric.flatMap((field) => [`${field}_min`, `${field}_max`, `${field}_isnull`]),
  ]);
  const query: Record<string, string | number> = {
    player_type: String(type),
    mode: String(mode),
    page: FIRST_PAGE,
    page_size: PAGE_SIZE,
  };
  for (const [key, value] of Object.entries(raw)) {
    if (!allowed.has(key) || typeof value !== 'string' || !value.trim())
      throw new Error('The Players URL contains an unsupported, repeated or empty filter.');
    if (key === 'page' || key === 'page_size') {
      const integer = Number(value);
      if (
        !POSITIVE_INTEGER.test(value) ||
        !Number.isSafeInteger(integer) ||
        (key === 'page_size' && integer > METADATA_PAGE_SIZE)
      )
        throw new Error('Choose a positive page and page size (maximum 100).');
      query[key] = integer;
    } else query[key] = key === 'search' ? value.trim() : value;
  }
  if (query.season_id && !isSeason(String(query.season_id)))
    throw new Error('Choose a consecutive eight-digit season ID.');
  for (const key of ['birth_date_min', 'birth_date_max'])
    if (query[key] && !isDate(String(query[key]))) throw new Error('Choose valid birth dates.');
  for (const field of numeric) {
    for (const bound of ['min', 'max']) {
      const value = query[`${field}_${bound}`];
      if (
        value !== undefined &&
        (!FINITE_NUMBER.test(String(value)) || !Number.isFinite(Number(value)))
      )
        throw new Error('Numeric bounds must be finite numbers.');
    }
    const missing = query[`${field}_isnull`];
    if (missing !== undefined && !['true', 'false'].includes(String(missing)))
      throw new Error('Missing-value filters must be true or false.');
    if (
      query[`${field}_min`] !== undefined &&
      query[`${field}_max`] !== undefined &&
      Number(query[`${field}_min`]) > Number(query[`${field}_max`])
    )
      throw new Error('Minimum bounds cannot exceed maximum bounds.');
  }
  if (query.birth_date_min && query.birth_date_max && query.birth_date_min > query.birth_date_max)
    throw new Error('Birth-date minimum cannot exceed maximum.');
  if (query.rookie !== undefined && !['true', 'false'].includes(String(query.rookie)))
    throw new Error('Choose a valid rookie filter.');
  for (const key of ['team', 'position', 'nation', 'ordering']) {
    if (query[key] === undefined) continue;
    const values = String(query[key]).split(',');
    const distinct = key === 'ordering' ? values.map((value) => value.replace(/^-/, '')) : values;
    if (
      values.some((value) => !value || value.trim() !== value) ||
      new Set(distinct).size !== values.length ||
      (key === 'ordering' && distinct.some((value) => !orderFields(String(type)).includes(value)))
    )
      throw new Error('Choose distinct, supported filter and ordering values.');
  }
  return query as PlayersListQuery;
}
export function statisticLabel(player: CataloguePlayer, field: string) {
  const value = (player.stats as unknown as Record<string, number | string | null>)[field];
  if (typeof value !== 'number') return '—';
  if (field.startsWith('avg_')) return toiLabel(value);
  if (field === 'save_percentage') return savePercentageLabel(value);
  return numberLabel(value);
}
