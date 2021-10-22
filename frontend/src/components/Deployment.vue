<script setup lang="ts">
import Message from './Message.vue';

defineProps<{ messages: any[] }>();
defineEmits(['send']);
</script>

<template>
  <div>
    <h1>Live Deployment</h1>
    <button @click="$emit('send')">start deployment</button>
    <transition-group name="list" tag="p">
      <div v-for="message in messages.slice().reverse()" :key="message.name" class="list-message">
        <Message :message="message" />
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.list-message {
  margin-right: 10px;
}
.list-enter-active,
.list-leave-active {
  transition: all 1s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateY(30px);
}
</style>
