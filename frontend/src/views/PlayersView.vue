<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue';
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router';
import {
  ApiError,
  playersList,
  playersFiltersRetrieve,
  seasonsList,
  type PlayersResponse,
  type PlayersFiltersResponse,
  type Season,
} from '../api/index.js';
import { SAVED_READ_TIMEOUT_MS } from '../refresh/useSavedRefresh.js';
import {
  FIELD_LABELS,
  FIRST_PAGE,
  METADATA_PAGE_SIZE,
  SKATER_FIELDS,
  GOALIE_FIELDS,
  numericFields,
  orderFields,
  parseCatalogueQuery,
  seasonLabel,
  statisticLabel,
  isSeason,
} from '../players/catalogue.js';

const route = useRoute();
const router = useRouter();
const phase = ref<'loading' | 'ready' | 'error'>('loading');
const filtersOpen = ref(false);
const error = ref('');
const reference = ref<string | null>(null);
const result = shallowRef<PlayersResponse | null>(null);
const filters = shallowRef<PlayersFiltersResponse | null>(null);
const seasons = shallowRef<Season[]>([]);
const defaultSeasonId = ref<string | null>(null);
const PAGE_SIZE_CHOICES = [25, 50, 100];
const draft = reactive<Record<string, string>>({});
let seasonsLoaded = false;
let controller: AbortController | undefined;
const type = computed(() => draft.player_type || 'skater');
const fields = computed(() => numericFields(type.value));
const columns = computed(() =>
  result.value?.meta.player_type === 'goalie' ? GOALIE_FIELDS : SKATER_FIELDS,
);
const page = computed(() => Number(route.query.page || FIRST_PAGE));
const selectedSeason = computed(() =>
  typeof route.query.season_id === 'string' ? route.query.season_id : '',
);
const seasonOptions = computed(() =>
  selectedSeason.value && !seasons.value.some((season) => season.season_id === selectedSeason.value)
    ? [
        {
          season_id: selectedSeason.value,
          label: `${seasonLabel(selectedSeason.value)} (no loaded rows)`,
        },
        ...seasons.value,
      ]
    : seasons.value,
);
const categories = computed(() => [
  {
    key: 'team',
    label: 'Season teams',
    options:
      filters.value?.options.teams.map((team) => ({ code: team.abbr, label: team.name })) ?? [],
  },
  { key: 'position', label: 'Positions', options: filters.value?.options.positions ?? [] },
  { key: 'nation', label: 'Nations', options: filters.value?.options.nations ?? [] },
]);
function selected(key: string) {
  return (draft[key] || '').split(',').filter(Boolean);
}
function toggle(key: string, code: string, checked: boolean) {
  const values = new Set(selected(key));
  if (checked) values.add(code);
  else values.delete(code);
  draft[key] = [...values].sort().join(',');
}
function changeType() {
  draft.mode = 'totals';
  // Type-specific filters/order must not leak into the other statistics contract.
  for (const key of Object.keys(draft))
    if (
      key !== 'season_id' &&
      key !== 'player_type' &&
      key !== 'mode' &&
      key !== 'search' &&
      key !== 'page_size'
    )
      delete draft[key];
}
function apply() {
  const query = Object.fromEntries(
    Object.entries(draft).filter(([key, value]) => value && key !== 'page'),
  );
  void router.push({ name: 'players', query });
}
function clearFilters() {
  void router.push({
    name: 'players',
    query: {
      season_id: isSeason(selectedSeason.value) ? selectedSeason.value : undefined,
      player_type: type.value,
      mode: draft.mode,
    },
  });
}
function choosePage(value: number) {
  void router.push({
    name: 'players',
    query: { ...route.query, page: String(value) } as LocationQueryRaw,
  });
}
async function load() {
  controller?.abort();
  const current = new AbortController();
  controller = current;
  let validated = false;
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    current.abort();
  }, SAVED_READ_TIMEOUT_MS);
  phase.value = 'loading';
  result.value = null;
  filters.value = null;
  error.value = '';
  reference.value = null;
  for (const key of Object.keys(draft)) delete draft[key];
  try {
    const query = parseCatalogueQuery(route.query);
    validated = true;
    for (const [key, value] of Object.entries(query)) draft[key] = String(value);
    if (!seasonsLoaded) {
      const loaded: Season[] = [];
      let nextPage = FIRST_PAGE;
      let defaultSeason: string | null = null;
      while (true) {
        const { data } = await seasonsList({
          query: { page: nextPage, page_size: METADATA_PAGE_SIZE },
          signal: current.signal,
        });
        if (current.signal.aborted) return;
        defaultSeason ??= data.meta.default_season_id;
        loaded.push(...data.results);
        if (!data.next) break;
        if (!data.results.length || loaded.length >= data.count)
          throw new Error('Invalid season pagination');
        nextPage += 1;
      }
      defaultSeasonId.value = defaultSeason;
      seasons.value = loaded;
      seasonsLoaded = true;
      if (!query.season_id && defaultSeason) {
        await router.replace({
          name: 'players',
          query: { ...route.query, season_id: defaultSeason },
        });
        return;
      }
    }
    // Pin omitted seasons to loaded metadata; an explicit empty season is never replaced.
    if (!query.season_id && defaultSeasonId.value) {
      await router.replace({
        name: 'players',
        query: { ...route.query, season_id: defaultSeasonId.value },
      });
      return;
    }
    const filterQuery = { ...query };
    delete filterQuery.page;
    delete filterQuery.page_size;
    delete filterQuery.ordering;
    const [catalogue, metadata] = await Promise.all([
      playersList({ query, signal: current.signal }),
      playersFiltersRetrieve({ query: filterQuery, signal: current.signal }),
    ]);
    if (current.signal.aborted) return;
    result.value = catalogue.data;
    filters.value = metadata.data;
    phase.value = 'ready';
  } catch (failure) {
    if (controller !== current || (current.signal.aborted && !timedOut)) return;
    current.abort();
    if (failure instanceof ApiError) {
      reference.value = failure.requestId;
      error.value =
        failure.response.status === 404
          ? 'That Players page is unavailable. Return to the first page or change filters.'
          : 'Unable to load saved players. Please try again.';
    } else
      error.value =
        failure instanceof Error && !validated
          ? failure.message
          : 'Unable to load saved players. Please try again.';
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
  <section aria-labelledby="players-title">
    <h1 id="players-title">Players</h1>
    <p>
      Saved regular-season statistics. Only players with known positive games are included. Missing
      values are shown as —, not zero.
    </p>
    <p v-if="phase === 'loading'" role="status">Loading saved players…</p>
    <div v-if="phase === 'error'" class="panel" role="alert">
      <p>{{ error }}</p>
      <p v-if="reference">Reference: {{ reference }}</p>
      <div class="button-row">
        <button type="button" @click="load()">Try again</button
        ><button v-if="page > FIRST_PAGE" type="button" @click="choosePage(FIRST_PAGE)">
          First page</button
        ><button type="button" @click="clearFilters()">Clear filters</button>
      </div>
    </div>
    <form v-if="phase === 'ready'" class="catalogue-form" @submit.prevent="apply">
      <div class="catalogue-controls">
        <label
          >Season<select v-model="draft.season_id">
            <option v-if="!seasonOptions.length" value="">No loaded seasons</option>
            <option
              v-for="season in seasonOptions"
              :key="season.season_id"
              :value="season.season_id"
            >
              {{ season.label }}
            </option>
          </select></label
        >
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
        <label>Search name<input v-model="draft.search" type="search" /></label>
        <label
          >Rookie<select v-model="draft.rookie">
            <option value="">All</option>
            <option value="true">Rookies</option>
            <option value="false">Non-rookies</option>
          </select></label
        >
        <label
          >Ordering<input
            v-model="draft.ordering"
            placeholder="Default ordering"
            list="players-ordering"
        /></label>
        <datalist id="players-ordering">
          <template v-for="field in orderFields(type)" :key="field"
            ><option :value="field">{{ FIELD_LABELS[field] }} ascending</option>
            <option :value="`-${field}`">{{ FIELD_LABELS[field] }} descending</option></template
          >
        </datalist>
        <label
          >Page size<select v-model="draft.page_size">
            <option v-for="size in PAGE_SIZE_CHOICES" :key="size" :value="String(size)">
              {{ size }}
            </option>
            <option
              v-if="draft.page_size && !PAGE_SIZE_CHOICES.map(String).includes(draft.page_size)"
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
        <summary>Filters and ranges</summary>
        <p>
          Options cover all pages with the applied non-categorical filters; categorical selections
          do not hide alternatives. Apply changes to refresh options and results. Comma-separated
          ordering supports multiple fields; prefix − for descending.
        </p>
        <fieldset v-for="category in categories" :key="category.key">
          <legend>{{ category.label }}</legend>
          <label
            v-for="code in [
              ...new Set([
                ...category.options.map((option) => option.code),
                ...selected(category.key),
              ]),
            ]"
            :key="code"
            class="category-choice"
            ><input
              type="checkbox"
              :checked="selected(category.key).includes(code)"
              @change="toggle(category.key, code, ($event.target as HTMLInputElement).checked)"
            />{{ category.options.find((option) => option.code === code)?.label || code }} ({{
              code
            }})</label
          >
        </fieldset>
        <div class="catalogue-controls">
          <label>Birth date from<input v-model="draft.birth_date_min" type="date" /></label
          ><label>Birth date through<input v-model="draft.birth_date_max" type="date" /></label>
        </div>
        <div class="catalogue-ranges">
          <fieldset v-for="field in fields" :key="field">
            <legend>{{ FIELD_LABELS[field] }}</legend>
            <p class="data-note">
              Season range: {{ filters?.initial_ranges[field]?.min ?? '—' }} to
              {{ filters?.initial_ranges[field]?.max ?? '—' }}
            </p>
            <label
              >Minimum<input
                :value="draft[`${field}_min`]"
                type="number"
                step="any"
                :aria-label="`${FIELD_LABELS[field]} minimum`"
                @input="draft[`${field}_min`] = ($event.target as HTMLInputElement).value"
            /></label>
            <label
              >Maximum<input
                :value="draft[`${field}_max`]"
                type="number"
                step="any"
                :aria-label="`${FIELD_LABELS[field]} maximum`"
                @input="draft[`${field}_max`] = ($event.target as HTMLInputElement).value"
            /></label>
            <label
              >Availability<select
                v-model="draft[`${field}_isnull`]"
                :aria-label="`${FIELD_LABELS[field]} availability`"
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
        ><button type="button" @click="clearFilters()">Clear filters</button>
      </div>
    </form>
    <template v-if="phase === 'ready' && result">
      <h2>
        {{ result.meta.season_id ? seasonLabel(result.meta.season_id) : 'No loaded season' }} ·
        {{ result.meta.player_type === 'goalie' ? 'Goalies' : 'Skaters' }} ·
        {{ result.meta.mode === 'averages' ? 'Per-game averages' : 'Totals' }}
      </h2>
      <p class="data-note">
        Season teams show participation; statistics include the player's whole season. Biography is
        current profile data. No reliable player refresh timestamp is available.
      </p>
      <p>
        Showing {{ result.results.length }} of {{ result.count }} players. Page {{ page }}.
        Ordering: {{ result.meta.ordering }}.
      </p>
      <p v-if="!result.results.length" role="status">
        No saved players match this season and selection.
      </p>
      <div
        v-else
        class="table-scroll"
        role="region"
        aria-label="Season player statistics"
        tabindex="0"
      >
        <table class="roster-table">
          <caption>
            Season player statistics ·
            {{
              result.meta.mode === 'averages'
                ? 'Counts per game; GP remains games played'
                : 'Season totals'
            }}
            <template v-if="result.meta.player_type === 'skater'">· TOI per game (mm:ss)</template>
          </caption>
          <thead>
            <tr>
              <th scope="col">Player</th>
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
                  @click="
                    router.push({
                      name: 'players',
                      query: {
                        ...route.query,
                        page: undefined,
                        ordering: route.query.ordering === `-${field}` ? field : `-${field}`,
                      },
                    })
                  "
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
              <th scope="row">{{ player.name }}</th>
              <td>{{ player.teams.map((team) => team.abbr).join(', ') || '—' }}</td>
              <td>{{ player.position_abbr || '—' }}</td>
              <td>{{ player.nation_abbr || '—' }}</td>
              <td>{{ player.availability === 'partial' ? 'Partial' : 'Complete' }}</td>
              <td v-for="field in columns" :key="field">{{ statisticLabel(player, field) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav
        v-if="result.previous || result.next"
        class="button-row pagination"
        aria-label="Players pages"
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
