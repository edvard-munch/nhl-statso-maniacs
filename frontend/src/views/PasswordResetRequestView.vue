<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { useSession } from '../auth/session.js';
import { safeReturnLocation } from '../auth/returnLocation.js';

const session = useSession();
const route = useRoute();
const router = useRouter();
const email = ref('');
const accepted = ref(false);
const attempted = ref(false);
const issue = computed(() =>
  attempted.value && session.issue.value?.action === 'reset-request' ? session.issue.value : null,
);
const signIn = computed(() => ({
  name: 'login',
  query: { returnTo: safeReturnLocation(route.query.returnTo, router) },
}));
let active = true;
async function submit() {
  if (!email.value || session.busy.value || session.status.value !== 'ready') return;
  attempted.value = true;
  const result = await session.requestPasswordReset({ email: email.value });
  if (result && active) {
    accepted.value = true;
    email.value = '';
  }
}
onBeforeUnmount(() => {
  active = false;
  email.value = '';
});
</script>

<template>
  <section class="login-view" aria-labelledby="reset-request-title">
    <h1 id="reset-request-title">Reset password</h1>
    <section v-if="accepted" aria-labelledby="reset-request-accepted">
      <h2 id="reset-request-accepted">Request received</h2>
      <p>
        If an eligible account matches that address, reset instructions may be sent. This does not
        confirm an account exists or that email was delivered.
      </p>
      <button
        type="button"
        @click="
          accepted = false;
          attempted = false;
        "
      >
        Send another request
      </button>
    </section>
    <template v-else>
      <p>Enter the email address associated with your account.</p>
      <p v-if="session.status.value !== 'ready'" role="status">
        Check your session above before requesting instructions.
      </p>
      <div v-if="issue" class="panel" role="alert">
        <p>{{ issue.message }}</p>
        <p v-if="issue.reference">Reference: {{ issue.reference }}</p>
        <ul v-if="issue.fields.non_field_errors?.length">
          <li v-for="message in issue.fields.non_field_errors" :key="message">{{ message }}</li>
        </ul>
      </div>
      <form class="login-form" @submit.prevent="submit">
        <label for="reset-email">Email</label>
        <input
          id="reset-email"
          v-model="email"
          name="email"
          type="email"
          autocomplete="email"
          required
          :disabled="session.busy.value || session.status.value !== 'ready'"
          :aria-invalid="!!issue?.fields.email?.length"
          :aria-describedby="issue?.fields.email?.length ? 'reset-email-errors' : undefined"
        />
        <ul v-if="issue?.fields.email?.length" id="reset-email-errors">
          <li v-for="message in issue.fields.email" :key="message">{{ message }}</li>
        </ul>
        <button type="submit" :disabled="session.busy.value || session.status.value !== 'ready'">
          Send reset instructions
        </button>
        <p v-if="session.activeAction.value === 'reset-request'" role="status">
          Requesting instructions…
        </p>
      </form>
    </template>
    <RouterLink class="action-link" :to="signIn">Back to sign in</RouterLink>
  </section>
</template>
