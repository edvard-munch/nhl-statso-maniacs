import type {
  Team,
  TeamDetail,
  TeamsResponse,
  TeamPlayersResponse,
  TeamPlayer,
} from '../../src/api/index.js';
import { player } from './players.js';
export function team(overrides: Partial<Team> = {}): Team {
  return {
    nhl_id: 7,
    name: 'Buffalo Sabres',
    abbr: 'BUF',
    slug: 'buffalo',
    image_url: null,
    arena_name: 'Saved Arena',
    arena_location: 'Buffalo',
    conference: 'Eastern',
    division: 'Atlantic',
    website_url: 'https://example.com/team',
    nhl_debut: '1970',
    ...overrides,
  };
}
export function teams(
  query = new URLSearchParams(),
  overrides: Partial<TeamsResponse> = {},
): TeamsResponse {
  return {
    count: 2,
    next: null,
    previous: null,
    meta: { ordering: query.get('ordering') || 'name,nhl_id' },
    results: [
      team(),
      team({
        nhl_id: 27,
        name: 'Historical Team',
        abbr: 'HIS',
        conference: '',
        division: '',
        arena_name: '',
        website_url: '',
        nhl_debut: '',
      }),
    ],
    ...overrides,
  };
}
export function teamDetail(
  query = new URLSearchParams(),
  overrides: Partial<TeamDetail> = {},
): TeamDetail {
  return {
    team: team(),
    meta: { season_id: query.get('season_id') || '20262027' },
    players_url: 'https://not-followed.example/team-players',
    ...overrides,
  };
}
export function teamPlayer(query = new URLSearchParams()): TeamPlayer {
  const base = player();
  if (base.stats.kind === 'goalie_totals') throw new Error('Expected skater fixture');
  const goalie = query.get('player_type') === 'goalie';
  const averages = query.get('mode') === 'averages';
  return {
    ...base,
    name: goalie ? 'Split Goalie' : 'Traded Skater',
    player_type: goalie ? 'goalie' : 'skater',
    position_abbr: goalie ? 'G' : 'C',
    jersey_number: 0,
    teams: [{ nhl_id: 7, abbr: 'BUF', name: 'Buffalo Sabres', slug: 'buffalo' }],
    stats: goalie
      ? {
          kind: 'goalie_totals',
          games: 3,
          wins: 1,
          losses: 1,
          ot_losses: null,
          saves: 60,
          shutouts: 0,
          goals_against_average: null,
          save_percentage: 0.9,
        }
      : {
          ...base.stats,
          kind: averages ? 'skater_averages' : 'skater_totals',
          games: 6,
          goals: averages ? 0.5 : 3,
          points: averages ? 0.67 : 4,
          assists: averages ? 0.17 : 1,
          plus_minus: averages ? -0.17 : -1,
          shots_on_goal: averages ? 1.5 : 9,
          faceoffs_won: averages ? 2 : 12,
          avg_toi_seconds: 1111,
          avg_pp_toi_seconds: 0,
          avg_sh_toi_seconds: null,
        },
  };
}
export function teamPlayers(
  query = new URLSearchParams(),
  overrides: Partial<TeamPlayersResponse> = {},
): TeamPlayersResponse {
  return {
    count: 1,
    next: null,
    previous: null,
    meta: {
      season_id: query.get('season_id') || '20262027',
      player_type: query.get('player_type') === 'goalie' ? 'goalie' : 'skater',
      mode: query.get('mode') === 'averages' ? 'averages' : 'totals',
      ordering:
        query.get('ordering') ||
        (query.get('player_type') === 'goalie'
          ? '-wins,last_name,nhl_id'
          : '-points,last_name,nhl_id'),
      team: { nhl_id: 7, name: 'Buffalo Sabres', abbr: 'BUF', slug: 'buffalo' },
    },
    results: [teamPlayer(query)],
    ...overrides,
  };
}
