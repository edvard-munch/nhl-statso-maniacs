<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import {
  ApiError,
  playerRetrieve,
  playerSeasonsList,
  type PlayerProfile,
  type HistoryResponse,
} from '../api/index.js';
import PlayerStatisticsTable from '../components/PlayerStatisticsTable.vue';
import { FIRST_PAGE, seasonLabel } from '../players/catalogue.js';
import {
  catalogueReturn,
  HISTORY_PAGE_SIZE,
  parsePlayerIdentity,
  parseProfileQuery,
} from '../players/profile.js';
import { SAVED_READ_TIMEOUT_MS } from '../refresh/useSavedRefresh.js';

const route = useRoute();
const router = useRouter();
const phase = ref<'loading' | 'ready' | 'error' | 'not-found'>('loading');
const profile = shallowRef<PlayerProfile | null>(null);
const history = shallowRef<HistoryResponse | null>(null);
const historyPhase = ref<'loading' | 'ready' | 'error'>('loading');
const error = ref('');
const reference = ref<string | null>(null);
const historyReference = ref<string | null>(null);
const draftSeason = ref('');
const draftMode = ref('totals');
const back = computed(() => catalogueReturn(route.query.returnTo, router));
const identity = computed(() => parsePlayerIdentity(route.params.playerType, route.params.nhlId));
const page = computed(() => Number(route.query.history_page || FIRST_PAGE));
const seasonHeading = computed(() =>
  profile.value?.meta.season_id ? seasonLabel(profile.value.meta.season_id) : 'No loaded season',
);
const packetRows = computed(() => {
  const data = profile.value;
  if (!data) return [];
  const rows = [
    {
      ...data.selected_season,
      label: `${seasonHeading.value} · ${data.meta.mode === 'averages' ? 'per-game averages' : 'totals'}`,
    },
    { ...data.career_totals, label: 'Career totals' },
  ];
  if (data.meta.player_type === 'skater')
    rows.push({
      ...(data.career_averages ?? { availability: 'missing' as const, stats: null }),
      label: 'Career per-game averages',
    });
  return rows;
});
const historyRows = computed(
  () =>
    history.value?.results.flatMap((season) => [
      {
        availability: season.availability,
        stats: season.stats,
        label: `${seasonLabel(season.season_id)} · overall`,
      },
      ...season.contributions.map((split) => ({
        availability: split.availability,
        stats: split.stats,
        label: `${seasonLabel(season.season_id)} · ${split.team.abbr} contribution`,
      })),
    ]) ?? [],
);
let controller: AbortController | undefined;
function navigationQuery() {
  return { ...route.query, returnTo: back.value };
}
function applySelection() {
  void router.push({
    name: 'player-profile',
    params: route.params,
    query: {
      returnTo: back.value,
      ...(draftSeason.value ? { season_id: draftSeason.value } : {}),
      mode: draftMode.value,
    },
  });
}
function choosePage(value: number) {
  void router.push({
    name: 'player-profile',
    params: route.params,
    query: { ...navigationQuery(), history_page: String(value) },
  });
}
function chooseSeason(season: string) {
  void router.push({
    name: 'player-profile',
    params: route.params,
    query: { ...navigationQuery(), season_id: season },
  });
}
function defaultSelection() {
  void router.replace({
    name: 'player-profile',
    params: route.params,
    query: { returnTo: back.value },
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
  profile.value = null;
  history.value = null;
  historyPhase.value = 'loading';
  reference.value = null;
  historyReference.value = null;
  error.value = '';
  try {
    const path = identity.value;
    if (!path) {
      phase.value = 'not-found';
      return;
    }
    let selection;
    try {
      selection = parseProfileQuery(route.query, path.player_type);
    } catch (failure) {
      error.value =
        failure instanceof Error ? failure.message : 'Choose a valid profile selection.';
      phase.value = 'error';
      return;
    }
    draftSeason.value = selection.query.season_id ?? '';
    draftMode.value = selection.query.mode ?? 'totals';
    const { data } = await playerRetrieve({ path, query: selection.query, signal: current.signal });
    if (current.signal.aborted) return;
    if (!selection.query.season_id && data.meta.season_id) {
      await router.replace({
        name: 'player-profile',
        params: route.params,
        query: { ...navigationQuery(), season_id: data.meta.season_id },
      });
      return;
    }
    profile.value = data;
    phase.value = 'ready';
    try {
      const historyData = await playerSeasonsList({
        path,
        query: { mode: selection.query.mode, page: selection.page, page_size: HISTORY_PAGE_SIZE },
        signal: current.signal,
      });
      if (current.signal.aborted) return;
      history.value = historyData.data;
      historyPhase.value = 'ready';
    } catch (failure) {
      if (stale()) return;
      historyReference.value = failure instanceof ApiError ? failure.requestId : null;
      historyPhase.value = 'error';
    }
  } catch (failure) {
    if (stale()) return;
    phase.value =
      failure instanceof ApiError && failure.response.status === 404 ? 'not-found' : 'error';
    reference.value = failure instanceof ApiError ? failure.requestId : null;
    error.value = 'Unable to load this saved player. Please try again.';
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
  <section aria-labelledby="player-profile-title">
    <RouterLink class="action-link" :to="back">Back to players</RouterLink>
    <h1 id="player-profile-title">{{ profile?.player.name || 'Player profile' }}</h1>
    <p v-if="phase === 'loading'" role="status">Loading saved player…</p>
    <div v-else-if="phase === 'not-found'" class="panel" role="alert">
      <h2>Player not found</h2>
      <p>This typed player identity is unavailable in the saved records.</p>
    </div>
    <div v-else-if="phase === 'error'" class="panel" role="alert">
      <p>{{ error }}</p>
      <p v-if="reference">Reference: {{ reference }}</p>
      <div class="button-row">
        <button type="button" @click="load()">Try again</button
        ><button type="button" @click="defaultSelection">Use default selection</button>
      </div>
    </div>
    <template v-else-if="profile">
      <p>
        {{ profile.meta.player_type === 'goalie' ? 'Goalie' : 'Skater' }} · NHL ID
        {{ profile.player.nhl_id }}
      </p>
      <img
        v-if="profile.player.image_url"
        class="profile-photo"
        :src="profile.player.image_url"
        :alt="profile.player.name"
      />
      <h2>Current saved biography</h2>
      <dl class="profile-biography">
        <div>
          <dt>Current team</dt>
          <dd>{{ profile.current_team?.name || '—' }}</dd>
        </div>
        <div>
          <dt>Position / number</dt>
          <dd>
            {{ profile.player.position_name || '—' }} / {{ profile.player.jersey_number ?? '—' }}
          </dd>
        </div>
        <div>
          <dt>Nation</dt>
          <dd>{{ profile.player.nation || profile.player.nation_abbr || '—' }}</dd>
        </div>
        <div>
          <dt>Birth date / age</dt>
          <dd>{{ profile.player.birth_date || '—' }} / {{ profile.player.age ?? '—' }}</dd>
        </div>
        <div>
          <dt>Birthplace</dt>
          <dd>
            {{
              [profile.player.birth_city, profile.player.birth_state, profile.player.birth_country]
                .filter(Boolean)
                .join(', ') || '—'
            }}
          </dd>
        </div>
        <div>
          <dt>Height</dt>
          <dd>{{ profile.player.height_cm === null ? '—' : `${profile.player.height_cm} cm` }}</dd>
        </div>
        <div>
          <dt>Weight</dt>
          <dd>
            {{ profile.player.weight_kg === null ? '—' : `${profile.player.weight_kg} kg` }} /
            {{ profile.player.weight_lb === null ? '—' : `${profile.player.weight_lb} lb` }}
          </dd>
        </div>
        <div>
          <dt>Draft year / round / number</dt>
          <dd>
            {{ profile.player.draft_year ?? '—' }} / {{ profile.player.draft_round ?? '—' }} /
            {{ profile.player.draft_number ?? '—' }}
          </dd>
        </div>
        <div>
          <dt>NHL debut</dt>
          <dd>{{ profile.player.nhl_debut || '—' }}</dd>
        </div>
        <div>
          <dt>Roster status</dt>
          <dd>{{ profile.player.roster_status || '—' }}</dd>
        </div>
        <div>
          <dt>Rookie</dt>
          <dd>{{ profile.player.rookie ? 'Yes' : 'No' }}</dd>
        </div>
        <div>
          <dt>Leadership</dt>
          <dd>
            {{
              profile.player.captain
                ? 'Captain'
                : profile.player.alternate_captain
                  ? 'Alternate captain'
                  : '—'
            }}
          </dd>
        </div>
      </dl>
      <form class="date-form" @submit.prevent="applySelection">
        <label for="profile-season">Season ID (eight digits)</label
        ><input
          id="profile-season"
          v-model="draftSeason"
          pattern="[0-9]{8}"
          placeholder="20262027"
        /><label for="profile-mode">Selected season and history statistics</label
        ><select id="profile-mode" v-model="draftMode">
          <option value="totals">Totals</option>
          <option v-if="profile.meta.player_type === 'skater'" value="averages">
            Per-game averages
          </option></select
        ><button type="submit">Apply selection</button>
      </form>
      <p class="data-note">
        An empty season selection uses the latest loaded season. Career packets are independent of
        season history and the selected season. No reliable player refresh timestamp is available.
      </p>
      <p>
        — means unknown, never zero. Missing or unverified packets are not replaced with snapshot or
        another season's statistics. Availability describes fields, not freshness.
      </p>
      <PlayerStatisticsTable
        caption="Selected season and career statistics"
        :kind="profile.meta.player_type"
        :rows="packetRows"
      />
      <h2>Season history</h2>
      <p>
        Overall season rows and exact team contributions are separate. Current team metadata does
        not establish historical participation.
      </p>
      <p v-if="historyPhase === 'loading'" role="status">Loading season history…</p>
      <div v-else-if="historyPhase === 'error'" class="panel" role="alert">
        <p>Unable to load this history page. The profile above remains available.</p>
        <p v-if="historyReference">Reference: {{ historyReference }}</p>
        <div class="button-row">
          <button type="button" @click="load()">Retry history</button
          ><button v-if="page > FIRST_PAGE" type="button" @click="choosePage(FIRST_PAGE)">
            First history page
          </button>
        </div>
      </div>
      <template v-else-if="history">
        <p v-if="!history.results.length" role="status">No saved season history.</p>
        <template v-else>
          <p>
            {{ history.count }} saved seasons. History page {{ page }}.
            {{
              history.meta.mode === 'averages'
                ? 'Per-game averages; GP remains games played.'
                : 'Season totals.'
            }}
          </p>
          <nav aria-label="Select a season from this history page">
            <button
              v-for="season in history.results"
              :key="season.season_id"
              type="button"
              @click="chooseSeason(season.season_id)"
            >
              Show {{ seasonLabel(season.season_id) }}
            </button>
          </nav>
          <PlayerStatisticsTable
            caption="Season history and team contributions"
            :kind="profile.meta.player_type"
            :rows="historyRows"
          />
          <nav
            v-if="history.next || history.previous"
            class="button-row pagination"
            aria-label="History pages"
          >
            <button type="button" :disabled="!history.previous" @click="choosePage(page - 1)">
              Previous history page</button
            ><button type="button" :disabled="!history.next" @click="choosePage(page + 1)">
              Next history page
            </button>
          </nav>
        </template>
      </template>
    </template>
  </section>
</template>

<style scoped>
.profile-photo {
  width: 8rem;
  max-width: 100%;
  height: auto;
}
.profile-biography {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
  gap: 1rem;
}
.profile-biography div {
  min-width: 0;
  overflow-wrap: anywhere;
}
.profile-biography dt {
  font-weight: 600;
}
.profile-biography dd {
  margin: 0;
}
.date-form select {
  min-width: 0;
  width: 100%;
  font: inherit;
  padding: 0.5rem;
  min-height: var(--touch-target);
}
</style>
