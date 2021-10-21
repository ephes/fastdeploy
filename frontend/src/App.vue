<script setup lang="ts">
// This starter template is using Vue 3 <script setup> SFCs
// Check out https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup
import { ref } from 'vue';
import { getCurrentInstance } from 'vue'
import Client from './client';
import Deployment from './components/Deployment.vue';
import Login from './components/Login.vue';

const app = getCurrentInstance()
const router = app.appContext.config.globalProperties.$router
const client = ref(new Client())

function navigateToHello() {
  console.log("pressed navigate to hello: ", router)
  router.push({ name: 'hello', params: { msg: "foo bar baz" } })
}
</script>

<template>
  <div v-if="client.is_authenticated">
      <Deployment :client="client" :messages="client.messages" @send="client.startDeployment()" />
  </div>
  <div v-else>
    <Login @login="client.login"/>
  </div>
  <br />
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
