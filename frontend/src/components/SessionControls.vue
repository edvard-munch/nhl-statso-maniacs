<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { useSession } from '../auth/session.js';

const session = useSession();
const route = useRoute();
const signIn = computed(() => ({ name: 'login', query: { returnTo: route.fullPath } }));
</script>

<template>
  <section
    v-if="
      session.status.value !== 'ready' ||
      session.user.value ||
      route.name !== 'login' ||
      session.issue.value?.action === 'logout'
    "
    class="session-controls"
    aria-label="Sign-in status"
  >
    <p v-if="session.status.value === 'loading'" role="status">Checking session…</p>
    <template v-else-if="session.status.value === 'error'">
      <p role="status">Sign-in status unavailable.</p>
      <button type="button" :disabled="session.busy.value" @click="session.checkSession()">
        Check session
      </button>
    </template>
    <template v-else-if="session.user.value">
      <span class="session-identity">Signed in as {{ session.user.value.username }}</span>
      <button type="button" :disabled="session.busy.value" @click="session.logout()">
        Sign out
      </button>
    </template>
    <RouterLink v-else-if="route.name !== 'login'" class="action-link" :to="signIn"
      >Sign in</RouterLink
    >
    <p v-if="session.activeAction.value === 'logout'" role="status">Signing out…</p>
    <p v-if="session.issue.value?.action === 'logout'" role="status">
      {{ session.issue.value.message }}
    </p>
  </section>
</template>
