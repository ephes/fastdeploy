<script setup lang="ts">
import { inject } from 'vue';
import Step from './Step.vue';

const client: any = inject("client");
const steps = client.steps;
defineEmits(['send']);
</script>

<template>
  <div>
    <h1>Live Deployment</h1>
    <button @click="$emit('send')">start deployment</button>
    Number of steps: {{ steps.length }}
    <transition-group name="list" tag="p">
      <div v-for="[id, step] in steps" :key="id" class="list-step">
        <step :step="step" />
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.list-step {
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
