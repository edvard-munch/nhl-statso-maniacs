<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { meFavoritesGamelogList } from '../api/index.js';
import { useSession } from '../auth/session.js';
import { usePrivateRead } from '../private/usePrivateRead.js';
import { AVAILABILITY_LABELS, numberLabel } from '../games/presentation.js';
import { FIRST_PAGE, seasonLabel } from '../players/catalogue.js';
import {
  GAME_FIELD_LABELS,
  GAME_PAGE_SIZES,
  gameFields,
  gameNumericFields,
  gameStatisticLabel,
} from '../players/gamelog.js';
import { stateLabel } from '../scoreboard/presentation.js';
import { favoritesReturn } from '../favorites/navigation.js';
import {
  FAVORITE_GAME_LABELS,
  favoriteGameOrderingFields,
  parseFavoriteGamelogQuery,
} from '../favorites/gamelog.js';

const route = useRoute();
const router = useRouter();
const session = useSession();
const selection = computed(() => {
  try {
    return { query: parseFavoriteGamelogQuery(route.query), error: '' };
  } catch (failure) {
    return {
      query: null,
      error:
        failure instanceof Error ? failure.message : 'Choose a valid Favorites gamelog selection.',
    };
  }
});
const resource = usePrivateRead(session, {
  key: () => route.fullPath,
  valid: () => selection.value.query !== null,
  read: async (client, signal) =>
    (await meFavoritesGamelogList({ client, query: selection.value.query!, signal })).data,
});
const phase = resource.phase;
const result = resource.data;
const draft = reactive<Record<string, string>>({});
const filtersOpen = ref(false);
const type = computed(() => draft.player_type || 'skater');
const columns = computed(() => gameFields(result.value?.meta.player_type || 'skater'));
const page = computed(() => Number(route.query.page || FIRST_PAGE));
const back = computed(
  () =>
    favoritesReturn(route.query.returnTo, router) ??
    router.resolve({
      name: 'favorites',
      query: {
        player_type: selection.value.query?.player_type || 'skater',
        season_id: selection.value.query?.season_id,
      },
    }).fullPath,
);
watch(
  () => route.fullPath,
  () => {
    for (const key of Object.keys(draft)) delete draft[key];
    for (const [key, value] of Object.entries(selection.value.query ?? {}))
      draft[key] = String(value);
  },
  { immediate: true },
);
function apply() {
  void router.push({
    name: 'favorite-gamelog',
    query: {
      ...Object.fromEntries(
        Object.entries(draft).filter(([key, value]) => key !== 'page' && value !== ''),
      ),
      returnTo: back.value,
    },
  });
}
function clearFilters() {
  void router.push({
    name: 'favorite-gamelog',
    query: { player_type: selection.value.query?.player_type || 'skater', returnTo: back.value },
  });
}
function changeType() {
  for (const key of Object.keys(draft))
    if (
      ![
        'season_id',
        'player_type',
        'search',
        'date_min',
        'date_max',
        'team',
        'opponent',
        'page_size',
      ].includes(key)
    )
      delete draft[key];
}
function choosePage(value: number) {
  void router.push({
    name: 'favorite-gamelog',
    query: { ...route.query, page: String(value), returnTo: back.value },
  });
}
function sort(field: string) {
  void router.push({
    name: 'favorite-gamelog',
    query: {
      ...route.query,
      returnTo: back.value,
      page: undefined,
      ordering: result.value?.meta.ordering.split(',')[0] === `-${field}` ? field : `-${field}`,
    },
  });
}
function sortState(field: string) {
  const primary = result.value?.meta.ordering.split(',')[0];
  return primary === field ? 'ascending' : primary === `-${field}` ? 'descending' : undefined;
}
</script>

