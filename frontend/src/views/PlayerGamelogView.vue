<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { ApiError, playerGamelogList, playerRetrieve, type GamelogResponse } from '../api/index.js';
import { AVAILABILITY_LABELS, numberLabel } from '../games/presentation.js';
import { FIRST_PAGE, seasonLabel } from '../players/catalogue.js';
import {
  GAME_FIELD_LABELS,
  GAME_PAGE_SIZES,
  gameFields,
  gameNumericFields,
  gameOrderingFields,
  gameStatisticLabel,
  parseGamelogQuery,
  profileReturn,
} from '../players/gamelog.js';
import { parsePlayerIdentity } from '../players/profile.js';
import { SAVED_READ_TIMEOUT_MS } from '../refresh/useSavedRefresh.js';
import { scheduleDateLabel, stateLabel } from '../scoreboard/presentation.js';

const route = useRoute();
const router = useRouter();
const identity = computed(() => parsePlayerIdentity(route.params.playerType, route.params.nhlId));
const back = computed(() =>
  identity.value ? profileReturn(route.query.returnTo, router, identity.value) : '/players',
);
const phase = ref<'loading' | 'ready' | 'error' | 'not-found'>('loading');
const result = shallowRef<GamelogResponse | null>(null);
const name = ref('');
const error = ref('');
const reference = ref<string | null>(null);
const draft = reactive<Record<string, string>>({});
const filtersOpen = ref(false);
const type = computed(() => identity.value?.player_type ?? 'skater');
const columns = computed(() => gameFields(type.value));
const numeric = computed(() => gameNumericFields(type.value));
const page = computed(() => Number(route.query.page || FIRST_PAGE));
let controller: AbortController | undefined;
function apply() {
  const query = Object.fromEntries(
    Object.entries(draft).filter(([key, value]) => key !== 'page' && value !== ''),
  );
  void router.push({
    name: 'player-gamelog',
    params: route.params,
    query: { ...query, returnTo: back.value },
  });
}
function clearFilters() {
  void router.push({
    name: 'player-gamelog',
    params: route.params,
    query: { returnTo: back.value },
  });
}
function choosePage(value: number) {
  void router.push({
    name: 'player-gamelog',
    params: route.params,
    query: { ...route.query, returnTo: back.value, page: String(value) },
  });
}
function sort(field: string) {
  const current = result.value?.meta.ordering.split(',')[0];
  void router.push({
    name: 'player-gamelog',
    params: route.params,
    query: {
      ...route.query,
      returnTo: back.value,
      page: undefined,
      ordering: current === `-${field}` ? field : `-${field}`,
    },
  });
}
function gameLink(id: number) {
  return { name: 'game-detail', params: { nhlId: id }, query: { gamelog: route.fullPath } };
}
async function load() {
  controller?.abort();
  const current = new AbortController();
  controller = current;
  let timedOut = false;
  let validated = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    current.abort();
  }, SAVED_READ_TIMEOUT_MS);
  phase.value = 'loading';
  result.value = null;
  name.value = '';
  reference.value = null;
  error.value = '';
  for (const key of Object.keys(draft)) delete draft[key];
  try {
    const path = identity.value;
    if (!path) {
      phase.value = 'not-found';
      return;
    }
    const query = parseGamelogQuery(route.query, path.player_type);
    validated = true;
    for (const [key, value] of Object.entries(query)) draft[key] = String(value);
    const [log, profile] = await Promise.all([
      playerGamelogList({ path, query, signal: current.signal }),
      // Only biography supplies the heading; profile defaults never choose gamelog scope.
      playerRetrieve({
        path,
        query: query.season_id ? { season_id: query.season_id } : {},
        signal: current.signal,
      }),
    ]);
    if (current.signal.aborted) return;
    result.value = log.data;
    name.value = profile.data.player.name;
    phase.value = 'ready';
  } catch (failure) {
    if (controller !== current || (current.signal.aborted && !timedOut)) return;
    current.abort();
    reference.value = failure instanceof ApiError ? failure.requestId : null;
    error.value =
      !validated && failure instanceof Error
        ? failure.message
        : failure instanceof ApiError && failure.response.status === 404
          ? 'This player or saved gamelog page is unavailable. Try the first page or change filters.'
          : 'Unable to load this saved gamelog. Please try again.';
    phase.value = 'error';
  } finally {
    clearTimeout(timeout);
  }
}
watch(
  () => route.fullPath,
  () => {
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());
</script>

<template>
  <section aria-labelledby="gamelog-title">
    <RouterLink class="action-link" :to="back">Back to player profile</RouterLink>
    <h1 id="gamelog-title">{{ name ? `${name} game log` : 'Player game log' }}</h1>
    <p v-if="phase === 'loading'" role="status">Loading saved gamelog…</p>
    <div v-else-if="phase === 'not-found'" role="alert" class="panel">
      <h2>Player not found</h2>
      <p>This typed player identity is unavailable.</p>
    </div>
    <div v-else-if="phase === 'error'" role="alert" class="panel">
      <p>{{ error }}</p>
      <p v-if="reference">Reference: {{ reference }}</p>
      <div class="button-row">
        <button type="button" @click="load()">Try again</button
        ><button v-if="page > FIRST_PAGE" type="button" @click="choosePage(FIRST_PAGE)">
          First page</button
        ><button type="button" @click="clearFilters">Clear filters</button>
      </div>
    </div>
    <template v-else-if="result">
      <p>
        {{ type === 'goalie' ? 'Goalie' : 'Skater' }} · NHL ID {{ identity?.nhl_id }} ·
        {{
          result.meta.season_id ? seasonLabel(result.meta.season_id) : 'All saved seasons and dates'
        }}
      </p>
      <p>
        Saved records, not current NHL observations. Availability concerns the player row; game
        state is separate. — means unknown, never zero. Unlinked rows do not establish team,
        opponent or game identity.
      </p>
      <form class="catalogue-form" @submit.prevent="apply">
        <div class="catalogue-controls">
          <label
            >Season ID (empty for all)<input
              v-model="draft.season_id"
              pattern="[0-9]{8}"
              placeholder="20262027"
          /></label>
          <label>Schedule date from<input v-model="draft.date_min" type="date" /></label>
          <label>Schedule date through<input v-model="draft.date_max" type="date" /></label>
          <label>Teams (comma-separated)<input v-model="draft.team" /></label>
          <label>Opponents (comma-separated)<input v-model="draft.opponent" /></label>
          <label
            >Ordering<input v-model="draft.ordering" list="gamelog-ordering" placeholder="-date"
          /></label>
          <datalist id="gamelog-ordering">
            <template v-for="field in gameOrderingFields(type)" :key="field"
              ><option :value="field">{{ GAME_FIELD_LABELS[field] }} ascending</option>
              <option :value="`-${field}`">
                {{ GAME_FIELD_LABELS[field] }} descending
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
          <summary>Statistic filters</summary>
          <p>
            Bounds use actual game TOI in seconds and save fractions (0–1). Prefix ordering with -
            for descending; comma-separated fields are supported. Filters and ordering apply before
            pagination.
          </p>
          <div class="catalogue-ranges">
            <fieldset v-for="field in numeric" :key="field">
              <legend>{{ GAME_FIELD_LABELS[field] }}</legend>
              <label
                >Minimum<input
                  :value="draft[`${field}_min`]"
                  type="number"
                  step="any"
                  :aria-label="`${GAME_FIELD_LABELS[field]} minimum`"
                  @input="draft[`${field}_min`] = ($event.target as HTMLInputElement).value"
              /></label>
              <label
                >Maximum<input
                  :value="draft[`${field}_max`]"
                  type="number"
                  step="any"
                  :aria-label="`${GAME_FIELD_LABELS[field]} maximum`"
                  @input="draft[`${field}_max`] = ($event.target as HTMLInputElement).value"
              /></label>
              <label
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
          ><button type="button" @click="clearFilters">Clear filters</button>
        </div>
      </form>
      <p>
        Showing {{ result.results.length }} of {{ result.count }} rows. Page {{ page }}. Ordering:
        {{ result.meta.ordering }}.
      </p>
      <p v-if="!result.results.length" role="status">No saved gamelog rows match this selection.</p>
      <div v-else class="table-scroll" role="region" aria-label="Saved player gamelog" tabindex="0">
        <table class="roster-table">
          <caption>
            Saved game statistics · actual TOI (mm:ss)
          </caption>
          <thead>
            <tr>
              <th scope="col">
                <button type="button" aria-label="Sort by Date" @click="sort('date')">
                  Date / game
                </button>
              </th>
              <th scope="col">Team</th>
              <th scope="col">Opponent</th>
              <th scope="col">Side</th>
              <th scope="col">Position / number</th>
              <th scope="col">Availability</th>
              <th scope="col">Saved game state</th>
              <th scope="col">Away / home score</th>
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
              :key="`${entry.game?.nhl_id ?? 'unlinked'}:${entry.date}:${index}`"
            >
              <th scope="row">
                <RouterLink v-if="entry.game" :to="gameLink(entry.game.nhl_id)"
                  >{{ entry.date ? scheduleDateLabel(entry.date, true) : 'Date unavailable' }} ·
                  Game {{ entry.game.nhl_id }}</RouterLink
                ><template v-else
                  >{{ entry.date ? scheduleDateLabel(entry.date, true) : 'Date unavailable' }} ·
                  Unlinked</template
                >
              </th>
              <td>{{ entry.team?.abbr ?? '—' }}</td>
              <td>{{ entry.opponent?.abbr ?? '—' }}</td>
              <td>{{ entry.side ?? '—' }}</td>
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
        aria-label="Gamelog pages"
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
