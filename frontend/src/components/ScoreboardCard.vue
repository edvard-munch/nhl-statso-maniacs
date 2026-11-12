<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router';
import type { ScoreboardGame } from '../api/index.js';
import { stateLabel } from '../scoreboard/presentation.js';

type GameSummary = Pick<
  ScoreboardGame,
  'away_team' | 'home_team' | 'away_score' | 'home_score' | 'state' | 'score_outcome' | 'freshness'
>;
defineProps<{ game: GameSummary; detailsTo?: RouteLocationRaw }>();
</script>

<template>
  <article
    class="game-card"
    :aria-label="`${game.away_team?.name ?? 'Away team unavailable'} at ${game.home_team?.name ?? 'Home team unavailable'}`"
  >
    <p class="game-state">
      {{ stateLabel(game.state) }}
      <span v-if="game.score_outcome">
        · {{ game.score_outcome === 'OT' ? 'Overtime' : 'Shootout' }}</span
      >
    </p>
    <ul class="game-sides">
      <li>
        <span
          ><span class="side-label">Away</span
          ><span>{{ game.away_team?.name ?? 'Away team unavailable' }}</span></span
        >
        <strong :aria-label="`Away score: ${game.away_score ?? 'unavailable'}`">{{
          game.away_score ?? '—'
        }}</strong>
      </li>
      <li>
        <span
          ><span class="side-label">Home</span
          ><span>{{ game.home_team?.name ?? 'Home team unavailable' }}</span></span
        >
        <strong :aria-label="`Home score: ${game.home_score ?? 'unavailable'}`">{{
          game.home_score ?? '—'
        }}</strong>
      </li>
    </ul>
    <p v-if="game.freshness.partial" class="data-note">Some saved game details are unavailable.</p>
    <RouterLink v-if="detailsTo" class="action-link" :to="detailsTo">View game details</RouterLink>
  </article>
</template>
