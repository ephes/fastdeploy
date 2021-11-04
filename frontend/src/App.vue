<script setup lang="ts">
import { inject } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const client: any = inject('client');

// dunno why this is necessary FIXME
const isAuthenticated = client.isAuthenticated;
const clientErrorMessage = client.errorMessage

async function login(username: string, password: string) {
  await client.login(username, password)
  if (client.isAuthenticated) {
    // redirect to home after successful login
    router.push("/")
  }
}
</script>

<template>
  <div>
    <h1>App Component</h1>
    <p v-if="clientErrorMessage">Client-Error: {{ clientErrorMessage }}</p>
    <p v-if="isAuthenticated">
      <router-link to="/">Services</router-link> |
      <router-link to="/hello">Hello</router-link> |
      <router-link to="/deployment">Deployment</router-link>
    </p>
    <router-view @send="client.startDeployment()" @login="login"></router-view>
  </div>
</template>

<style>
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}
</style>
