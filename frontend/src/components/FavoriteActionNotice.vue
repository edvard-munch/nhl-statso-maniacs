<script setup lang="ts">
import { computed, inject } from 'vue';
import { favoriteActionsKey } from '../favorites/actions.js';
const actions = inject(favoriteActionsKey, null);
const notice = computed(() => actions?.notice.value);
</script>
<template>
  <div
    v-if="notice"
    class="panel"
    :role="notice.outcome === 'confirmed' || notice.outcome === 'observed' ? 'status' : 'alert'"
    aria-label="Favorites action result"
  >
    <p>{{ notice.message }}</p>
    <p v-if="notice.reference">Reference: {{ notice.reference }}</p>
    <p v-if="notice.quota">
      Quota reported by this save: {{ notice.quota.total_count }} of
      {{ notice.quota.limit }} players; {{ notice.quota.remaining }} remaining.
    </p>
  </div>
</template>
