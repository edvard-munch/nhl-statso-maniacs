<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { useSession } from '../auth/session.js';
import { safeReturnLocation } from '../auth/returnLocation.js';

const session = useSession();
const route = useRoute();
const router = useRouter();
const username = ref('');
const password = ref('');
const returnTo = computed(() => safeReturnLocation(route.query.returnTo, router));
const loginIssue = computed(() =>
  session.issue.value?.action === 'login' ? session.issue.value : null,
);
let active = true;
async function submit() {
  if (!username.value || !password.value || session.busy.value || session.status.value !== 'ready')
    return;
  try {
    const success = await session.login({ username: username.value, password: password.value });
    if (success && active) await router.replace(returnTo.value);
  } finally {
    password.value = '';
  }
}
onBeforeUnmount(() => {
  active = false;
  password.value = '';
});
</script>

<template>
  <section class="login-view" aria-labelledby="login-title">
    <h1 id="login-title">Sign in</h1>
    <p v-if="session.status.value === 'loading'" role="status">Checking sign-in status…</p>
    <p v-if="session.status.value === 'error'" role="status">
      Check your session above before signing in.
    </p>
    <p v-if="session.status.value === 'ready' && session.user.value">
      Currently signed in as {{ session.user.value.username }}.
      <RouterLink :to="returnTo">Continue</RouterLink>, or sign in to another account below.
    </p>
    <div v-if="loginIssue" role="alert" class="panel">
      <p>{{ loginIssue.message }}</p>
      <p v-if="loginIssue.reference">Reference: {{ loginIssue.reference }}</p>
    </div>
    <form class="login-form" @submit.prevent="submit">
      <label for="login-username">Username</label>
      <input
        id="login-username"
        v-model="username"
        name="username"
        autocomplete="username"
        required
        :disabled="session.busy.value || session.status.value !== 'ready'"
        :aria-invalid="!!loginIssue?.fields.username?.length"
        :aria-describedby="loginIssue?.fields.username?.length ? 'username-errors' : undefined"
      />
      <ul v-if="loginIssue?.fields.username?.length" id="username-errors">
        <li v-for="message in loginIssue.fields.username" :key="message">{{ message }}</li>
      </ul>
      <label for="login-password">Password</label>
      <input
        id="login-password"
        v-model="password"
        name="password"
        type="password"
        autocomplete="current-password"
        required
        :disabled="session.busy.value || session.status.value !== 'ready'"
        :aria-invalid="!!loginIssue?.fields.password?.length"
        :aria-describedby="loginIssue?.fields.password?.length ? 'password-errors' : undefined"
      />
      <ul v-if="loginIssue?.fields.password?.length" id="password-errors">
        <li v-for="message in loginIssue.fields.password" :key="message">{{ message }}</li>
      </ul>
      <button type="submit" :disabled="session.busy.value || session.status.value !== 'ready'">
        Sign in
      </button>
      <p
        v-if="session.activeAction.value === 'login' && session.status.value === 'ready'"
        role="status"
      >
        Signing in…
      </p>
    </form>
  </section>
</template>