<template>
  <section aria-labelledby="favorite-gamelog-title">
    <RouterLink class="action-link" :to="back">Back to Favorites</RouterLink>
    <h1 id="favorite-gamelog-title">Favorites game log</h1>
    <p v-if="phase === 'waiting'" role="status">Waiting for session checks…</p>
    <div v-else-if="phase === 'anonymous'" class="panel">
      <p>Sign in to view your Favorites game log.</p>
      <RouterLink class="action-link" :to="{ name: 'login', query: { returnTo: route.fullPath } }"
        >Sign in to view Favorites gamelog</RouterLink
      >
    </div>
    <p v-else-if="phase === 'session-error'" role="alert">
      Sign-in status is unavailable. Check your session above before loading the Favorites game log.
    </p>
    <div v-else-if="phase === 'forbidden'" class="panel" role="alert">
      <p>
        Access to the Favorites game log could not be confirmed. Check your session before trying
        again.
      </p>
      <p v-if="resource.reference.value">Reference: {{ resource.reference.value }}</p>
      <button type="button" :disabled="session.busy.value" @click="session.checkSession()">
        Check session
      </button>
    </div>
    <div v-else-if="phase === 'invalid' || phase === 'error'" class="panel" role="alert">
      <p>
        {{
          phase === 'invalid'
            ? selection.error
            : resource.httpStatus.value === 404
              ? 'This Favorites gamelog page is unavailable. Return to the first page or change filters.'
              : 'Unable to load saved Favorites game rows. Please try again.'
        }}
      </p>
      <p v-if="resource.reference.value">Reference: {{ resource.reference.value }}</p>
      <div class="button-row">
        <button v-if="phase === 'error'" type="button" @click="resource.reload()">Try again</button
        ><button v-if="page > FIRST_PAGE" type="button" @click="choosePage(FIRST_PAGE)">
          First page</button
        ><button type="button" @click="clearFilters">Clear filters</button>
      </div>
    </div>
    <p v-else-if="phase === 'loading'" role="status">Loading Favorite game rows…</p>
    <template v-else-if="phase === 'ready' && result">
      <p>
        Saved for {{ session.user.value?.username }}. Each row belongs to one typed favorite player;
        two favorites in the same game produce separate rows.
      </p>
      <p aria-label="Favorites gamelog quota">
        {{ result.meta.quota.total_count }} of {{ result.meta.quota.limit }} saved players ·
        {{ result.meta.quota.skaters_count }} skaters ·
        {{ result.meta.quota.goalies_count }} goalies · {{ result.meta.quota.remaining }} remaining.
        Quota counts both unfiltered groups, not game rows.
      </p>
      <p v-if="result.meta.quota.over_limit" role="status">
        Your saved list is above the limit. Existing entries are retained.
      </p>
      <form class="catalogue-form" @submit.prevent="apply">
        <div class="catalogue-controls">
          <label
            >Player type<select v-model="draft.player_type" @change="changeType">
              <option value="skater">Skaters</option>
              <option value="goalie">Goalies</option>
            </select></label
          >
          <label
            >Season ID (empty for all saved)<input
              v-model="draft.season_id"
              pattern="[0-9]{8}"
              placeholder="20262027"
          /></label>
          <label>Search favorite player name<input v-model="draft.search" type="search" /></label>
          <label>Schedule date from<input v-model="draft.date_min" type="date" /></label>
          <label>Schedule date through<input v-model="draft.date_max" type="date" /></label>
          <label>Teams (comma-separated)<input v-model="draft.team" /></label>
          <label>Opponents (comma-separated)<input v-model="draft.opponent" /></label>
          <label
            >Ordering<input
              v-model="draft.ordering"
              list="favorite-gamelog-ordering"
              placeholder="-date" /></label
          ><datalist id="favorite-gamelog-ordering">
            <template v-for="field in favoriteGameOrderingFields(type)" :key="field"
              ><option :value="field">
                {{ FAVORITE_GAME_LABELS[field] || GAME_FIELD_LABELS[field] }} ascending
              </option>
              <option :value="`-${field}`">
                {{ FAVORITE_GAME_LABELS[field] || GAME_FIELD_LABELS[field] }} descending
              </option></template
            >
          </datalist>
          <label
            >Page size<select v-model="draft.page_size">
              <option v-for="size in GAME_PAGE_SIZES" :key="size" :value="String(size)">
                {{ size }}
              </option>
              <option
                v-if="draft.page_size && !GAME_PAGE_SIZES.map(String).includes(draft.page_size)"
                :value="draft.page_size"
              >
                {{ draft.page_size }}
              </option>
            </select></label
          >
        </div>
        <details
          :open="filtersOpen"
          @toggle="filtersOpen = ($event.target as HTMLDetailsElement).open"
        >
          <summary>Game statistic filters</summary>
          <p>
            Bounds use actual game TOI in seconds and save fractions (0–1). Name/game ordering is
            applied globally before pagination; comma-separated fields and - descending are
            supported. No choices or ranges are inferred from a single page.
          </p>
          <div class="catalogue-ranges">
            <fieldset v-for="field in gameNumericFields(type)" :key="field">
              <legend>{{ GAME_FIELD_LABELS[field] }}</legend>
              <label
                >Minimum<input
                  :value="draft[`${field}_min`]"
                  type="number"
                  step="any"
                  :aria-label="`${GAME_FIELD_LABELS[field]} minimum`"
                  @input="
                    draft[`${field}_min`] = ($event.target as HTMLInputElement).value
                  " /></label
              ><label
                >Maximum<input
                  :value="draft[`${field}_max`]"
                  type="number"
                  step="any"
                  :aria-label="`${GAME_FIELD_LABELS[field]} maximum`"
                  @input="
                    draft[`${field}_max`] = ($event.target as HTMLInputElement).value
                  " /></label
              ><label
                >Availability<select
                  :value="draft[`${field}_isnull`] ?? ''"
                  :aria-label="`${GAME_FIELD_LABELS[field]} availability`"
                  @change="draft[`${field}_isnull`] = ($event.target as HTMLSelectElement).value"
                >
                  <option value="">Any</option>
                  <option value="true">Missing</option>
                  <option value="false">Known</option>
                </select></label
              >
            </fieldset>
          </div>
        </details>
        <div class="button-row">
          <button type="submit">Apply filters</button
          ><button type="button" @click="clearFilters">Clear filters</button
          ><button type="button" @click="resource.reload()">Refresh gamelog</button>
        </div>
      </form>
      <h2>
        {{
          result.meta.season_id ? seasonLabel(result.meta.season_id) : 'All saved seasons and dates'
        }}
        · {{ result.meta.player_type === 'goalie' ? 'Goalies' : 'Skaters' }}
      </h2>
      <p>
        Saved game records. Player-row availability is separate from game-state evidence; unknown
        values stay —, while genuine zeros stay zero. Game position/number never fall back to
        current profile data.
      </p>
      <p>
        Showing {{ result.results.length }} of {{ result.count }} saved player-game rows. Page
        {{ page }}. Ordering: {{ result.meta.ordering }}.
      </p>
      <p v-if="!result.results.length" role="status">
        {{
          result.meta.quota.total_count === 0
            ? 'No saved Favorites yet.'
            : 'No Favorite game rows match this selection. Players without game rows remain in Favorites.'
        }}
      </p>
      <div
        v-else
        class="table-scroll"
        role="region"
        aria-label="Favorites game statistics"
        tabindex="0"
      >
        <table class="roster-table">
          <caption>
            Saved Favorite player-game rows · actual game TOI (mm:ss)
          </caption>
          <thead>
            <tr>
              <th scope="col" :aria-sort="sortState('player_name')">
                <button type="button" aria-label="Sort by Player name" @click="sort('player_name')">
                  Player
                </button>
              </th>
              <th scope="col" :aria-sort="sortState('date')">
                <button type="button" aria-label="Sort by Date" @click="sort('date')">
                  Date / game
                </button>
              </th>
              <th scope="col">Team</th>
              <th scope="col">Opponent</th>
              <th scope="col">Side</th>
              <th scope="col">Current position</th>
              <th scope="col">Game position / number</th>
              <th scope="col">Availability</th>
              <th scope="col">Saved game state</th>
              <th scope="col">Away / home score</th>
              <th v-for="field in columns" :key="field" scope="col" :aria-sort="sortState(field)">
                <button
                  type="button"
                  :aria-label="`Sort by ${GAME_FIELD_LABELS[field]}`"
                  @click="sort(field)"
                >
                  {{
                    field === 'save_percentage'
                      ? 'Save %'
                      : (GAME_FIELD_LABELS[field] || field).replace(' (seconds)', '')
                  }}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(entry, index) in result.results"
              :key="`${entry.player.player_type}:${entry.player.nhl_id}:${entry.game?.nhl_id ?? 'unlinked'}:${entry.date}:${index}`"
            >
              <th scope="row">
                <RouterLink
                  :to="{
                    name: 'player-profile',
                    params: { playerType: entry.player.player_type, nhlId: entry.player.nhl_id },
                    query: {
                      season_id: result.meta.season_id || undefined,
                      returnTo: route.fullPath,
                    },
                  }"
                  >{{ entry.player.name || `NHL player ${entry.player.nhl_id}` }}</RouterLink><span
                  class="side-label"
                  >{{ entry.player.player_type === 'goalie' ? 'Goalie' : 'Skater' }} · NHL ID
                  {{ entry.player.nhl_id }}</span
                >
              </th>
              <td>
                <RouterLink
                  v-if="entry.game"
                  :to="{
                    name: 'game-detail',
                    params: { nhlId: entry.game.nhl_id },
                    query: { favoriteLog: route.fullPath },
                  }"
                  >{{ entry.date || 'Date unavailable' }} · Game {{ entry.game.nhl_id }}</RouterLink
                ><template v-else>{{ entry.date || 'Date unavailable' }} · Unlinked</template>
              </td>
              <td>{{ entry.team?.abbr ?? '—' }}</td>
              <td>{{ entry.opponent?.abbr ?? '—' }}</td>
              <td>{{ entry.side ?? '—' }}</td>
              <td>{{ entry.player.position_abbr || '—' }}</td>
              <td>{{ entry.game_position ?? '—' }} / {{ entry.sweater_number ?? '—' }}</td>
              <td>{{ AVAILABILITY_LABELS[entry.availability] }}</td>
              <td>{{ entry.game ? stateLabel(entry.game.state) : 'Unlinked' }}</td>
              <td>
                {{
                  entry.game
                    ? `${numberLabel(entry.game.away_score)} / ${numberLabel(entry.game.home_score)}`
                    : '—'
                }}
              </td>
              <td v-for="field in columns" :key="field">
                {{ gameStatisticLabel(entry.stats, field) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav
        v-if="result.next || result.previous"
        class="button-row pagination"
        aria-label="Favorites gamelog pages"
      >
        <button type="button" :disabled="!result.previous" @click="choosePage(page - 1)">
          Previous page</button
        ><button type="button" :disabled="!result.next" @click="choosePage(page + 1)">
          Next page
        </button>
      </nav>
    </template>
  </section>
</template>
