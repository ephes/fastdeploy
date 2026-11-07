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
  <div>
    <h1>Login</h1>
    <form @submit.prevent="login" :aria-busy="pending">
      <p v-if="authStore.errorMessage" id="login-error" role="alert">Login-Error: {{ authStore.errorMessage }}</p>
      <label for="username">Username</label>
      <input id="username" name="username" v-model="authStore.username" autocomplete="username" required
        :aria-describedby="authStore.errorMessage ? 'login-error' : undefined" />
      <label for="password">Password</label>
      <input id="password" name="password" v-model="authStore.password" type="password" autocomplete="current-password" required
        :aria-describedby="authStore.errorMessage ? 'login-error' : undefined" />
      <button type="submit" :disabled="pending">{{ pending ? 'Logging in…' : 'Login' }}</button>
    </form>
  </div>
</template>
<style scoped>
input, button { margin-left: 1em; }
</style>
