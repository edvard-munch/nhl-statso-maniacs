<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { ApiError, gameRetrieve, type GameDetail } from '../api/index.js';
import ScoreboardCard from '../components/ScoreboardCard.vue';
import GameRosterTable from '../components/GameRosterTable.vue';
import SavedRefreshControls from '../components/SavedRefreshControls.vue';
import { SAVED_READ_TIMEOUT_MS, useSavedRefresh } from '../refresh/useSavedRefresh.js';
import { parseGameId } from '../games/presentation.js';
import { favoriteGamelogReturn } from '../favorites/gamelog.js';
import { gamelogReturn } from '../players/gamelog.js';
import {
  FIRST_PAGE,
  isScheduleDate,
  parsePage,
  savedTimeLabel,
  scheduleDateLabel,
} from '../scoreboard/presentation.js';

const route = useRoute();
const router = useRouter();
const favoriteLogBack = computed(() => favoriteGamelogReturn(route.query.favoriteLog, router));
const gamelogBack = computed(() => gamelogReturn(route.query.gamelog, router));
const game = shallowRef<GameDetail | null>(null);
const phase = ref<'loading' | 'ready' | 'error' | 'not-found'>('loading');
const requestId = ref<string | null>(null);
const busy = ref(false);
let controller: AbortController | undefined;
const sides = ['away', 'home'] as const;
const backLink = computed(() => {
  const date = isScheduleDate(route.query.date) ? route.query.date : game.value?.date;
  const page = parsePage(route.query.page);
  return {
    name: 'games',
    query: isScheduleDate(date)
      ? {
          date,
          // Only an explicit validated date/page is return context, never an arbitrary redirect URL.
          ...(isScheduleDate(route.query.date) && page !== null && page > FIRST_PAGE
            ? { page: String(page) }
            : {}),
        }
      : {},
  };
});
const refresh = useSavedRefresh({
  key: () => String(route.params.nhlId),
  ready: () => phase.value === 'ready' && !busy.value,
  freshness: () => game.value?.freshness ?? null,
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
    game.value = null;
    requestId.value = null;
    phase.value = 'loading';
  }
  const id = parseGameId(route.params.nhlId);
  if (id === null) {
    phase.value = 'not-found';
    busy.value = false;
    return;
  }
  busy.value = true;
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    current.abort();
  }, SAVED_READ_TIMEOUT_MS);
  try {
    // Browser return-context queries must not be forwarded to this query-free API.
    const { data } = await gameRetrieve({ path: { nhl_id: id }, signal });
    if (signal.aborted) return;
    game.value = data;
    phase.value = 'ready';
    return true;
  } catch (failure) {
    if (controller !== current || (signal.aborted && !timedOut)) return;
    if (background) return false;
    phase.value =
      failure instanceof ApiError && failure.response.status === 404 ? 'not-found' : 'error';
    requestId.value = failure instanceof ApiError ? failure.requestId : null;
    return false;
  } finally {
    clearTimeout(timeout);
    if (controller === current) busy.value = false;
  }
}
watch(
  () => route.params.nhlId,
  () => {
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());
</script>

<template>
  <section aria-labelledby="game-detail-title">
    <RouterLink v-if="favoriteLogBack" class="action-link" :to="favoriteLogBack"
      >Back to Favorites gamelog</RouterLink
    >
    <RouterLink v-else-if="gamelogBack" class="action-link" :to="gamelogBack"
      >Back to player gamelog</RouterLink
    >
    <RouterLink v-else class="action-link" :to="backLink">Back to games</RouterLink>
    <h1 id="game-detail-title">Game details</h1>
    <p v-if="phase === 'loading'" role="status">Loading saved game…</p>
    <div v-else-if="phase === 'not-found'" role="alert" class="panel">
      <h2>Game not found</h2>
      <p>This game is not available in the saved records.</p>
    </div>
    <div v-else-if="phase === 'error'" role="alert" class="panel">
      <p>Unable to load this saved game. Please try again.</p>
      <p v-if="requestId">Reference: {{ requestId }}</p>
      <button type="button" @click="load()">Try again</button>
    </div>
    <template v-else-if="game">
      <SavedRefreshControls :refresh="refresh" />
      <h2>
        {{ game.away_team?.name ?? 'Away team unavailable' }} at
        {{ game.home_team?.name ?? 'Home team unavailable' }}
      </h2>
      <p v-if="game.date">Pacific schedule date: {{ scheduleDateLabel(game.date) }}</p>
      <p v-else>Schedule date unavailable. Date-specific player statistics may be missing.</p>
      <ScoreboardCard :game="game" />
      <p class="data-note">
        Saved states, not current NHL observations. Unknown does not mean live.
      </p>
      <p v-if="refresh.stale.value" class="data-note">Saved data may be out of date.</p>
      <p class="data-note">Saved record update: {{ savedTimeLabel(game.freshness.saved_at) }}.</p>
      <section aria-labelledby="rosters-title">
        <h2 id="rosters-title">Saved rosters and statistics</h2>
        <p>
          — means unavailable, never zero. Complete and partial describe field availability, not
          final NHL reports. Missing or unverified rows retain the known player identity.
        </p>
        <p>
          Position and number are game-specific when known. Player names are current saved profile
          metadata.
        </p>
        <p class="data-note">
          Swipe or scroll sideways to see all statistics. Keyboard users can focus a table and use
          arrow keys.
        </p>
        <section
          v-for="side in sides"
          :key="side"
          :aria-label="`${side === 'away' ? 'Away' : 'Home'} roster`"
        >
          <h2>
            {{ side === 'away' ? 'Away' : 'Home' }} —
            {{ game[`${side}_team`]?.name ?? 'Team unavailable' }}
          </h2>
          <GameRosterTable
            :caption="`${side === 'away' ? 'Away' : 'Home'} forwards`"
            kind="skater"
            :players="game.rosters[side].forwards"
          />
          <GameRosterTable
            :caption="`${side === 'away' ? 'Away' : 'Home'} defencemen`"
            kind="skater"
            :players="game.rosters[side].defencemen"
          />
          <GameRosterTable
            :caption="`${side === 'away' ? 'Away' : 'Home'} goalies`"
            kind="goalie"
            :players="game.rosters[side].goalies"
          />
        </section>
      </section>
    </template>
  </section>
</template>
