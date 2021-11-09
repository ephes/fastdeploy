<script setup lang="ts">
import { inject } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const client: any = inject('client');

const clientErrorMessage = client.errorMessage
</script>

<template>
  <div>
    <h1>FastDeploy</h1>
    <p v-if="clientErrorMessage">Client-Error: {{ clientErrorMessage }}</p>
    <p v-if="client.isAuthenticated.value">
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
