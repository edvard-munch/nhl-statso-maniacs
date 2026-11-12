import type {
  GameDetail,
  GameGoalie,
  GameRoster,
  GameSkater,
  GoalieGameStats,
  SkaterGameStats,
} from '../../src/api/index.js';
import { freshness, game } from './scoreboard.js';

export function skaterStats(overrides: Partial<SkaterGameStats> = {}): SkaterGameStats {
  return {
    goals: 1,
    assists: 0,
    points: 1,
    plus_minus: -2,
    penalty_minutes: 0,
    shots_on_goal: 4,
    hits: 0,
    blocked_shots: 1,
    faceoffs_won: 3,
    pp_points: 0,
    sh_points: 0,
    toi_seconds: 754,
    pp_toi_seconds: 0,
    sh_toi_seconds: 121,
    ...overrides,
  };
}
export function goalieStats(overrides: Partial<GoalieGameStats> = {}): GoalieGameStats {
  return {
    decision: 'W',
    toi_seconds: 3600,
    goals_against: 2,
    saves: 24,
    shots_against: 26,
    save_percentage: 0.923,
    shutouts: 0,
    ...overrides,
  };
}
export function skater(overrides: Partial<GameSkater> = {}): GameSkater {
  return {
    player_type: 'skater',
    nhl_id: 8480001,
    name: 'Alex Forward',
    last_name: 'Forward',
    slug: 'alex-forward',
    position_abbr: 'RW',
    game_position: 'C',
    sweater_number: 7,
    availability: 'complete',
    stats: skaterStats(),
    ...overrides,
  };
}
export function goalie(overrides: Partial<GameGoalie> = {}): GameGoalie {
  // Same numeric NHL ID as the skater deliberately exercises typed identity.
  return {
    player_type: 'goalie',
    nhl_id: 8480001,
    name: 'Jamie Goalie',
    last_name: 'Goalie',
    slug: 'jamie-goalie',
    position_abbr: 'G',
    game_position: 'G',
    sweater_number: 30,
    availability: 'complete',
    stats: goalieStats(),
    ...overrides,
  };
}
export function emptyRoster(): GameRoster {
  return { forwards: [], defencemen: [], goalies: [] };
}
export function gameDetail(overrides: Partial<GameDetail> = {}): GameDetail {
  return {
    ...game(),
    freshness: freshness({ partial: true }),
    rosters: {
      away: {
        forwards: [skater()],
        defencemen: [skater({ nhl_id: 8480002, name: 'Casey Defender', game_position: 'D' })],
        goalies: [goalie()],
      },
      home: emptyRoster(),
    },
    ...overrides,
  };
}
export function unknownSkaterStats(): SkaterGameStats {
  return {
    goals: null,
    assists: null,
    points: null,
    plus_minus: null,
    penalty_minutes: null,
    shots_on_goal: null,
    hits: null,
    blocked_shots: null,
    faceoffs_won: null,
    pp_points: null,
    sh_points: null,
    toi_seconds: null,
    pp_toi_seconds: null,
    sh_toi_seconds: null,
  };
}
