<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useDeployments } from '../stores/deployment';
import { useSteps } from '../stores/step';
import { rememberSession } from '../stores/session';
import Step from './Step.vue';

const route = useRoute();
const deploymentId = computed(() => Number(route.params.id));
const deploymentStore = useDeployments();
const deployment = computed(() => deploymentStore.deployments[deploymentId.value]);
const stepsStore = useSteps();
const loading = ref(false);
const error = ref('');
let generation = 0;

async function fetchSteps() {
  const id = deploymentId.value;
  const current = ++generation;
  const isCurrentSession = rememberSession();
  loading.value = true;
  error.value = '';
  try {
    await stepsStore.fetchStepsFromDeployment(id);
  } catch {
    if (current === generation && isCurrentSession()) error.value = 'Could not load deployment steps. Try again.';
  } finally {
    if (current === generation && isCurrentSession()) loading.value = false;
  }
}
watch(deploymentId, fetchSteps, { immediate: true, flush: 'sync' });
</script>

<template>
  <div>
    <h1>Deployment ID: {{ deploymentId }}</h1>
    <div v-if="deployment">
      <h2>deployment origin: {{ deployment.origin }}</h2>
      <h2>deployment started: {{ deployment.started }}</h2>
      <h2>deployment finished: {{ deployment.finished }}</h2>
    </div>
    <p v-else-if="!loading && !error">Deployment not found in loaded history.</p>
    <p v-if="loading" role="status">Loading steps…</p>
    <div v-else-if="error" role="alert">{{ error }} <button @click="fetchSteps">Retry</button></div>
    <transition-group v-else name="list" tag="div">
      <div v-for="step of stepsStore.getStepsByDeployment(deploymentId)" :key="step.id" class="list-step">
        <step :step="step" />
      </div>
    </transition-group>
  </div>
</template>
<style scoped>
.list-step { margin-right: 10px; }
.list-enter-active, .list-leave-active { transition: all 1s ease; }
.list-enter-from, .list-leave-to { opacity: 0; transform: translateY(30px); }
</style>
