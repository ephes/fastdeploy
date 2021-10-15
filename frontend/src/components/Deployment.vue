<script setup lang="ts">
import Message from './Message.vue';

defineProps<{ messages: Message[] }>();
defineEmits(['send']);
</script>

<template>
  <div>
    <h1>Live Deployment</h1>
    <button @click="$emit('send')">start deployment</button>
    <div id="messages">
      <div v-for="message in messages">
          <Message :message="message" />
      </div>
    </div>
  </div>
</template>
