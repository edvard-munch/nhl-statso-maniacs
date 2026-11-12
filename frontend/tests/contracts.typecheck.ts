/** Compiled by tsc; never executed. These assertions exercise the actual generated contract. */
import { expectTypeOf } from 'vitest';
import {
  authLoginCreate,
  meAccountImagePut,
  meAccountPatch,
  meFavoriteDelete,
  meFavoritesGamelogList,
  playerRetrieve,
  playersList,
} from '../src/api/generated/sdk.js';
import type {
  CataloguePlayer,
  CatalogueSeasonStatistics,
  ErrorResponse,
  SavedGameState,
  PlayersResponse,
} from '../src/api/generated/types.js';
import type { ApiClient } from '../src/api/http.js';

export function compileContract(
  api: ApiClient,
  stats: CatalogueSeasonStatistics,
  state: SavedGameState,
) {
  // A known null is preserved; wire dates stay strings rather than becoming Date objects.
  expectTypeOf<CataloguePlayer['height_cm']>().toEqualTypeOf<number | null>();
  expectTypeOf<CataloguePlayer['birth_date']>().toEqualTypeOf<string>();
  expectTypeOf<SavedGameState['observed_at']>().toEqualTypeOf<string | null>();
  expectTypeOf(state.value).toEqualTypeOf<'unknown' | 'live' | 'final'>();
  if (stats.kind === 'goalie_totals') {
    expectTypeOf(stats.wins).toEqualTypeOf<number | null>();
    // @ts-expect-error Skater fields cannot be read from the goalie variant.
    void stats.goals;
  } else {
    expectTypeOf(stats.goals).toEqualTypeOf<number | null>();
    // @ts-expect-error Goalie fields cannot be read from a skater variant.
    void stats.wins;
  }
  expectTypeOf<Awaited<ReturnType<typeof meFavoriteDelete>>['data']>().toEqualTypeOf<undefined>();
  expectTypeOf<
    Awaited<ReturnType<typeof playersList<true>>>['data']
  >().toEqualTypeOf<PlayersResponse>();
  expectTypeOf<Awaited<ReturnType<typeof playersList<false>>>['error']>().toEqualTypeOf<
    ErrorResponse | undefined
  >();

  // Transport-owned CSRF headers are optional at the call site, other required inputs are not.
  authLoginCreate({ client: api, body: { username: 'name', password: 'secret' } });
  meAccountImagePut({ client: api, body: { image: new Blob(['image']) } });
  meAccountPatch({ client: api, body: { measurements_format: 'Europe' } });
  meFavoritesGamelogList({
    client: api,
    query: { player_type: 'goalie', ordering: 'player_name,-date' },
  });
  playersList({ client: api, query: { mode: 'averages', hits_isnull: true, points_min: 0 } });
  // @ts-expect-error Login requires a password.
  authLoginCreate({ client: api, body: { username: 'name' } });
  // @ts-expect-error Binary input is a Blob/File, not a filesystem path or URL.
  meAccountImagePut({ client: api, body: { image: '/tmp/avatar.png' } });
  // @ts-expect-error Typed NHL IDs remain numeric.
  playerRetrieve({ client: api, path: { player_type: 'skater', nhl_id: '8482076' } });
  // @ts-expect-error Public player types remain a literal union.
  playerRetrieve({ client: api, path: { player_type: 'forward', nhl_id: 8482076 } });
  // @ts-expect-error Invalid enum modes must fail compilation.
  playersList({ client: api, query: { mode: 'career' } });
  // @ts-expect-error Unknown body fields cannot be smuggled into account changes.
  meAccountPatch({ client: api, body: { is_staff: true } });
  // @ts-expect-error Wire query dates remain strings.
  meFavoritesGamelogList({ client: api, query: { date_min: new Date() } });
}
