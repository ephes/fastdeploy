<script setup lang="ts">
import { inject, onMounted, computed, reactive } from 'vue';
import { useRoute } from 'vue-router';
import Step from './Step.vue';
import { Client, Deployment } from '../typings';

const route = useRoute();
const deploymentIdFromRoute = Number(route.params.id);

const client: Client = inject('client') as Client;
const deployment: Deployment | undefined = client.deployments.get(
  deploymentIdFromRoute
);

const steps = computed(() => {
  const filteredSteps = [...client.steps].filter(
    ([id, step]) => step.deployment_id === deploymentIdFromRoute
  );
  console.log('called computed..');
  return filteredSteps;
});

onMounted(async () => {
  // top level await does not quite work
  await client.fetchStepsFromDeployment(deploymentIdFromRoute);
});
</script>

<template>
  <div>
    <h1>Deployment ID: {{ deploymentIdFromRoute }}</h1>
    <div v-if="deployment">
      <h2>deployment origin: {{ deployment.origin }}</h2>
    </div>
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
