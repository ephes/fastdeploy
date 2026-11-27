<script setup lang="ts">
import { useRoute } from 'vue-router';
import { computed, watch } from 'vue';

import { useDeployments } from '../stores/deployment';
import { useServices } from '../stores/service';
import { formatDateTime, formatDuration, formatRelative } from '../format';
import { useNow } from '../useNow';

const deploymentStore = useDeployments();
const serviceStore = useServices();
const now = useNow(30_000);

const route = useRoute();
const serviceId = computed(() => {
  const value = route.query.serviceId;
  const id = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : NaN;
  return Number.isSafeInteger(id) && id > 0 ? id : undefined;
});
watch(serviceId, (id) => deploymentStore.fetchDeployments(id), { immediate: true });
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>Deployments</h1>
        <p v-if="serviceId !== undefined" class="sub">
          Only {{ serviceStore.services[serviceId]?.name ?? `service ${serviceId}` }}.
          <router-link :to="{ name: 'deployment-list' }">Show all services</router-link>
        </p>
      </div>
    </div>
    <div class="panel">
      <table class="data-table history" role="table">
        <thead role="rowgroup"><tr role="row">
          <th role="columnheader">Deployment</th>
          <th role="columnheader">Service</th>
          <th role="columnheader">Started</th>
          <th role="columnheader">Took</th>
          <th role="columnheader">Started by</th>
          <th role="columnheader"><span class="sr-only">Details</span></th>
        </tr></thead>
        <tbody role="rowgroup"><tr v-for="deployment of deploymentStore.historyDeployments" :key="deployment.id" role="row">
          <td class="id" role="cell">
            <span class="num">#{{ deployment.id }}</span>
            <span v-if="!deployment.finished" class="badge running">Running</span>
          </td>
          <td class="service" role="cell">{{ serviceStore.services[deployment.serviceId]?.name ?? `service ${deployment.serviceId}` }}</td>
          <td class="started" role="cell" :title="formatDateTime(deployment.started)">{{ formatRelative(deployment.started, now) }}</td>
          <td class="took num" role="cell">{{ formatDuration(deployment.started, deployment.finished) }}</td>
          <td class="by" role="cell">{{ deployment.user }} <span class="muted">via {{ deployment.origin }}</span></td>
          <td class="link" role="cell">
            <router-link
              :to="{ name: 'deployment-detail', params: { id: deployment.id } }"
              :aria-label="`details for ${deployment.id}`"
              >Details</router-link
            >
          </td>
        </tr></tbody>
      </table>
      <p v-if="!deploymentStore.historyDeployments.length && !deploymentStore.historyLoading && !deploymentStore.historyError"
        class="empty muted">No deployments yet.</p>
    </div>
    <div class="more">
      <p v-if="deploymentStore.historyError" role="alert">{{ deploymentStore.historyError }}</p>
      <button v-if="deploymentStore.historyError" :disabled="deploymentStore.historyLoading"
        @click="deploymentStore.fetchDeployments(serviceId)">Retry history</button>
      <button v-else-if="deploymentStore.historyHasMore" :disabled="deploymentStore.historyLoading"
        @click="deploymentStore.fetchDeployments(serviceId, true)">
        {{ deploymentStore.historyLoading ? 'Loading…' : 'Load more' }}
      </button>
    </div>
  </div>
</template>
<style scoped>
.empty { padding: 1.5rem 1rem; }
.id { white-space: nowrap; font-weight: 600; }
.id .badge { margin-left: 0.6rem; }
.service { font-weight: 600; overflow-wrap: anywhere; }
.started, .took { white-space: nowrap; }
.by { overflow-wrap: anywhere; }
.link { width: 1%; text-align: right; }
.history tbody tr:hover > td { background: var(--surface-sunk); }
.more { margin-top: 1rem; }
.more [role="alert"] { margin-bottom: 0.75rem; }

@media (max-width: 46rem) {
  .history, .history tbody, .history tr, .history td { display: block; }
  /* Out of sight, still announced as column headers. */
  .history thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .history tbody tr {
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "service id"
      "started took"
      "by link";
    align-items: baseline;
    gap: 0.2rem 1rem;
    padding: 0.8rem 1rem;
    border-bottom: 1px solid var(--line);
  }
  .history tbody tr:last-child { border-bottom: 0; }
  .history td { width: auto; padding: 0; border: 0; }
  .history tbody tr:hover > td { background: none; }
  .service { grid-area: service; font-size: 1rem; }
  .id { grid-area: id; text-align: right; font-weight: 500; color: var(--muted); }
  .id .badge { margin: 0 0 0 0.4rem; }
  .started { grid-area: started; color: var(--muted); }
  .took { grid-area: took; text-align: right; color: var(--muted); }
  .by { grid-area: by; font-size: 0.875rem; }
  .link { grid-area: link; }
  .link a { display: inline-block; padding: 0.3rem 0 0.1rem; }
}
</style>
