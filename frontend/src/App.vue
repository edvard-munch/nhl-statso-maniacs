<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';

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
      </nav>
    </div>
  </header>
  <main id="main-content" ref="main" class="container main-content" tabindex="-1">
    <RouterView />
  </main>
  <footer class="container site-footer">NHL games and player statistics</footer>
</template>
