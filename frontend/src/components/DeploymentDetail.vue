<script setup lang="ts">
import { inject, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import Step from './Step.vue';
import { Client, Deployment } from '../typings';

const client: Client = inject('client') as Client;
const steps = client.steps;
const route = useRoute();
const deploymentIdFromRoute = Number(route.params.id);
const deployment: Deployment | undefined = client.deployments.get(
  deploymentIdFromRoute
);

onMounted(async () => {
  await client.fetchStepsFromDeployment(deploymentIdFromRoute);
});

function getSteps() {
  return [...steps].filter(
    ([id, step]) => step.deployment_id === deploymentIdFromRoute
  );
}
</script>

<template>
  <div>
    <h1>Deployment ID: {{ $route.params.id }}</h1>
    <div v-if="deployment">
      <h2>deployment origin: {{ deployment.origin }}</h2>
    </div>
    <div v-for="[id, step] in steps" :key="id" class="list-step">
      <step :step="step" />
    </div>
  </div>
</template>
