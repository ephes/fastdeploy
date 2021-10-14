<script setup lang="ts">
import Message from './Message.vue';

defineProps<{ messages: Message[] }>();
defineEmits(['send']);
</script>

<template>
  <div>
    <h1>Live Deployment</h1>
    <button @click="$emit('send')">send message</button>
    <ul id="messages">
      <li v-for="message in messages">
          <Message :message="message" />
      </li>
    </ul>
  </div>
</template>
