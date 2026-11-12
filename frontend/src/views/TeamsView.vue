<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { ApiError, teamsList, type TeamsResponse } from '../api/index.js';
import { FIRST_PAGE } from '../players/catalogue.js';
import { TEAM_ORDER_FIELDS, TEAM_PAGE_SIZES, parseTeamsQuery } from '../teams/navigation.js';
import { SAVED_READ_TIMEOUT_MS } from '../refresh/useSavedRefresh.js';

const route = useRoute();
const router = useRouter();
const phase = ref<'loading' | 'ready' | 'error'>('loading');
const result = shallowRef<TeamsResponse | null>(null);
const error = ref('');
const reference = ref<string | null>(null);
const draft = reactive<Record<string, string>>({});
const page = computed(() => Number(route.query.page || FIRST_PAGE));
let controller: AbortController | undefined;
function apply() {
  void router.push({
    name: 'teams',
    query: Object.fromEntries(
      Object.entries(draft).filter(([key, value]) => key !== 'page' && value !== ''),
    ),
  });
}
function clear() {
  void router.push({ name: 'teams' });
}
function choosePage(value: number) {
  void router.push({ name: 'teams', query: { ...route.query, page: String(value) } });
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
  error.value = '';
  reference.value = null;
  for (const key of Object.keys(draft)) delete draft[key];
  try {
    const query = parseTeamsQuery(route.query);
    validated = true;
    for (const [key, value] of Object.entries(query)) draft[key] = String(value);
    const { data } = await teamsList({ query, signal: current.signal });
    if (current.signal.aborted) return;
    result.value = data;
    phase.value = 'ready';
  } catch (failure) {
    if (controller !== current || (current.signal.aborted && !timedOut)) return;
    reference.value = failure instanceof ApiError ? failure.requestId : null;
    error.value =
      !validated && failure instanceof Error
        ? failure.message
        : failure instanceof ApiError && failure.response.status === 404
          ? 'This Teams page is unavailable. Return to the first page or change filters.'
          : 'Unable to load saved teams. Please try again.';
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
  <section aria-labelledby="teams-title">
    <h1 id="teams-title">Teams</h1>
    <p>
      All saved team identities, including historical teams. Conference, division and arena describe
      current saved metadata; this list does not establish active status or season participation.
    </p>
    <p v-if="phase === 'loading'" role="status">Loading saved teams…</p>
    <div v-else-if="phase === 'error'" role="alert" class="panel">
      <p>{{ error }}</p>
      <p v-if="reference">Reference: {{ reference }}</p>
      <div class="button-row">
        <button type="button" @click="load()">Try again</button
        ><button v-if="page > FIRST_PAGE" type="button" @click="choosePage(FIRST_PAGE)">
          First page</button
        ><button type="button" @click="clear">Clear filters</button>
      </div>
    </div>
    <template v-else-if="result">
      <form class="catalogue-form" @submit.prevent="apply">
        <div class="catalogue-controls">
          <label
            >Search team name or abbreviation<input v-model="draft.search" type="search"
          /></label>
          <label>Conferences (comma-separated)<input v-model="draft.conference" /></label>
          <label>Divisions (comma-separated)<input v-model="draft.division" /></label>
          <label
            >Ordering<input
              v-model="draft.ordering"
              list="team-directory-ordering"
              placeholder="name,nhl_id"
          /></label>
          <datalist id="team-directory-ordering">
            <template v-for="field in TEAM_ORDER_FIELDS" :key="field"
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
        <p>
          Names are exact for conference/division filters. Ordering accepts comma-separated fields
          and - for descending.
        </p>
        <div class="button-row">
          <button type="submit">Apply filters</button
          ><button type="button" @click="clear">Clear filters</button>
        </div>
      </form>
      <p>
        Showing {{ result.results.length }} of {{ result.count }} teams. Page {{ page }}. Ordering:
        {{ result.meta.ordering }}.
      </p>
      <p v-if="!result.results.length" role="status">No saved teams match this selection.</p>
      <div v-else class="table-scroll" role="region" aria-label="Saved teams" tabindex="0">
        <table class="roster-table">
          <caption>
            Saved team identities
          </caption>
          <thead>
            <tr>
              <th scope="col">Team</th>
              <th scope="col">Abbreviation</th>
              <th scope="col">Conference</th>
              <th scope="col">Division</th>
              <th scope="col">Arena</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="team in result.results" :key="team.nhl_id">
              <th scope="row">
                <RouterLink
                  :to="{
                    name: 'team-detail',
                    params: { nhlId: team.nhl_id },
                    query: { returnTo: route.fullPath },
                  }"
                  >{{ team.name }}</RouterLink
                >
              </th>
              <td>{{ team.abbr || '—' }}</td>
              <td>{{ team.conference || '—' }}</td>
              <td>{{ team.division || '—' }}</td>
              <td>{{ team.arena_name || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav
        v-if="result.next || result.previous"
        class="button-row pagination"
        aria-label="Teams pages"
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
