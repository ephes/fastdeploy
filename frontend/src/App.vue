<script setup lang="ts">
// This starter template is using Vue 3 <script setup> SFCs
// Check out https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup
import { ref } from 'vue';
import { getCurrentInstance } from 'vue'
import Client from './client';
import Deployment from './components/Deployment.vue';

const app = getCurrentInstance()
const router = app.appContext.config.globalProperties.$router
const client = ref(new Client())

function navigateToHello() {
  console.log("pressed navigate to hello: ", router)
  router.push({ name: 'hello', params: { msg: "foo bar baz" } })
}

export default = {
  data: function () {
    console.log("in data function")
    return {
      greeting: 'Hello'
    }
  }
}

// const navigateToHello: () => {
//   console.log("pressed navigate to hello: ", router)
//   console.log("this is undefined? ", this)
//   // router.push({ name: 'hello', params: { msg: "foo bar baz" } })
// }
</script>

<template>
  <!-- <img alt="Vue logo" src="./assets/logo.png" /> -->
  <!-- <HelloWorld msg="Hello Vue 3 + TypeScript + Vite" /> -->
  <p>
    <router-link to="/">Go to Home</router-link>
    <br />
    <!-- <router-link to="{ name: 'user', params: { msg: 'fido' }}">Go to Hello</router-link> -->
  </p>
  <button @click="navigateToHello()">Got to Hello</button>
  <Deployment :client="client" :messages="client.messages" @send="client.startDeployment()" />
  <h1>Wut?</h1>
  <router-view></router-view>
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
