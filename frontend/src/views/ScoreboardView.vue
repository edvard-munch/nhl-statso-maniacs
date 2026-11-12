<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ApiError,
  gameDatesList,
  scoreboardList,
  type GameDatesMeta,
  type ScoreboardResponse,
} from '../api/index.js';
import ScoreboardCard from '../components/ScoreboardCard.vue';
import SavedRefreshControls from '../components/SavedRefreshControls.vue';
import { SAVED_READ_TIMEOUT_MS, useSavedRefresh } from '../refresh/useSavedRefresh.js';
import {
  FIRST_PAGE,
  SCOREBOARD_PAGE_SIZE,
  isScheduleDate,
  parsePage,
  savedTimeLabel,
  scheduleDateLabel,
} from '../scoreboard/presentation.js';

const route = useRoute();
const router = useRouter();
const phase = ref<'loading' | 'ready' | 'error'>('loading');
const error = ref('');
const requestId = ref<string | null>(null);
const busy = ref(false);
const draftDate = ref('');
const selectedDate = ref('');
const initialFallback = shallowRef<{ date: string; reference: string } | null>(null);
const page = ref(FIRST_PAGE);
const dates = shallowRef<GameDatesMeta | null>(null);
const scoreboard = shallowRef<ScoreboardResponse | null>(null);
let controller: AbortController | undefined;
const exactNavigation = computed(() => dates.value?.selected_date === selectedDate.value);
const previousDate = computed(() => (exactNavigation.value ? dates.value?.previous_date : null));
const nextDate = computed(() => (exactNavigation.value ? dates.value?.next_date : null));

function chooseDate(date: string) {
  if (!isScheduleDate(date)) return;
  if (route.query.date === date && route.query.page === undefined) {
    void load();
    return;
  }
  void router.push({ name: 'games', query: { date } });
}
function gameDetailsLink(nhlId: number) {
  return {
    name: 'game-detail',
    params: { nhlId },
    query: {
      date: selectedDate.value,
      ...(page.value > FIRST_PAGE ? { page: String(page.value) } : {}),
    },
  };
}
function choosePage(value: number) {
  void router.push({ name: 'games', query: { date: selectedDate.value, page: String(value) } });
}

const refresh = useSavedRefresh({
  key: () => JSON.stringify([route.query.date, route.query.page]),
  ready: () => phase.value === 'ready' && !busy.value,
  freshness: () => scoreboard.value?.meta.freshness ?? null,
  refresh: () => load(true),
});
async function load(background = false): Promise<boolean | undefined> {
  if (background && busy.value) return;
  if (!background) refresh.reset();
  controller?.abort();
  const current = new AbortController();
  controller = current;
  const { signal } = current;
  if (!background) {
    phase.value = 'loading';
    scoreboard.value = null;
    dates.value = null;
    error.value = '';
    requestId.value = null;
  }
  // An initially empty store keeps its API-supplied Pacific reference date when polling.
  const date = route.query.date ?? (background ? selectedDate.value || undefined : undefined);
  const requestedPage = parsePage(route.query.page);
  if (!background) {
    selectedDate.value = isScheduleDate(date) ? date : '';
    draftDate.value = selectedDate.value;
  }
  if ((date !== undefined && !isScheduleDate(date)) || requestedPage === null) {
    error.value = 'Choose a valid schedule date (YYYY-MM-DD) and a positive page number.';
    phase.value = 'error';
    busy.value = false;
    return;
  }
  page.value = requestedPage;
  busy.value = true;
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    current.abort();
  }, SAVED_READ_TIMEOUT_MS);
  try {
    if (date === undefined) {
      // Only a visit without an explicit date adopts the API's Pacific/default selection.
      const { data } = await gameDatesList({ signal });
      if (signal.aborted) return;
      if (data.meta.selected_date) {
        initialFallback.value = data.meta.used_fallback
          ? { date: data.meta.selected_date, reference: data.meta.reference_date }
          : null;
        await router.replace({ name: 'games', query: { date: data.meta.selected_date } });
        return;
      }
      dates.value = data.meta;
      selectedDate.value = data.meta.reference_date;
      draftDate.value = data.meta.reference_date;
      phase.value = 'ready';
      return true;
    }
    // isScheduleDate above has validated the route; never pass raw route parameters.
    const requestedDate = selectedDate.value;
    const [navigation, games] = await Promise.all([
      gameDatesList({ query: { date: requestedDate }, signal }),
      scoreboardList({
        query: { date: requestedDate, page: requestedPage, page_size: SCOREBOARD_PAGE_SIZE },
        signal,
      }),
    ]);
    if (signal.aborted) return;
    dates.value = navigation.data.meta;
    scoreboard.value = games.data;
    phase.value = 'ready';
    return true;
  } catch (failure) {
    if (controller !== current || (signal.aborted && !timedOut)) return;
    current.abort();
    if (background) return false;
    requestId.value = failure instanceof ApiError ? failure.requestId : null;
    error.value =
      failure instanceof ApiError && failure.response.status === 404
        ? 'That saved games page is unavailable. Choose another date or return to the first page.'
        : 'Unable to load saved games. Please try again.';
    phase.value = 'error';
    return false;
  } finally {
    clearTimeout(timeout);
    if (controller === current) busy.value = false;
  }
}

