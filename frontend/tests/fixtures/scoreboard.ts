import type {
  Freshness,
  GameDatesMeta,
  GameDatesResponse,
  ScoreboardGame,
  ScoreboardResponse,
} from '../../src/api/index.js';

export function freshness(overrides: Partial<Freshness> = {}): Freshness {
  return {
    has_data: true,
    is_final: false,
    saved_at: '2026-11-12T10:00:00Z',
    checked_at: '2026-11-12T10:01:00Z',
    age_seconds: 60,
    stale_after_seconds: 900,
    is_stale: false,
    partial: false,
    ...overrides,
  };
}
export function game(overrides: Partial<ScoreboardGame> = {}): ScoreboardGame {
  return {
    nhl_id: 2026020001,
    slug: 'tor-mtl',
    date: '2026-11-12',
    is_final: false,
    away_team: { nhl_id: 10, name: 'Toronto Maple Leafs', abbr: 'TOR', slug: 'toronto' },
    home_team: { nhl_id: 8, name: 'Montreal Canadiens', abbr: 'MTL', slug: 'montreal' },
    away_score: 0,
    home_score: 2,
    score_outcome: null,
    score_source: 'legacy_result',
    state: { value: 'unknown', source: null, observed_at: null, conflict: false },
    freshness: freshness(),
    ...overrides,
  };
}
export function gameDates(overrides: Partial<GameDatesMeta> = {}): GameDatesResponse {
  const meta: GameDatesMeta = {
    requested_date: '2026-11-12',
    reference_date: '2026-11-12',
    schedule_timezone: 'America/Los_Angeles',
    latest_date: '2026-11-14',
    selected_date: '2026-11-12',
    used_fallback: false,
    previous_date: '2026-11-10',
    next_date: '2026-11-14',
    window: ['2026-11-10', '2026-11-12', '2026-11-14'],
    ...overrides,
  };
  return {
    count: meta.window.length,
    next: null,
    previous: null,
    results: meta.window.map((date) => ({ date })),
    meta,
  };
}
export function games(
  date = '2026-11-12',
  results = [game()],
  overrides: Partial<ScoreboardResponse> = {},
): ScoreboardResponse {
  return {
    count: results.length,
    next: null,
    previous: null,
    results,
    meta: {
      date,
      freshness: freshness(
        results.length ? {} : { has_data: false, saved_at: null, age_seconds: null },
      ),
    },
    ...overrides,
  };
}
