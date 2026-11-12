<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import {
  ApiError,
  teamRetrieve,
  teamPlayersList,
  type TeamDetail,
  type TeamPlayersResponse,
} from '../api/index.js';
import {
  FIELD_LABELS,
  FIRST_PAGE,
  SKATER_FIELDS,
  GOALIE_FIELDS,
  numericFields,
  orderFields,
  seasonLabel,
  statisticLabel,
} from '../players/catalogue.js';
import {
  TEAM_PAGE_SIZES,
  parseTeamId,
  parseTeamPlayersQuery,
  teamsReturn,
  externalWebsite,
} from '../teams/navigation.js';
import { SAVED_READ_TIMEOUT_MS } from '../refresh/useSavedRefresh.js';

const route = useRoute();
const router = useRouter();
const phase = ref<'loading' | 'ready' | 'error' | 'not-found'>('loading');
const detail = shallowRef<TeamDetail | null>(null);
const result = shallowRef<TeamPlayersResponse | null>(null);
const playersPhase = ref<'loading' | 'ready' | 'error'>('loading');
const error = ref('');
const reference = ref<string | null>(null);
const playersReference = ref<string | null>(null);
const draft = reactive<Record<string, string>>({});
const filtersOpen = ref(false);
const back = computed(() => teamsReturn(route.query.returnTo, router));
const type = computed(() => draft.player_type || 'skater');
const page = computed(() => Number(route.query.page || FIRST_PAGE));
const columns = computed(() =>
  result.value?.meta.player_type === 'goalie' ? GOALIE_FIELDS : SKATER_FIELDS,
);
const website = computed(() => externalWebsite(detail.value?.team.website_url || ''));
let controller: AbortController | undefined;
function apply() {
  void router.push({
    name: 'team-detail',
    params: route.params,
    query: {
      ...Object.fromEntries(
        Object.entries(draft).filter(([key, value]) => key !== 'page' && value !== ''),
      ),
      returnTo: back.value,
    },
  });
}
function clear() {
  void router.push({
    name: 'team-detail',
    params: route.params,
    query: {
      season_id: detail.value?.meta.season_id || undefined,
      player_type: type.value,
      mode: 'totals',
      returnTo: back.value,
    },
  });
}
function changeType() {
  for (const key of Object.keys(draft))
    if (!['season_id', 'player_type', 'search', 'page_size'].includes(key)) delete draft[key];
  draft.mode = 'totals';
}
function choosePage(value: number) {
  void router.push({
    name: 'team-detail',
    params: route.params,
    query: { ...route.query, page: String(value), returnTo: back.value },
  });
}
function sort(field: string) {
  void router.push({
    name: 'team-detail',
    params: route.params,
    query: {
      ...route.query,
      returnTo: back.value,
      page: undefined,
      ordering: result.value?.meta.ordering.split(',')[0] === `-${field}` ? field : `-${field}`,
    },
  });
}
async function load() {
  controller?.abort();
  const current = new AbortController();
  controller = current;
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    current.abort();
  }, SAVED_READ_TIMEOUT_MS);
  const stale = () => controller !== current || (current.signal.aborted && !timedOut);
  phase.value = 'loading';
  detail.value = null;
  result.value = null;
  playersPhase.value = 'loading';
  error.value = '';
  reference.value = null;
  playersReference.value = null;
  for (const key of Object.keys(draft)) delete draft[key];
  try {
    const id = parseTeamId(route.params.nhlId);
    if (id === null) {
      phase.value = 'not-found';
      return;
    }
    let query;
    try {
      query = parseTeamPlayersQuery(route.query);
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : 'Choose a valid team selection.';
      phase.value = 'error';
      return;
    }
    for (const [key, value] of Object.entries(query)) draft[key] = String(value);
    const { data } = await teamRetrieve({
      path: { nhl_id: id },
      query: query.season_id ? { season_id: query.season_id } : {},
      signal: current.signal,
    });
    if (current.signal.aborted) return;
    if (!query.season_id && data.meta.season_id) {
      await router.replace({
        name: 'team-detail',
        params: route.params,
        query: { ...route.query, season_id: data.meta.season_id, returnTo: back.value },
      });
      return;
    }
    detail.value = data;
    phase.value = 'ready';
    try {
      const players = await teamPlayersList({
        path: { nhl_id: id },
        query,
        signal: current.signal,
      });
      if (current.signal.aborted) return;
      result.value = players.data;
      playersPhase.value = 'ready';
    } catch (failure) {
      if (stale()) return;
      playersReference.value = failure instanceof ApiError ? failure.requestId : null;
      playersPhase.value = 'error';
    }
  } catch (failure) {
    if (stale()) return;
    phase.value =
      failure instanceof ApiError && failure.response.status === 404 ? 'not-found' : 'error';
    reference.value = failure instanceof ApiError ? failure.requestId : null;
    error.value = 'Unable to load this saved team. Please try again.';
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
  <section aria-labelledby="team-title">
    <RouterLink class="action-link" :to="back">Back to teams</RouterLink>
    <h1 id="team-title">{{ detail?.team.name || 'Team details' }}</h1>
    <p v-if="phase === 'loading'" role="status">Loading saved team…</p>
    <div v-else-if="phase === 'not-found'" role="alert" class="panel">
      <h2>Team not found</h2>
      <p>This team identity is unavailable in the saved records.</p>
    </div>
    <div v-else-if="phase === 'error'" role="alert" class="panel">
      <p>{{ error }}</p>
      <p v-if="reference">Reference: {{ reference }}</p>
      <div class="button-row">
        <button type="button" @click="load()">Try again</button
        ><button type="button" @click="clear">Clear filters</button>
      </div>
    </div>
    <template v-else-if="detail">
      <img
        v-if="detail.team.image_url"
        class="team-photo"
        :src="detail.team.image_url"
        :alt="detail.team.name"
      />
      <p>Current saved metadata, not a historical reconstruction or proof of active status.</p>
      <dl class="team-biography">
        <div>
          <dt>Abbreviation</dt>
          <dd>{{ detail.team.abbr || '—' }}</dd>
        </div>
        <div>
          <dt>Conference / division</dt>
          <dd>{{ detail.team.conference || '—' }} / {{ detail.team.division || '—' }}</dd>
        </div>
        <div>
          <dt>Arena / location</dt>
          <dd>{{ detail.team.arena_name || '—' }} / {{ detail.team.arena_location || '—' }}</dd>
        </div>
        <div>
          <dt>NHL debut</dt>
          <dd>{{ detail.team.nhl_debut || '—' }}</dd>
        </div>
        <div>
          <dt>Saved website</dt>
          <dd>
            <a v-if="website" :href="website" target="_blank" rel="noopener noreferrer">{{
              detail.team.website_url
            }}</a><span v-else>{{ detail.team.website_url || '—' }}</span>
          </dd>
        </div>
      </dl>
      <h2>
        {{ detail.meta.season_id ? seasonLabel(detail.meta.season_id) : 'No loaded season' }} · Team
        contributions
      </h2>
      <p>
        Only exact {{ detail.team.abbr || 'team' }} season splits with known positive games are
        included. Combined-only totals and current roster membership never fill a missing split.
        Player profiles show overall season values separately.
      </p>
      <p>
        Position and jersey number are current profile data. — means unknown, never zero; TOI is per
        game. No reliable player refresh timestamp is available.
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
              list="team-player-ordering"
              placeholder="Default ordering" /></label
          ><datalist id="team-player-ordering">
            <template v-for="field in orderFields(type)" :key="field"
              ><option :value="field" />
              <option :value="`-${field}`"
            /></template>
          </datalist>
          <label
            >Page size<select v-model="draft.page_size">
              <option v-for="size in TEAM_PAGE_SIZES" :key="size" :value="String(size)">
                {{ size }}
              </option>
              <option
                v-if="draft.page_size && !TEAM_PAGE_SIZES.map(String).includes(draft.page_size)"
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
            Bounds use this team's season contribution, not overall player totals. TOI bounds use
            seconds and save-percentage bounds use fractions (0–1). No team-scoped ranges or choices
            are inferred from this page or global Players metadata. Ordering accepts comma-separated
            fields with - for descending.
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
          ><button type="button" @click="clear">Clear filters</button>
        </div>
      </form>
      <p v-if="playersPhase === 'loading'" role="status">Loading team contributions…</p>
      <div v-else-if="playersPhase === 'error'" class="panel" role="alert">
        <p>Unable to load this team contribution page. Team metadata remains available.</p>
        <p v-if="playersReference">Reference: {{ playersReference }}</p>
        <div class="button-row">
          <button type="button" @click="load()">Retry contributions</button
          ><button v-if="page > FIRST_PAGE" type="button" @click="choosePage(FIRST_PAGE)">
            First page
          </button>
        </div>
      </div>
      <template v-else-if="result"
        ><p>
          Showing {{ result.results.length }} of {{ result.count }}
          {{ result.meta.player_type === 'goalie' ? 'goalies' : 'skaters' }}. Page {{ page }}.
          {{
            result.meta.mode === 'averages'
              ? 'Counts per game; GP remains games played.'
              : 'Team season totals.'
          }}
          Ordering: {{ result.meta.ordering }}.
        </p>
        <p v-if="!result.results.length" role="status">
          No saved team contributions match this season and selection.
        </p>
        <div
          v-else
          class="table-scroll"
          role="region"
          aria-label="Team season contributions"
          tabindex="0"
        >
          <table class="roster-table">
            <caption>
              {{
                detail.team.abbr
              }}
              season contributions ·
              <template v-if="result.meta.player_type === 'skater'">TOI per game (mm:ss)</template
              ><template v-else>Goalie totals and rates</template>
            </caption>
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Current number</th>
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
                <td>{{ player.jersey_number ?? '—' }}</td>
                <td>{{ player.position_abbr || '—' }}</td>
                <td>{{ player.nation_abbr || '—' }}</td>
                <td>{{ player.availability === 'partial' ? 'Partial' : 'Complete' }}</td>
                <td v-for="field in columns" :key="field">{{ statisticLabel(player, field) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <nav
          v-if="result.next || result.previous"
          class="button-row pagination"
          aria-label="Team contribution pages"
        >
          <button type="button" :disabled="!result.previous" @click="choosePage(page - 1)">
            Previous page</button
          ><button type="button" :disabled="!result.next" @click="choosePage(page + 1)">
            Next page
          </button>
        </nav>
      </template>
    </template>
  </section>
</template>

<style scoped>
.team-photo {
  width: 8rem;
  max-width: 100%;
  height: auto;
}
.team-biography {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
  gap: 1rem;
}
.team-biography div {
  min-width: 0;
  overflow-wrap: anywhere;
}
.team-biography dt {
  font-weight: 600;
}
.team-biography dd {
  margin: 0;
}
</style>
