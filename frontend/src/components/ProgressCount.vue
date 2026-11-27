<script setup lang="ts">
import { computed, ComputedRef } from 'vue';
import { useDeployments } from '../stores/deployment';
import { ServiceWithId, Deployment, DeploymentById } from '../typings';
import { formatRelative, formatDateTime } from '../format';
import { useNow } from '../useNow';

const props = defineProps<{ service: ServiceWithId }>();

const deploymentStore = useDeployments();
const now = useNow(30_000);
const activeDeployments: ComputedRef<DeploymentById> = computed(() => {
  return deploymentStore.getActiveDeploymentsByService(props.service.id);
});
const hasActive = computed(() => {
  for (const _id in activeDeployments.value) return true;
  return false;
});
/** The newest finished deployment of this service the page already knows about. */
const lastFinished: ComputedRef<Deployment | null> = computed(() => {
  let last: Deployment | null = null;
  for (const id in deploymentStore.deployments) {
    const deployment = deploymentStore.deployments[id];
    if (deployment.serviceId === props.service.id && deployment.finished && (!last || deployment.id > last.id)) {
      last = deployment;
    }
  }
  return last;
});

function percent([finished, all]: [number, number]): number {
  return all > 0 ? Math.round((finished / all) * 100) : 0;
}
</script>

<template>
  <div v-for="(deployment, deploymentId) of activeDeployments" :key="deploymentId" class="run">
    <span class="badge running">Running</span>
    <span class="meter" role="progressbar" aria-valuemin="0" aria-valuemax="100"
      :aria-valuenow="percent(deploymentStore.getFinishedVsAllSteps(deployment.id))"
      :aria-label="`Progress of deployment ${deployment.id}`">
      <span :style="{ width: percent(deploymentStore.getFinishedVsAllSteps(deployment.id)) + '%' }"></span>
    </span>
    <span class="count num">
      {{ deploymentStore.getFinishedVsAllSteps(deployment.id)[0] }} of
      {{ deploymentStore.getFinishedVsAllSteps(deployment.id)[1] }} steps
    </span>
    <router-link
      :to="{ name: 'deployment-detail', params: { id: deployment.id } }"
      :aria-label="`Watch deployment ${deployment.id} live`"
    >Watch live</router-link>
  </div>
  <div v-if="!hasActive && lastFinished" class="last muted">
    Last deployment
    <router-link :to="{ name: 'deployment-detail', params: { id: lastFinished.id } }" class="num">#{{ lastFinished.id }}</router-link>
    finished
    <span :title="formatDateTime(lastFinished.finished)">{{ formatRelative(lastFinished.finished, now) }}</span>
  </div>
</template>
<style scoped>
.run {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.75rem;
}
.run + .run { margin-top: 0.4rem; }
.meter {
  flex: 1 1 5rem;
  min-width: 4rem;
  max-width: 12rem;
  height: 0.4rem;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
}
.meter > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--run-fill);
  transition: width 0.4s ease;
}
.count { color: var(--muted); font-size: 0.875rem; white-space: nowrap; }
.last { font-size: 0.875rem; }
</style>
