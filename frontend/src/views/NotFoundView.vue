<script setup lang="ts">
import { RouterLink } from 'vue-router';
</script>

<template>
  <section aria-labelledby="not-found-title">
    <h1 id="not-found-title">Page not found</h1>
    <p>The page you requested is unavailable.</p>
    <RouterLink class="action-link" to="/">Return home</RouterLink>
  </section>
</template>
