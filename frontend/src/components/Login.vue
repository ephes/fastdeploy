<script setup lang="ts">
import { ref } from 'vue';

let username = ref('');
let password = ref('');
defineEmits(['login']);
</script>

<template>
  <div>
    <h1>Login</h1>
    <input v-model="username" placeholder="foobar" />
    <input v-model="password" type="password" />
    <button @click="$emit('login', username, password)">login</button>
    <br />
    {{ username }}
    <br />
    {{ password }}
  </div>
</template>
