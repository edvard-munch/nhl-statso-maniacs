<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { safeReturnLocation } from '../auth/returnLocation.js';
import { useSession } from '../auth/session.js';

const session = useSession();
const route = useRoute();
const router = useRouter();
const returnTo = computed(() =>
  ['register', 'password-reset', 'recover-password'].includes(String(route.name))
    ? safeReturnLocation(route.query.returnTo, router)
    : route.fullPath,
);
const recoveryPending = computed(
  () =>
    !!session.activeAction.value?.startsWith('reset-') &&
    !['password-reset', 'recover-password'].includes(String(route.name)),
);
const signIn = computed(() => ({ name: 'login', query: { returnTo: returnTo.value } }));
</script>

<template>
  <section
    v-if="
      session.status.value !== 'ready' ||
      session.user.value ||
      route.name !== 'login' ||
      session.issue.value?.action === 'logout' ||
      session.activeAction.value === 'register' ||
      recoveryPending
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
    <template v-else-if="route.name !== 'login'">
      <RouterLink class="action-link" :to="signIn">Sign in</RouterLink>
      <RouterLink
        v-if="route.name !== 'register'"
        class="action-link"
        :to="{ name: 'register', query: { returnTo } }"
        >Create account</RouterLink
      >
    </template>
    <p v-if="session.activeAction.value === 'register' && route.name !== 'register'" role="status">
      Creating account…
    </p>
    <p v-if="recoveryPending" role="status">Password recovery request in progress…</p>
    <p v-if="session.activeAction.value === 'logout'" role="status">Signing out…</p>
    <p v-if="session.issue.value?.action === 'logout'" role="status">
      {{ session.issue.value.message }}
    </p>
  </section>
</template>
