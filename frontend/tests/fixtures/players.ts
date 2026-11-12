import type {
  CataloguePlayer,
  PlayersResponse,
  PlayersFiltersResponse,
  SeasonsResponse,
} from '../../src/api/index.js';
export const loadedSeasons: SeasonsResponse = {
  count: 2,
  next: null,
  previous: null,
  meta: { default_season_id: '20262027' },
  results: [
    { season_id: '20262027', label: '2026–27' },
    { season_id: '20252026', label: '2025–26' },
  ],
};
export function player(overrides: Partial<CataloguePlayer> = {}): CataloguePlayer {
  return {
    player_type: 'skater',
    nhl_id: 8480001,
    name: 'Season Skater',
    last_name: 'Skater',
    slug: 'season-skater',
    image_url: null,
    nation_flag_url: null,
    position_abbr: 'C',
    position_name: 'Center',
    nation: 'Canada',
    nation_abbr: 'CAN',
    birth_date: '2000-01-01',
    age: 26,
    height_cm: 180,
    weight_kg: 80,
    weight_lb: 176,
    draft_year: null,
    draft_number: null,
    rookie: false,
    availability: 'partial',
    teams: [
      { nhl_id: 7, abbr: 'BUF', name: 'Buffalo Sabres', slug: 'buffalo' },
      { nhl_id: null, abbr: 'OLD', name: 'OLD', slug: null },
    ],
    stats: {
      kind: 'skater_totals',
      games: 8,
      goals: 0,
      assists: 3,
      points: 3,
      plus_minus: -1,
      penalty_minutes: 0,
      shots_on_goal: 9,
      hits: null,
      blocked_shots: 0,
      faceoffs_won: 12,
      pp_points: 0,
      sh_points: 0,
      avg_toi_seconds: 601,
      avg_pp_toi_seconds: 0,
      avg_sh_toi_seconds: null,
    },
    ...overrides,
  };
}
export function catalogue(
  query = new URLSearchParams(),
  overrides: Partial<PlayersResponse> = {},
): PlayersResponse {
  const goalie = query.get('player_type') === 'goalie';
  const averages = query.get('mode') === 'averages';
  let entry = goalie
    ? player({
        name: 'Season Goalie',
        player_type: 'goalie',
        position_abbr: 'G',
        stats: {
          kind: 'goalie_totals',
          games: 4,
          wins: 0,
          losses: 2,
          ot_losses: null,
          saves: 85,
          shutouts: 0,
          goals_against_average: null,
          save_percentage: 0.915,
        },
      })
    : player();
  if (averages && entry.stats.kind === 'skater_totals')
    entry = { ...entry, stats: { ...entry.stats, kind: 'skater_averages', points: 0.375 } };
  return {
    count: 1,
    next: null,
    previous: null,
    results: [entry],
    meta: {
      season_id: query.get('season_id') || '20262027',
      player_type: goalie ? 'goalie' : 'skater',
      mode: averages ? 'averages' : 'totals',
      ordering:
        query.get('ordering') || (goalie ? '-wins,last_name,nhl_id' : '-points,last_name,nhl_id'),
    },
    ...overrides,
  };
}
export function filterMetadata(query = new URLSearchParams()): PlayersFiltersResponse {
  const meta = catalogue(query).meta;
  return {
    meta,
    initial_count: 150,
    options_count: 140,
    filtered_count: 1,
    initial_ranges: { points: { min: 0, max: 100 }, height_cm: { min: 170, max: 200 } },
    filtered_ranges: { points: { min: 3, max: 3 } },
    height_values_cm: [180],
    options: {
      teams: [
        { nhl_id: 7, abbr: 'BUF', name: 'Buffalo Sabres', slug: 'buffalo' },
        { nhl_id: 8, abbr: 'MTL', name: 'Montreal Canadiens', slug: 'montreal' },
      ],
      nations: [
        { code: 'CAN', label: 'Canada' },
        { code: 'FIN', label: 'Finland' },
      ],
      positions: [
        {
          code: meta.player_type === 'goalie' ? 'G' : 'C',
          label: meta.player_type === 'goalie' ? 'Goalie' : 'Center',
        },
      ],
    },
  };
}
