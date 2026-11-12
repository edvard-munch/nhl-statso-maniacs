<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, shallowRef } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import type { SessionUser } from '../api/index.js';
import { useSession } from '../auth/session.js';
import { safeReturnLocation } from '../auth/returnLocation.js';

const session = useSession();
const route = useRoute();
const router = useRouter();
const form = reactive({ username: '', email: '', password1: '', password2: '' });
const fields = [
  { name: 'username', label: 'Username', type: 'text', autocomplete: 'username' },
  { name: 'email', label: 'Email', type: 'email', autocomplete: 'email' },
  { name: 'password1', label: 'Password', type: 'password', autocomplete: 'new-password' },
  { name: 'password2', label: 'Confirm password', type: 'password', autocomplete: 'new-password' },
] as const;
const attempted = ref(false);
const created = shallowRef<SessionUser | null>(null);
const registrationIssue = computed(() =>
  attempted.value && session.issue.value?.action === 'register' ? session.issue.value : null,
);
const signIn = computed(() => ({
  name: 'login',
  query: { returnTo: safeReturnLocation(route.query.returnTo, router) },
}));
let active = true;
async function submit() {
  if (
    session.busy.value ||
    session.status.value !== 'ready' ||
    fields.some((field) => !form[field.name])
  )
    return;
  attempted.value = true;
  try {
    const result = await session.register({ ...form });
    if (result && active) {
      created.value = result.user;
      form.username = '';
      form.email = '';
    }
  } finally {
    form.password1 = '';
    form.password2 = '';
  }
}
onBeforeUnmount(() => {
  active = false;
  for (const field of fields) form[field.name] = '';
});
</script>

<template>
  <section class="login-view" aria-labelledby="register-title">
    <h1 id="register-title">Create account</h1>
    <section v-if="created" aria-labelledby="created-title">
      <h2 id="created-title">Account created</h2>
      <p>
        Your account {{ created.username }} has been created. You have not been signed in to the new
        account.
      </p>
      <p v-if="session.user.value">You are still signed in as {{ session.user.value.username }}.</p>
      <RouterLink class="action-link" :to="signIn">Sign in to the new account</RouterLink>
    </section>
    <template v-else>
      <p v-if="session.status.value === 'loading'" role="status">Checking sign-in status…</p>
      <p v-if="session.status.value === 'error'" role="status">
        Check your session above before creating an account.
      </p>
      <p v-if="session.status.value === 'ready' && session.user.value">
        Creating another account will keep you signed in as {{ session.user.value.username }}.
      </p>
      <div v-if="registrationIssue" role="alert" class="panel">
        <p>{{ registrationIssue.message }}</p>
        <p v-if="registrationIssue.reference">Reference: {{ registrationIssue.reference }}</p>
        <ul v-if="registrationIssue.fields.non_field_errors?.length">
          <li v-for="message in registrationIssue.fields.non_field_errors" :key="message">
            {{ message }}
          </li>
        </ul>
      </div>
      <form class="login-form" @submit.prevent="submit">
        <template v-for="field in fields" :key="field.name">
          <label :for="`register-${field.name}`">{{ field.label }}</label>
          <input
            :id="`register-${field.name}`"
            v-model="form[field.name]"
            :name="field.name"
            :type="field.type"
            :autocomplete="field.autocomplete"
            required
            :disabled="session.busy.value || session.status.value !== 'ready'"
            :aria-invalid="!!registrationIssue?.fields[field.name]?.length"
            :aria-describedby="
              registrationIssue?.fields[field.name]?.length
                ? `register-${field.name}-errors`
                : undefined
            "
          />
          <ul
            v-if="registrationIssue?.fields[field.name]?.length"
            :id="`register-${field.name}-errors`"
          >
            <li v-for="message in registrationIssue.fields[field.name]" :key="message">
              {{ message }}
            </li>
          </ul>
        </template>
        <button type="submit" :disabled="session.busy.value || session.status.value !== 'ready'">
          Create account
        </button>
        <p
          v-if="session.activeAction.value === 'register' && session.status.value === 'ready'"
          role="status"
        >
          Creating account…
        </p>
      </form>
      <RouterLink class="action-link" :to="signIn">Already have an account? Sign in</RouterLink>
    </template>
  </section>
</template>
