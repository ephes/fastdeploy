<script setup lang="ts">
import { useRouter } from 'vue-router';
import { useAuth } from '../stores/auth';

const router = useRouter();
const authStore = useAuth();

// pass router to authStore to be able to redirect to
// login when user is logged out via websocket close
authStore.router = router;

async function login() {
  await authStore.login()
  if (authStore.isAuthenticated) {
    // redirect to home after successful login
    router.push("/")
  }
}
</script>

<template>
  <div>
    <h1>Login</h1>
    <p v-if="authStore.errorMessage">Login-Error: {{ authStore.errorMessage }}</p>
    <input v-model="authStore.username" placeholder="foobar" />
    <input v-model="authStore.password" type="password" @keyup.enter="login()" />
    <button @click="login()">login</button>
    <br />
    {{ authStore.username }}
  </div>
</template>