watch(
  [() => route.query.date, () => route.query.page],
  () => {
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());
</script>

<template>
  <section aria-labelledby="scoreboard-title">
    <h1 id="scoreboard-title">Games</h1>
    <p>Browse saved NHL results by Pacific schedule date.</p>
    <form class="date-form" @submit.prevent="chooseDate(draftDate)">
      <label for="schedule-date">Schedule date</label>
      <input id="schedule-date" v-model="draftDate" type="date" required />
      <button type="submit">Show games</button>
    </form>
    <p v-if="phase === 'loading'" role="status">Loading saved games…</p>
    <div v-else-if="phase === 'error'" class="panel" role="alert">
      <p>{{ error }}</p>
      <p v-if="requestId">Reference: {{ requestId }}</p>
      <div class="button-row">
        <button type="button" @click="load()">Try again</button>
        <button
          v-if="selectedDate && page > FIRST_PAGE"
          type="button"
          @click="chooseDate(selectedDate)"
        >
          First page
        </button>
      </div>
    </div>
    <template v-else>
      <SavedRefreshControls :refresh="refresh" />
      <template v-if="dates?.selected_date">
        <nav class="date-navigation" aria-label="Saved game dates">
          <div class="button-row">
            <button
              type="button"
              aria-label="Previous saved date"
              :disabled="!previousDate"
              @click="previousDate && chooseDate(previousDate)"
            >
              Previous date
            </button>
            <button
              type="button"
              aria-label="Next saved date"
              :disabled="!nextDate"
              @click="nextDate && chooseDate(nextDate)"
            >
              Next date
            </button>
          </div>
          <p>Available saved dates</p>
          <div class="button-row date-window">
            <button
              v-for="date in dates.window"
              :key="date"
              type="button"
              :aria-pressed="date === selectedDate"
              :aria-label="scheduleDateLabel(date)"
              @click="chooseDate(date)"
            >
              {{ scheduleDateLabel(date, true) }}
            </button>
          </div>
        </nav>
        <p v-if="!exactNavigation" class="data-note">
          This date is not in the saved dates. Choose an available date above; results below still
          use your requested date.
        </p>
      </template>
      <p v-if="!scoreboard" role="status">No saved game dates are available.</p>
      <template v-else>
        <h2>{{ scheduleDateLabel(scoreboard.meta.date) }}</h2>
        <p v-if="initialFallback?.date === selectedDate" class="data-note">
          Latest saved date selected because no saved date matched
          {{ initialFallback.reference }} (Pacific).
        </p>
        <p class="data-note">
          Saved states, not current NHL observations. Unknown does not mean live.
        </p>
        <p v-if="refresh.stale.value" class="data-note">Saved data may be out of date.</p>
        <p v-if="scoreboard.meta.freshness.partial" class="data-note">
          Some saved team or score details are unavailable.
        </p>
        <p v-if="!scoreboard.results.length" role="status">No saved games for this date.</p>
        <template v-else>
          <p>
            Showing {{ scoreboard.results.length }} of {{ scoreboard.count }} saved games. Page
            {{ page }}.
          </p>
          <div class="scoreboard-grid">
            <ScoreboardCard
              v-for="game in scoreboard.results"
              :key="game.nhl_id"
              :game="game"
              :details-to="gameDetailsLink(game.nhl_id)"
            />
          </div>
          <nav
            v-if="scoreboard.previous || scoreboard.next"
            class="button-row pagination"
            aria-label="Games pages"
          >
            <button type="button" :disabled="!scoreboard.previous" @click="choosePage(page - 1)">
              Previous page
            </button>
            <button type="button" :disabled="!scoreboard.next" @click="choosePage(page + 1)">
              Next page
            </button>
          </nav>
          <p class="data-note">
            Saved record update: {{ savedTimeLabel(scoreboard.meta.freshness.saved_at) }}.
          </p>
        </template>
      </template>
    </template>
  </section>
</template>
