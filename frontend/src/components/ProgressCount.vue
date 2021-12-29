<script setup lang="ts">
import { computed, ComputedRef } from 'vue';
import { useDeployments } from '../stores/deployment';
import { ServiceWithId, DeploymentById } from '../typings';

const props = defineProps<{ service: ServiceWithId }>();

const deploymentStore = useDeployments();
const activeDeployments: ComputedRef<DeploymentById> = computed(() => {
  return deploymentStore.getActiveDeploymentsByService(props.service.id);
});
</script>

<template>
  <div v-for="(deployment, deploymentId) of activeDeployments" :key="deploymentId">
    id: {{ deployment.id }} progress: {{ deploymentStore.getFinishedVsAllSteps(deployment.id) }}
    <router-link
      :to="{ name: 'deployment-detail', params: { id: deployment.id } }"
    >live</router-link>
  </div>
</template>
