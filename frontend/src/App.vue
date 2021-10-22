<script setup lang="ts">
// This starter template is using Vue 3 <script setup> SFCs
// Check out https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup
import { ref, inject } from 'vue';
import { useRouter } from 'vue-router';
import { getCurrentInstance } from 'vue';
import Deployment from './components/Deployment.vue';
import Login from './components/Login.vue';

const app = getCurrentInstance();
const router = useRouter();
const client: any = inject('client');
console.log('client: ', client);
console.log('is authenticated: ', client.isAuthenticated.value);

// dunno why this is necessary FIXME
const messages = client.messages;
const isAuthenticated = client.isAuthenticated;

// function navigateToHello() {
//   console.log('pressed navigate to hello: ', router);
//   router.push({ name: 'hello', params: { msg: 'foo bar baz' } });
// }
</script>

<template>
  <div>
    <h1>App Component</h1>
  <!-- <div v-if="!isAuthenticated">
    <Login @login="client.login" />
  </div>
  <div v-else>
  <Deployment
    :messages="messages"
    @send="client.startDeployment()"
  />
  </div> -->
    <p v-if="isAuthenticated">
      <router-link to="/">Home</router-link> |
      <router-link to="/login">Login</router-link> |
      <router-link to="/hello">Hello</router-link> |
      <router-link to="/deployment">Deployment</router-link>
    </p>
    <p v-else>
      <Login @login="client.login" />
    </p>
    <router-view @send="client.startDeployment()"></router-view>
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
