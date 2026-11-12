import { gameDetail, skater, emptyRoster } from './game-detail.js';
import type {
  GamelogResponse,
  GamelogEntry,
  SkaterGameStats,
  GoalieGameStats,
} from '../../src/api/index.js';
import { game } from './scoreboard.js';
export function skaterGameStats(overrides: Partial<SkaterGameStats> = {}): SkaterGameStats {
  return {
    goals: 0,
    assists: 1,
    points: 1,
    plus_minus: -1,
    penalty_minutes: 0,
    shots_on_goal: 2,
    hits: null,
    blocked_shots: 0,
    faceoffs_won: 4,
    pp_points: 0,
    sh_points: 0,
    toi_seconds: 754,
    pp_toi_seconds: 0,
    sh_toi_seconds: 95,
    ...overrides,
  };
}
export function goalieGameStats(overrides: Partial<GoalieGameStats> = {}): GoalieGameStats {
  return {
    decision: 'L',
    toi_seconds: 3600,
    goals_against: null,
    saves: 29,
    shots_against: 32,
    save_percentage: 0.90625,
    shutouts: 0,
    ...overrides,
  };
}
export function gamelogEntry(overrides: Partial<GamelogEntry> = {}): GamelogEntry {
  return {
    date: '2026-11-12',
    game: game(),
    side: 'away',
    team: { nhl_id: 10, abbr: 'TOR', name: 'Toronto Maple Leafs', slug: 'toronto' },
    opponent: { nhl_id: 8, abbr: 'MTL', name: 'Montreal Canadiens', slug: 'montreal' },
    game_position: 'C',
    sweater_number: 0,
    availability: 'partial',
    stats: skaterGameStats(),
    ...overrides,
  };
}
export function gamelog(
  query = new URLSearchParams(),
  overrides: Partial<GamelogResponse> = {},
): GamelogResponse {
  const goalie = query.get('player_type') === 'goalie';
  const emptyStats = goalie
    ? goalieGameStats({
        decision: null,
        toi_seconds: null,
        goals_against: null,
        saves: null,
        shots_against: null,
        save_percentage: null,
        shutouts: null,
      })
    : (Object.fromEntries(
        Object.keys(skaterGameStats()).map((key) => [key, null]),
      ) as SkaterGameStats);
  return {
    count: 3,
    next: null,
    previous: null,
    meta: {
      nhl_id: 8480001,
      player_type: goalie ? 'goalie' : 'skater',
      season_id: query.get('season_id'),
      date_min: query.get('date_min'),
      date_max: query.get('date_max'),
      ordering: query.get('ordering') || '-date',
    },
    results: [
      gamelogEntry(goalie ? { game_position: 'G', stats: goalieGameStats() } : {}),
      gamelogEntry({
        date: '2026-11-10',
        game: null,
        side: null,
        team: null,
        opponent: null,
        game_position: null,
        sweater_number: null,
        availability: 'unverified',
        stats: emptyStats,
      }),
      gamelogEntry({
        date: null,
        game: { ...game(), nhl_id: 2026020002, date: null },
        side: null,
        team: null,
        opponent: null,
        game_position: null,
        sweater_number: null,
        availability: 'missing',
        stats: emptyStats,
      }),
    ],
    ...overrides,
  };
}

export function gamelogGameDetail() {
  return gameDetail({
    rosters: {
      away: {
        forwards: [skater({ name: 'Profile Skater', stats: skaterGameStats() })],
        defencemen: [],
        goalies: [],
      },
      home: emptyRoster(),
    },
  });
}
