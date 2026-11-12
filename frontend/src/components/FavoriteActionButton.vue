<script setup lang="ts">
import { inject } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { useSession } from '../auth/session.js';
import { favoriteActionsKey } from '../favorites/actions.js';
const props = defineProps<{
  action: 'add' | 'remove';
  playerType: string;
  nhlId: number;
  name: string;
}>();
const actions = inject(favoriteActionsKey, null);
const session = useSession();
const route = useRoute();
</script>
<template>
  <template v-if="actions">
    <button
      v-if="session.status.value === 'ready' && session.user.value"
      type="button"
      :disabled="session.busy.value || actions.running.value"
      :aria-label="action === 'add' ? `Save ${name} to Favorites` : `Remove ${name} from Favorites`"
      @click="actions.run(props.action, props.playerType, props.nhlId, props.name, route.fullPath)"
    >
      {{ action === 'add' ? 'Save to Favorites' : 'Remove from Favorites' }}
    </button>
    <RouterLink
      v-else-if="action === 'add' && session.status.value === 'ready' && !session.busy.value"
      class="action-link"
      :to="{ name: 'login', query: { returnTo: route.fullPath } }"
      >Sign in to save this player</RouterLink
    >
  </template>
</template>
