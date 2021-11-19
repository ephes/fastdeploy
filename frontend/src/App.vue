<script setup lang="ts">
import { useRouter } from 'vue-router';
import { useAuth } from './stores/auth';

const router = useRouter();
const authStore = useAuth();
</script>

<template>
  <div>
    <h1>FastDeploy</h1>
    <p v-if="authStore.isAuthenticated">
      <router-link to="/">Services</router-link>|
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
