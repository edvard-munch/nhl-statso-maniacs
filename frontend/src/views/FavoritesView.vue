<script setup lang="ts">
import { computed, inject, reactive, ref, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { meFavoritesList } from '../api/index.js';
import FavoriteActionButton from '../components/FavoriteActionButton.vue';
import { favoriteActionsKey } from '../favorites/actions.js';
import { useSession } from '../auth/session.js';
import { usePrivateRead } from '../private/usePrivateRead.js';
import { AVAILABILITY_LABELS } from '../games/presentation.js';
import {
  FIELD_LABELS,
  FIRST_PAGE,
  SKATER_FIELDS,
  GOALIE_FIELDS,
  numericFields,
  orderFields,
  parseCatalogueQuery,
  seasonLabel,
} from '../players/catalogue.js';
import { profileStatisticLabel } from '../players/profile.js';

const PAGE_SIZES = [25, 50, 100];
const actions = inject(favoriteActionsKey, null);
const route = useRoute();
const router = useRouter();
const session = useSession();
const selection = computed(() => {
  try {
    return { query: parseCatalogueQuery(route.query), error: '' };
  } catch (failure) {
    return {
      query: null,
      error: failure instanceof Error ? failure.message : 'Choose a valid Favorites selection.',
    };
  }
});
const resource = usePrivateRead(session, {
  key: () => route.fullPath,
  valid: () => selection.value.query !== null,
  read: async (client, signal) =>
    (await meFavoritesList({ client, query: selection.value.query!, signal })).data,
});
const phase = resource.phase;
const result = resource.data;
const draft = reactive<Record<string, string>>({});
const filtersOpen = ref(false);
const type = computed(() => draft.player_type || 'skater');
const page = computed(() => Number(route.query.page || FIRST_PAGE));
const columns = computed(() =>
  result.value?.meta.player_type === 'goalie' ? GOALIE_FIELDS : SKATER_FIELDS,
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
watch(
  () => result.value?.meta.season_id,
  (season) => {
    if (resource.phase.value === 'ready' && route.query.season_id === undefined && season)
      void router.replace({ name: 'favorites', query: { ...route.query, season_id: season } });
  },
);
watch(
  [() => resource.phase.value, () => resource.httpStatus.value, () => actions?.notice.value],
  () => {
    const notice = actions?.notice.value;
    if (
      notice?.action === 'remove' &&
      notice.desiredObserved &&
      notice.owner === session.user.value?.id &&
      notice.revision === session.revision.value &&
      notice.source === route.fullPath &&
      resource.phase.value === 'error' &&
      resource.httpStatus.value === 404 &&
      page.value > FIRST_PAGE
    )
      void router.replace({
        name: 'favorites',
        query: { ...route.query, page: String(FIRST_PAGE) },
      });
  },
);
function apply() {
  void router.push({
    name: 'favorites',
    query: Object.fromEntries(
      Object.entries(draft).filter(([key, value]) => key !== 'page' && value !== ''),
    ),
  });
}
function clearFilters() {
  const query = selection.value.query;
  void router.push({
    name: 'favorites',
    query: {
      season_id: query?.season_id,
      player_type: query?.player_type || 'skater',
      mode: query?.mode || 'totals',
    },
  });
}
function changeType() {
  for (const key of Object.keys(draft))
    if (!['season_id', 'player_type', 'search', 'page_size'].includes(key)) delete draft[key];
  draft.mode = 'totals';
}
function choosePage(value: number) {
  void router.push({ name: 'favorites', query: { ...route.query, page: String(value) } });
}
function sort(field: string) {
  void router.push({
    name: 'favorites',
    query: {
      ...route.query,
      page: undefined,
      ordering: result.value?.meta.ordering.split(',')[0] === `-${field}` ? field : `-${field}`,
    },
  });
}
</script>

<template>
  <section aria-labelledby="favorites-title">
    <h1 id="favorites-title">Favorites</h1>
    <p v-if="phase === 'waiting'" role="status">Waiting for session checks…</p>
    <div v-else-if="phase === 'anonymous'" class="panel">
      <p>Sign in to view your saved Favorites.</p>
      <RouterLink class="action-link" :to="{ name: 'login', query: { returnTo: route.fullPath } }"
        >Sign in to view Favorites</RouterLink
      >
    </div>
    <p v-else-if="phase === 'session-error'" role="alert">
      Sign-in status is unavailable. Check your session above before loading Favorites.
    </p>
    <div v-else-if="phase === 'forbidden'" class="panel" role="alert">
      <p>Access to Favorites could not be confirmed. Check your session before trying again.</p>
      <p v-if="resource.reference.value">Reference: {{ resource.reference.value }}</p>
      <button type="button" :disabled="session.busy.value" @click="session.checkSession()">
        Check session
      </button>
    </div>
    <div v-else-if="phase === 'invalid' || phase === 'error'" role="alert" class="panel">
      <p>
        {{
          phase === 'invalid'
            ? selection.error
            : resource.httpStatus.value === 404
              ? 'This Favorites page is unavailable. Return to the first page or change filters.'
              : 'Unable to load saved Favorites. Please try again.'
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
    <p v-else-if="phase === 'loading'" role="status">Loading your Favorites…</p>
    <template v-else-if="phase === 'ready' && result">
      <p>
        Saved for {{ session.user.value?.username }}. Missing, unverified and zero-game season rows
        remain in your list unless excluded by a filter.
      </p>
      <p aria-label="Favorites quota">
        {{ result.meta.quota.total_count }} of {{ result.meta.quota.limit }} saved players ·
        {{ result.meta.quota.skaters_count }} skaters ·
        {{ result.meta.quota.goalies_count }} goalies · {{ result.meta.quota.remaining }} remaining.
        Quota counts both unfiltered groups.
      </p>
      <p v-if="result.meta.quota.over_limit" role="status">
        Your saved list is above the limit. Existing entries are retained.
      </p>
      <form class="catalogue-form" @submit.prevent="apply">
        <div class="catalogue-controls">
          <label
            >Season ID (empty for latest loaded)<input
              v-model="draft.season_id"
              pattern="[0-9]{8}"
              placeholder="20262027"
          /></label>
          <label
            >Player type<select v-model="draft.player_type" @change="changeType">
              <option value="skater">Skaters</option>
              <option value="goalie">Goalies</option>
            </select></label
          >
          <label
            >Statistics<select v-model="draft.mode">
              <option value="totals">Totals</option>
              <option v-if="type === 'skater'" value="averages">Per-game averages</option>
            </select></label
          >
          <label>Search player name<input v-model="draft.search" type="search" /></label>
          <label>Season teams (comma-separated)<input v-model="draft.team" /></label>
          <label>Positions (comma-separated)<input v-model="draft.position" /></label>
          <label>Nations (comma-separated)<input v-model="draft.nation" /></label>
          <label
            >Rookie<select
              :value="draft.rookie ?? ''"
              @change="draft.rookie = ($event.target as HTMLSelectElement).value"
            >
              <option value="">All</option>
              <option value="true">Rookies</option>
              <option value="false">Non-rookies</option>
            </select></label
          >
          <label
            >Ordering<input
              v-model="draft.ordering"
              list="favorite-ordering"
              placeholder="Default ordering" /></label
          ><datalist id="favorite-ordering">
            <template v-for="field in orderFields(type)" :key="field"
              ><option :value="field" />
              <option :value="`-${field}`"
            /></template>
          </datalist>
          <label
            >Page size<select v-model="draft.page_size">
              <option v-for="size in PAGE_SIZES" :key="size" :value="String(size)">
                {{ size }}
              </option>
              <option
                v-if="draft.page_size && !PAGE_SIZES.map(String).includes(draft.page_size)"
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
          <summary>Birth date and numeric filters</summary>
          <p>
            Codes and ordering are comma-separated; prefix ordering with - for descending. Numeric
            bounds exclude unknowns unless a missing-value filter selects them. TOI bounds use
            seconds and save-percentage bounds use fractions (0–1). Public Players facets do not
            describe your private population.
          </p>
          <div class="catalogue-controls">
            <label>Birth date from<input v-model="draft.birth_date_min" type="date" /></label
            ><label>Birth date through<input v-model="draft.birth_date_max" type="date" /></label>
          </div>
          <div class="catalogue-ranges">
            <fieldset v-for="field in numericFields(type)" :key="field">
              <legend>{{ FIELD_LABELS[field] }}</legend>
              <label
                >Minimum<input
                  :value="draft[`${field}_min`]"
                  type="number"
                  step="any"
                  :aria-label="`${FIELD_LABELS[field]} minimum`"
                  @input="
                    draft[`${field}_min`] = ($event.target as HTMLInputElement).value
                  " /></label
              ><label
                >Maximum<input
                  :value="draft[`${field}_max`]"
                  type="number"
                  step="any"
                  :aria-label="`${FIELD_LABELS[field]} maximum`"
                  @input="
                    draft[`${field}_max`] = ($event.target as HTMLInputElement).value
                  " /></label
              ><label
                >Availability<select
                  :value="draft[`${field}_isnull`] ?? ''"
                  :aria-label="`${FIELD_LABELS[field]} availability`"
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
          <button type="submit">Apply selections</button
          ><button type="button" @click="clearFilters">Clear filters</button
          ><button type="button" @click="resource.reload()">Refresh Favorites</button>
        </div>
      </form>
      <nav aria-label="Favorites game logs">
        <RouterLink
          v-if="result.meta.season_id"
          class="action-link"
          :to="{
            name: 'favorite-gamelog',
            query: {
              player_type: result.meta.player_type,
              season_id: result.meta.season_id || undefined,
              returnTo: route.fullPath,
            },
          }"
          >Selected-season Favorites game log</RouterLink
        >
        <RouterLink
          class="action-link"
          :to="{
            name: 'favorite-gamelog',
            query: { player_type: result.meta.player_type, returnTo: route.fullPath },
          }"
          >All saved Favorite games</RouterLink
        >
      </nav>
      <h2>
        {{ result.meta.season_id ? seasonLabel(result.meta.season_id) : 'No loaded season' }} ·
        {{ result.meta.player_type === 'goalie' ? 'Goalies' : 'Skaters' }} ·
        {{ result.meta.mode === 'averages' ? 'Per-game averages' : 'Totals' }}
      </h2>
      <p>
        No reliable player refresh timestamp is available. — means unknown, never zero; season teams
        describe participation, not a reconstructed roster.
      </p>
      <p>
        Showing {{ result.results.length }} of {{ result.count }} matches. Page {{ page }}.
        Ordering: {{ result.meta.ordering }}.
      </p>
      <p v-if="!result.results.length" role="status">
        {{
          result.meta.quota.total_count === 0
            ? 'No saved Favorites yet.'
            : 'No Favorites match this type and selection.'
        }}
      </p>
      <div
        v-else
        class="table-scroll"
        role="region"
        aria-label="Favorite season statistics"
        tabindex="0"
      >
        <table class="roster-table">
          <caption>
            Favorite season statistics<template v-if="result.meta.player_type === 'skater'">
              · TOI per game (mm:ss)</template
            >
          </caption>
          <thead>
            <tr>
              <th scope="col">Player</th>
              <th scope="col">Actions</th>
              <th scope="col">Season teams</th>
              <th scope="col">Position</th>
              <th scope="col">Nation</th>
              <th scope="col">Availability</th>
              <th
                v-for="field in columns"
                :key="field"
                scope="col"
                :aria-sort="
                  result.meta.ordering.split(',')[0] === field
                    ? 'ascending'
                    : result.meta.ordering.split(',')[0] === `-${field}`
                      ? 'descending'
                      : undefined
                "
              >
                <button
                  type="button"
                  :aria-label="`Sort by ${FIELD_LABELS[field]}`"
                  @click="sort(field)"
                >
                  {{
                    field === 'save_percentage'
                      ? 'Save %'
                      : (FIELD_LABELS[field] || field).replace(' (seconds)', '')
                  }}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="player in result.results" :key="`${player.player_type}:${player.nhl_id}`">
              <th scope="row">
                <RouterLink
                  :to="{
                    name: 'player-profile',
                    params: { playerType: player.player_type, nhlId: player.nhl_id },
                    query: {
                      season_id: result.meta.season_id || undefined,
                      mode: result.meta.mode,
                      returnTo: route.fullPath,
                    },
                  }"
                  >{{ player.name }}</RouterLink
                >
              </th>
              <td>
                <FavoriteActionButton
                  action="remove"
                  :player-type="player.player_type"
                  :nhl-id="player.nhl_id"
                  :name="player.name"
                />
              </td>
              <td>{{ player.teams.map((team) => team.abbr).join(', ') || '—' }}</td>
              <td>{{ player.position_abbr || '—' }}</td>
              <td>{{ player.nation_abbr || '—' }}</td>
              <td>{{ AVAILABILITY_LABELS[player.availability] }}</td>
              <td v-for="field in columns" :key="field">
                {{ profileStatisticLabel(player.stats, field) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav
        v-if="result.next || result.previous"
        class="button-row pagination"
        aria-label="Favorites pages"
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
