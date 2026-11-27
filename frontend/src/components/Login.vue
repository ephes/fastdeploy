<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuth } from '../stores/auth';

const router = useRouter();
const authStore = useAuth();
const pending = ref(false);
authStore.router = router;

async function login() {
  if (pending.value) return;
  pending.value = true;
  authStore.errorMessage = null;
  try {
    await authStore.login();
    if (authStore.isAuthenticated) await router.push('/');
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <div class="login">
    <h1>Log in</h1>
    <form class="panel" @submit.prevent="login" :aria-busy="pending">
      <p v-if="authStore.errorMessage" id="login-error" role="alert">{{ authStore.errorMessage }}</p>
      <div class="field">
        <label for="username">Username</label>
        <input id="username" name="username" v-model="authStore.username" autocomplete="username" required
          autocapitalize="off" spellcheck="false"
          :aria-describedby="authStore.errorMessage ? 'login-error' : undefined" />
      </div>
      <div class="field">
        <label for="password">Password</label>
        <input id="password" name="password" v-model="authStore.password" type="password" autocomplete="current-password" required
          :aria-describedby="authStore.errorMessage ? 'login-error' : undefined" />
      </div>
      <button class="primary" type="submit" :disabled="pending">{{ pending ? 'Logging in…' : 'Login' }}</button>
    </form>
  </div>
</template>
<style scoped>
.login {
  max-width: 22rem;
  margin: clamp(1rem, 10vh, 5rem) auto 0;
}
h1 { margin-bottom: 1rem; }
form { padding: 1.25rem; }
.field, [role="alert"] { margin-bottom: 1rem; }
button { width: 100%; min-height: 2.5rem; margin-top: 0.25rem; }
</style>
