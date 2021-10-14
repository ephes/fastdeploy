<script setup lang="ts">

const props = defineProps<{ messages: any }>();
defineEmits(['send']);
</script>

<template>
  <div>
    <h1>View deployment</h1>
    <p>Some paragraph..</p>
    <button @click="$emit('send')">send message</button>
    <ul id="messages">
      <li v-for="message in props.messages" :key="message.message">
        {{ message.message }}
      </li>
    </ul>
  </div>
</template>
