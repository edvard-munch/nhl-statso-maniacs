<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, shallowRef, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { useSession } from '../auth/session.js';
import { resetLinkKey } from '../auth/resetLink.js';

const session = useSession();
const link = shallowRef(inject(resetLinkKey, null)?.take() ?? null);
const phase = ref<
  'waiting' | 'checking' | 'valid' | 'invalid' | 'check-error' | 'uncertain' | 'complete'
>(link.value ? 'waiting' : 'invalid');
const attempted = ref(false);
const password1 = ref('');
const password2 = ref('');
const issue = computed(() =>
  attempted.value &&
  (session.issue.value?.action === 'reset-validate' ||
    session.issue.value?.action === 'reset-confirm')
    ? session.issue.value
    : null,
);
let active = true;
function invalidLink() {
  link.value = null;
  phase.value = 'invalid';
}
async function checkLink() {
  if (!link.value || session.busy.value || session.status.value !== 'ready') return;
  phase.value = 'checking';
  attempted.value = true;
  const result = await session.validatePasswordReset({ ...link.value });
  if (!active) return;
  if (result) phase.value = 'valid';
  else if (session.issue.value?.code === 'invalid_reset_token') invalidLink();
  else phase.value = 'check-error';
}
async function submit() {
  if (
    !link.value ||
    !password1.value ||
    !password2.value ||
    session.busy.value ||
    session.status.value !== 'ready'
  )
    return;
  try {
    const result = await session.confirmPasswordReset({
      ...link.value,
      new_password1: password1.value,
      new_password2: password2.value,
    });
    if (!active) return;
    if (result) {
      link.value = null;
      phase.value = 'complete';
    } else if (session.issue.value?.code === 'invalid_reset_token') invalidLink();
    else if (!['invalid_parameters', 'csrf_failed'].includes(session.issue.value?.code ?? ''))
      phase.value = 'uncertain';
  } finally {
    password1.value = '';
    password2.value = '';
  }
}
watch(
  [() => session.status.value, () => session.busy.value],
  () => {
    if (phase.value === 'waiting' && session.status.value === 'ready' && !session.busy.value)
      void checkLink();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  active = false;
  link.value = null;
  password1.value = '';
  password2.value = '';
});
</script>

<template>
  <section class="login-view" aria-labelledby="reset-confirm-title">
    <h1 id="reset-confirm-title">Choose a new password</h1>
    <template v-if="phase === 'complete'">
      <h2>Password changed</h2>
      <p>Your password has been reset. Sign in with the new password to continue.</p>
      <p v-if="session.user.value">
        This browser is still signed in as {{ session.user.value.username }}.
      </p>
      <RouterLink class="action-link" :to="{ name: 'login' }">Sign in</RouterLink>
    </template>
    <div v-else-if="phase === 'invalid'" class="panel" role="alert">
      <p>
        This reset link is invalid or no longer available. Reopen the link from your email or
        request new instructions.
      </p>
    </div>
    <template v-else>
      <p v-if="phase === 'waiting'" role="status">Waiting for session checks…</p>
      <p v-if="phase === 'checking'" role="status">Checking reset link…</p>
      <p v-if="session.status.value === 'error'" role="status">
        Check your session above before continuing.
      </p>
      <div v-if="issue" class="panel" role="alert">
        <p>{{ issue.message }}</p>
        <p v-if="issue.reference">Reference: {{ issue.reference }}</p>
        <ul v-if="issue.fields.non_field_errors?.length">
          <li v-for="message in issue.fields.non_field_errors" :key="message">{{ message }}</li>
        </ul>
      </div>
      <template v-if="phase === 'check-error' || phase === 'uncertain'">
        <button
          type="button"
          :disabled="session.busy.value || session.status.value !== 'ready'"
          @click="checkLink()"
        >
          Check link again
        </button>
        <RouterLink class="action-link" :to="{ name: 'login' }">Try signing in</RouterLink>
      </template>
      <form v-if="phase === 'valid'" class="login-form" @submit.prevent="submit">
        <p>
          Keep this page open while resetting your password. Reloading requires reopening the email
          link.
        </p>
        <label for="reset-password1">New password</label>
        <input
          id="reset-password1"
          v-model="password1"
          name="new_password1"
          type="password"
          autocomplete="new-password"
          required
          :disabled="session.busy.value || session.status.value !== 'ready'"
          :aria-invalid="!!issue?.fields.new_password1?.length"
          :aria-describedby="
            issue?.fields.new_password1?.length ? 'new-password1-errors' : undefined
          "
        />
        <ul v-if="issue?.fields.new_password1?.length" id="new-password1-errors">
          <li v-for="message in issue.fields.new_password1" :key="message">{{ message }}</li>
        </ul>
        <label for="reset-password2">Confirm new password</label>
        <input
          id="reset-password2"
          v-model="password2"
          name="new_password2"
          type="password"
          autocomplete="new-password"
          required
          :disabled="session.busy.value || session.status.value !== 'ready'"
          :aria-invalid="!!issue?.fields.new_password2?.length"
          :aria-describedby="
            issue?.fields.new_password2?.length ? 'new-password2-errors' : undefined
          "
        />
        <ul v-if="issue?.fields.new_password2?.length" id="new-password2-errors">
          <li v-for="message in issue.fields.new_password2" :key="message">{{ message }}</li>
        </ul>
        <button type="submit" :disabled="session.busy.value || session.status.value !== 'ready'">
          Set new password
        </button>
        <p v-if="session.activeAction.value === 'reset-confirm'" role="status">
          Resetting password…
        </p>
      </form>
    </template>
    <RouterLink v-if="phase !== 'complete'" class="action-link" :to="{ name: 'password-reset' }"
      >Request a new reset link</RouterLink
    >
  </section>
</template>
