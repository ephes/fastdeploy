<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { useDeployments } from '../stores/deployment';
import { useSteps } from '../stores/step';
import { useServices } from '../stores/service';
import { rememberSession } from '../stores/session';
import { formatDateTime, formatDuration } from '../format';
import { useNow } from '../useNow';
import Step from './Step.vue';

const route = useRoute();
const deploymentId = computed(() => Number(route.params.id));
const deploymentStore = useDeployments();
const deployment = computed(() => deploymentStore.deployments[deploymentId.value]);
const stepsStore = useSteps();
const serviceStore = useServices();
const now = useNow(1000);
const steps = computed(() => stepsStore.getStepsByDeployment(deploymentId.value));
const stepsVisible = computed(() => stepsStore.inventoryComplete[deploymentId.value] || (!loading.value && !error.value));
/** Overall state as far as the loaded deployment and its steps tell. */
const state = computed(() => {
  if (!deployment.value) return null;
  if (steps.value.some(step => step.state === 'failure')) return { name: 'failure', label: 'Failed' };
  if (!deployment.value.finished) return { name: 'running', label: 'Running' };
  // Only an inventory this page loaded after the deployment had finished vouches for all steps.
  if (verifiedDeploymentId.value === deploymentId.value && !loading.value && !error.value
      && steps.value.length && steps.value.every(step => step.state === 'success')) return { name: 'success', label: 'Succeeded' };
  return { name: 'finished', label: 'Finished' };
});
const finishedSteps = computed(() => steps.value.filter(step => step.finished).length);
/** The deployment whose steps were loaded completely after it had finished. */
const verifiedDeploymentId = ref<number | null>(null);
const loading = ref(false);
const error = ref('');
let refresh: AbortController | undefined;

async function fetchSteps() {
  const id = deploymentId.value;
  refresh?.abort();
  const controller = new AbortController();
  refresh = controller;
  const isCurrentSession = rememberSession();
  const ownsRefresh = () => !controller.signal.aborted && deploymentId.value === id && isCurrentSession();
  loading.value = true;
  error.value = '';
  verifiedDeploymentId.value = null;
  const finishedBefore = !!deploymentStore.deployments[id]?.finished;
  try {
    await stepsStore.fetchStepsFromDeployment(id, ownsRefresh, controller.signal);
    if (ownsRefresh() && finishedBefore && stepsStore.inventoryComplete[id]) verifiedDeploymentId.value = id;
  } catch {
    if (ownsRefresh()) error.value = 'Could not load deployment steps. Try again.';
  } finally {
    if (ownsRefresh()) loading.value = false;
    if (refresh === controller) refresh = undefined;
  }
}
watch(deploymentId, (id) => {
  deploymentStore.displayedDeploymentId = id;
  deploymentStore.pruneHistory();
  void fetchSteps();
}, { immediate: true });
onBeforeUnmount(() => {
  refresh?.abort();
  deploymentStore.displayedDeploymentId = null;
  deploymentStore.pruneHistory();
});
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>Deployment ID: {{ deploymentId }}</h1>
        <p v-if="deployment" class="sub">
          <router-link :to="{ path: '/deployments', query: { serviceId: deployment.serviceId } }">{{
            serviceStore.services[deployment.serviceId]?.name ?? `service ${deployment.serviceId}`
          }}</router-link>
        </p>
      </div>
      <span v-if="state" class="badge state" :class="state.name">{{ state.label }}</span>
    </div>
    <dl v-if="deployment" class="facts panel">
      <div>
        <dt>Started</dt>
        <dd>{{ formatDateTime(deployment.started) }}</dd>
      </div>
      <div v-if="deployment.finished">
        <dt>Finished</dt>
        <dd>{{ formatDateTime(deployment.finished) }}</dd>
      </div>
      <div>
        <dt>{{ deployment.finished ? 'Took' : 'Running for' }}</dt>
        <dd class="num">{{ formatDuration(deployment.started, deployment.finished ?? new Date(now)) }}</dd>
      </div>
      <div>
        <dt>Started by</dt>
        <dd>{{ deployment.user }} <span class="muted">via {{ deployment.origin }}</span></dd>
      </div>
    </dl>
    <p v-else-if="!loading && !error" class="notice">Deployment not found in loaded history.</p>
    <p v-if="loading" role="status">Loading steps…</p>
    <div v-else-if="error" role="alert">{{ error }} <button @click="fetchSteps">Retry</button></div>
    <div v-if="stepsVisible && steps.length" class="progress">
      <div class="segments" :class="{ dense: steps.length > 40 }" aria-hidden="true">
        <i v-for="step of steps" :key="step.id" :class="step.state"></i>
      </div>
      <p class="muted num">{{ finishedSteps }} of {{ steps.length }} steps finished</p>
    </div>
    <transition-group
      v-if="stepsVisible"
      :key="deploymentId" name="list" tag="div" class="steps"
    >
      <div v-for="step of steps" :key="step.id" class="list-step">
        <step :step="step" />
      </div>
    </transition-group>
  </div>
</template>
<style scoped>
.state { font-size: 0.875rem; padding: 0.2rem 0.8rem; }

.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
  gap: 1rem 1.5rem;
  margin: 0 0 1.25rem;
  padding: 1rem 1.25rem;
}
.facts dt { color: var(--muted); font-size: 0.8125rem; }
.facts dd { margin: 0.1rem 0 0; font-weight: 550; overflow-wrap: anywhere; }
.facts dd .muted { font-weight: 400; }

[role="status"], [role="alert"], .notice { margin-bottom: 1.25rem; }
[role="alert"] button { margin-left: 0.6rem; }

/* One segment per step, in the order the steps run. */
.progress { margin-bottom: 1.25rem; }
.segments {
  display: flex;
  gap: 3px;
  margin-bottom: 0.4rem;
  overflow: hidden;
}
/* Too many steps for gaps: one continuous strip. */
.segments.dense { gap: 0; }
.segments.dense i { border-radius: 0; }
.segments i {
  flex: 1;
  min-width: 0;
  height: 0.5rem;
  border-radius: 2px;
  background: var(--line);
  transition: background-color 0.3s;
}
.segments .success { background: var(--ok); }
.segments .failure { background: var(--fail); }
.segments .running {
  background: var(--run-fill);
  animation: pulse 1.6s ease-in-out infinite;
}
.progress p { font-size: 0.875rem; }

/* The rail of a step ends at the last one. */
.list-step:last-child :deep(.step::before) { display: none; }

.list-enter-active, .list-leave-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.list-enter-from, .list-leave-to { opacity: 0; transform: translateY(8px); }
</style>
