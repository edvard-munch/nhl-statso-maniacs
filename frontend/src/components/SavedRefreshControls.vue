<script setup lang="ts">
import type { SavedRefresh } from '../refresh/useSavedRefresh.js';
import { savedTimeLabel } from '../scoreboard/presentation.js';

defineProps<{ refresh: SavedRefresh }>();
</script>

<template>
  <section class="refresh-controls" aria-label="Saved data refresh">
    <div class="button-row">
      <label class="refresh-toggle"
        ><input
          type="checkbox"
          :checked="refresh.automatic.value"
          @change="refresh.setAutomatic(($event.target as HTMLInputElement).checked)"
        />
        Auto-refresh</label
      >
      <button
        type="button"
        :aria-disabled="
          refresh.checking.value ||
          !refresh.ready.value ||
          refresh.offline.value ||
          refresh.hidden.value
        "
        @click="refresh.run()"
      >
        Refresh now
      </button>
    </div>
    <p v-if="refresh.checking.value" role="status">Checking saved data…</p>
    <p v-else-if="refresh.failed.value" role="status">
      Refresh failed. Displayed data is unchanged.
      <span v-if="refresh.automatic.value">Will retry while this tab is visible and online.</span
      ><span v-else>Use Refresh now to retry.</span>
    </p>
    <p v-if="refresh.offline.value" role="status">Offline. Saved-data checks are paused.</p>
    <p v-else-if="refresh.hidden.value">Checks are paused while this tab is hidden.</p>
    <p v-else-if="refresh.automatic.value && !refresh.failed.value">
      Checks saved data every minute while visible. NHL updates run separately.
    </p>
    <p v-else-if="!refresh.automatic.value">Auto-refresh paused.</p>
    <p v-if="refresh.checkedAt.value" class="data-note">
      Last checked: {{ savedTimeLabel(refresh.checkedAt.value) }}. A check does not mean new NHL
      data was saved.
    </p>
  </section>
</template>
