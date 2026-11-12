import type { HistoryResponse, PlayerProfile, ProfileStatistics } from '../../src/api/index.js';
import { player } from './players.js';

export function profileStats(overrides: Partial<ProfileStatistics> = {}): ProfileStatistics {
  return { ...player().stats, ...overrides } as ProfileStatistics;
}
export function profile(
  query = new URLSearchParams(),
  overrides: Partial<PlayerProfile> = {},
): PlayerProfile {
  const goalie = query.get('player_type') === 'goalie';
  const mode = query.get('mode') === 'averages' ? 'averages' : 'totals';
  const goalieStats: ProfileStatistics = {
    kind: 'goalie_totals',
    games: 2,
    wins: 0,
    losses: 1,
    ot_losses: null,
    saves: 45,
    shutouts: 0,
    goals_against_average: null,
    save_percentage: 0.915,
  };
  const stats = goalie
    ? goalieStats
    : profileStats(
        mode === 'averages' ? { kind: 'skater_averages', goals: 0.5, points: 1.25 } : {},
      );
  return {
    player: {
      ...player(),
      player_type: goalie ? 'goalie' : 'skater',
      name: goalie ? 'Profile Goalie' : 'Profile Skater',
      first_name: 'Profile',
      birth_city: 'Toronto',
      birth_state: 'Ontario',
      birth_country: 'Canada',
      birth_country_abbr: 'CAN',
      jersey_number: 0,
      draft_round: null,
      nhl_debut: '',
      roster_status: 'N',
      captain: false,
      alternate_captain: true,
      video_url: '',
    },
    meta: {
      player_type: goalie ? 'goalie' : 'skater',
      season_id: query.get('season_id') || '20262027',
      mode,
    },
    current_team: { nhl_id: 7, abbr: 'BUF', name: 'Buffalo Sabres', slug: 'buffalo' },
    selected_season: { availability: 'partial', stats },
    career_totals: {
      availability: 'partial',
      stats: goalie ? goalieStats : profileStats({ games: 100, goals: 45, points: 120 }),
    },
    career_averages: goalie
      ? null
      : {
          availability: 'partial',
          stats: profileStats({ kind: 'skater_averages', games: 100, goals: 0.45, points: 1.2 }),
        },
    seasons_url: 'https://not-followed.example/history',
    gamelog_url: 'https://not-followed.example/log',
    ...overrides,
  };
}
export function seasonHistory(
  query = new URLSearchParams(),
  overrides: Partial<HistoryResponse> = {},
): HistoryResponse {
  const goalie = query.get('player_type') === 'goalie';
  const mode = query.get('mode') === 'averages' ? 'averages' : 'totals';
  const stats = profile(query).selected_season.stats;
  return {
    count: 2,
    next: null,
    previous: null,
    meta: { nhl_id: 8480001, player_type: goalie ? 'goalie' : 'skater', mode },
    results: [
      {
        season_id: '20262027',
        availability: 'partial',
        stats,
        contributions: [
          {
            team: { nhl_id: 7, abbr: 'BUF', name: 'Buffalo Sabres', slug: 'buffalo' },
            availability: 'unverified',
            stats: null,
          },
          {
            team: { nhl_id: null, abbr: 'OLD', name: 'OLD', slug: null },
            availability: 'partial',
            stats,
          },
        ],
      },
      {
        season_id: '20252026',
        availability: 'partial',
        stats: goalie
          ? ({
              ...profile(query).selected_season.stats!,
              kind: 'goalie_totals',
              games: 0,
              wins: 0,
            } as ProfileStatistics)
          : profileStats({ games: 0, goals: 0, points: null }),
        contributions: [],
      },
    ],
    ...overrides,
  };
}
