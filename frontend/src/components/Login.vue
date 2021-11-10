<script setup lang="ts">
import { ref, inject } from 'vue';
import { Client } from '../typings';
import { useRouter } from 'vue-router';

const router = useRouter();
const client: Client = inject('client') as Client;

let username = ref('');
let password = ref('');

async function login() {
  await client.login(username.value, password.value)
  if (client.isAuthenticated) {
    // redirect to home after successful login
    router.push("/")
  }
}
</script>

<template>
  <div>
    <h1>Login</h1>
    <input v-model="username" placeholder="foobar" />
    <input v-model="password" type="password" @keyup.enter="login()"/>
    <button @click="login()">login</button>
    <br />
    {{ username }}
  </div>
</template>
