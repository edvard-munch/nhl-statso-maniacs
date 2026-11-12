<script setup lang="ts">
import { inject, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';

import { resetLinkKey } from './auth/resetLink.js';
import { sessionKey } from './auth/session.js';
import SessionControls from './components/SessionControls.vue';

const session = inject(sessionKey, null);
const resetLink = inject(resetLinkKey, null);
onBeforeUnmount(() => {
  session?.dispose();
  resetLink?.clear();
});
const route = useRoute();
const main = ref<HTMLElement | null>(null);
// Preserve keyboard context after client-side navigation, without scrolling again.
watch(
  () => route.path,
  async () => {
    await nextTick();
    main.value?.focus({ preventScroll: true });
  },
);
</script>

<template>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <header class="site-header">
    <div class="container header-content">
      <RouterLink class="brand" to="/">NHL Statso Maniacs</RouterLink>
      <nav aria-label="Main navigation">
        <RouterLink to="/" exact-active-class="current-page">Home</RouterLink>
        <RouterLink to="/players" exact-active-class="current-page">Players</RouterLink>
        <RouterLink to="/teams" exact-active-class="current-page">Teams</RouterLink>
        <RouterLink to="/games" exact-active-class="current-page">Games</RouterLink>
      </nav>
      <SessionControls v-if="session" />
    </div>
  </header>
  <main id="main-content" ref="main" class="container main-content" tabindex="-1">
    <RouterView :key="route.name === 'recover-password' ? resetLink?.version.value : undefined" />
  </main>
  <footer class="container site-footer">NHL games and player statistics</footer>
</template>
