<script setup lang="ts">
import { inject } from 'vue';
import { useRouter } from 'vue-router';
import { useAuth } from '../stores/auth';

const router = useRouter();
const authStore = useAuth();

const websocketClient = inject('websocketClient');
console.log("websocketClient from login: ", websocketClient);

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
    {{ username }}
  </div>
</template>
