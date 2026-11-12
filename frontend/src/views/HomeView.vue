<script setup lang="ts">
import { RouterLink } from 'vue-router';
</script>

<template>
  <section aria-labelledby="home-title">
    <h1 id="home-title">Follow NHL games and players</h1>
    <p>Game scores, player statistics and your saved lists, together in one place.</p>
    <section class="panel" aria-labelledby="home-players-title">
      <h2 id="home-players-title">Players</h2>
      <p>Browse saved season statistics for skaters and goalies.</p>
      <RouterLink class="action-link" to="/players">Browse players</RouterLink>
    </section>
    <section class="panel" aria-labelledby="home-teams-title">
      <h2 id="home-teams-title">Teams</h2>
      <p>Browse saved teams and exact season contributions.</p>
      <RouterLink class="action-link" to="/teams">Browse teams</RouterLink>
    </section>
    <section class="panel" aria-labelledby="games-title">
      <h2 id="games-title">Games</h2>
      <p>Browse saved NHL results by schedule date.</p>
      <RouterLink class="action-link" to="/games">Browse games</RouterLink>
    </section>
  </section>
</template>
