<script setup lang="ts">
import { inject } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const client: any = inject('client');

// dunno why this is necessary FIXME
const isAuthenticated = client.isAuthenticated;
const clientErrorMessage = client.errorMessage
</script>

<template>
  <div>
    <h1>FastDeploy</h1>
    <p v-if="clientErrorMessage">Client-Error: {{ clientErrorMessage }}</p>
    <p v-if="isAuthenticated">
      <router-link to="/">Services</router-link> |
      <router-link to="/deployments">Deployments</router-link>
    </p>
    <router-view></router-view>
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
