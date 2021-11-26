<script setup lang="ts">
import { inject, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useDeployments } from '../stores/deployment';
import { useSteps } from '../stores/step';
import Step from './Step.vue';
import { Deployment, Step as StepType } from '../typings';

const route = useRoute();
const deploymentIdFromRoute = Number(route.params.id);

const deploymentStore = useDeployments();
const deployment: Deployment = deploymentStore.deployments[deploymentIdFromRoute];

const stepsStore = useSteps();
stepsStore.fetchStepsFromDeployment(deploymentIdFromRoute);
</script>

<template>
  <div>
    <h1>Deployment ID: {{ deploymentIdFromRoute }}</h1>
    <div v-if="deployment">
      <h2>deployment origin: {{ deployment.origin }}</h2>
    </div>
    <transition-group name="list" tag="p">
      <div v-for="step of stepsStore.getStepByDeployment(deploymentIdFromRoute)" :key="step.id" class="list-step">
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
