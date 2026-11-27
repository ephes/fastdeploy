<script setup lang="ts">
import { onBeforeUnmount, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useServices } from '../stores/service';
import { DeploymentServiceChangedError, useDeployments } from '../stores/deployment';
import { rememberSession } from '../stores/session';
import ProgressCount from './ProgressCount.vue';

const serviceStore = useServices();
const deploymentStore = useDeployments();
const router = useRouter();
let viewActive = true;
onBeforeUnmount(() => { viewActive = false; });
const pendingStarts = reactive<Record<number, boolean>>({});
const startErrors = reactive<Record<number, string>>({});
const startSelectionError = ref('');

async function deleteService(id: number, name: string) {
  if (serviceStore.pendingDeletes.has(id)) return;
  if (!window.confirm(`Delete service "${name}" and its deployment history?`)) return;
  await serviceStore.deleteService(id);
}

async function forceSync() {
  if (serviceStore.syncPending) return;
  const refusal = serviceStore.syncRefusal;
  if (!refusal?.wouldDelete.length) return;
  const names = refusal.wouldDelete.join(", ");
  if (window.confirm(`Force the services sync? This can delete ${names} together with their deployment history.`)) {
    await serviceStore.syncServices(refusal.confirmation);
  }
}

async function startDeployment(id: number, serviceName: string) {
  if (pendingStarts[id]) return;
  pendingStarts[id] = true;
  startErrors[id] = '';
  startSelectionError.value = '';
  const isCurrentSession = rememberSession();
  const launchRoute = router.currentRoute.value;
  const ownsView = () => viewActive && router.currentRoute.value === launchRoute && isCurrentSession();
  try {
    const deployment = await deploymentStore.startDeployment(serviceName, undefined, message => {
      if (ownsView()) startErrors[id] = `Could not start ${serviceName}: ${message}`;
    });
    if (!ownsView()) return;
    if (!deployment) {
      if (!startErrors[id]) startErrors[id] = `Could not obtain a deployment token for ${serviceName}. Check permissions and retry.`;
      return;
    }
    await router.push({ name: 'deployment-detail', params: { id: deployment.id } });
  } catch (error: any) {
    if (!ownsView()) return;
    if (error instanceof DeploymentServiceChangedError) {
      startSelectionError.value = `Could not start ${serviceName}: ${error.message}`;
    } else if (error?.response?.status === 409) {
      // 409 covers a running deployment and an orphan backlog; without a readable reason say neither.
      const detail = error.body?.detail;
      startErrors[id] = detail?.code === 'orphan_backlog'
        ? `Open deployment history to reconcile orphaned deployments, then retry starting ${serviceName}.`
        : Number.isInteger(detail?.deployment_id)
          ? `A deployment is already running for ${serviceName}. Check its history before retrying.`
          : `The server refused to start ${serviceName}. Check its history before retrying.`;
    } else {
      startErrors[id] = `Could not confirm deployment start for ${serviceName}. Check its history before retrying.`;
    }
  } finally {
    delete pendingStarts[id];
  }
}
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>Services</h1>
        <p v-if="serviceStore.getAvailableServiceNames.length" class="sub">
          Not added yet: {{ serviceStore.getAvailableServiceNames.join(", ") }}
        </p>
      </div>
      <div v-if="serviceStore.getAvailableServiceNames.length">
        <button :disabled="serviceStore.syncPending" title="Read the service definitions from disk again"
          @click="serviceStore.syncServices()">sync</button>
      </div>
    </div>
    <div class="notices">
      <p v-if="serviceStore.serviceNamesLoading" role="status">Loading service names…</p>
      <p v-if="serviceStore.serviceNamesError" role="alert">
        {{ serviceStore.serviceNamesError }}
        <button @click="serviceStore.fetchServiceNames()">Retry service names</button>
      </p>
      <div v-if="serviceStore.syncRefusal" class="sync-refusal" role="alert">
        <p class="notice-title">Services sync refused: {{ serviceStore.syncRefusal.message }}</p>
        <p v-if="serviceStore.syncRefusal.wouldDelete.length">
          Services that would be deleted: <strong>{{ serviceStore.syncRefusal.wouldDelete.join(", ") }}</strong>
        </p>
        <div class="notice-actions">
          <button class="quiet" @click="serviceStore.syncRefusal = null">dismiss</button>
          <button v-if="serviceStore.syncRefusal.wouldDelete.length" class="danger-solid force" :disabled="serviceStore.syncPending" @click="forceSync()">force sync</button>
          <button v-else :disabled="serviceStore.syncPending" @click="serviceStore.syncServices()">retry sync</button>
        </div>
      </div>
      <div v-if="serviceStore.syncErrorMessage" class="sync-error" role="alert">
        {{ serviceStore.syncErrorMessage }}
      </div>
      <div v-if="serviceStore.syncReceipt" class="sync-receipt notice ok" role="status">
        <p class="notice-title">Services synced.</p>
        <p v-if="serviceStore.syncReceipt.updated.length">Updated {{ serviceStore.syncReceipt.updated.join(", ") }}</p>
        <p v-if="serviceStore.syncReceipt.deleted.length">Deleted {{ serviceStore.syncReceipt.deleted.join(", ") }}</p>
        <template v-if="serviceStore.syncReceipt.skipped.length">
          <p>Skipped services</p>
          <ul>
            <li v-for="service in serviceStore.syncReceipt.skipped" :key="service.name">
              {{ service.name }} · {{ service.reason }}
            </li>
          </ul>
        </template>
      </div>
      <p v-if="serviceStore.servicesError" role="alert">
        {{ serviceStore.servicesError }}
        <button @click="serviceStore.fetchServices()">Retry services</button>
      </p>
      <div v-if="serviceStore.serviceTokenErrorMessage" role="alert">
        {{ serviceStore.serviceTokenErrorMessage }}
      </div>
      <p v-if="startSelectionError" role="alert">{{ startSelectionError }}</p>
    </div>
    <div class="panel">
      <table class="service-list data-table" role="table">
        <thead role="rowgroup"><tr class="head-row" role="row">
          <th role="columnheader">Service</th>
          <th role="columnheader">Activity</th>
          <th role="columnheader"><span class="sr-only">Pages</span></th>
          <th role="columnheader"><span class="sr-only">Deploy</span></th>
          <th role="columnheader"><span class="sr-only">Delete</span></th>
        </tr></thead>
        <tbody role="rowgroup"><tr v-for="service of serviceStore.getServices" :key="service.id" class="list-service" role="row">
          <td class="name" role="cell">{{ service.name }}</td>
          <td class="activity" role="cell">
            <progress-count :service="service"/>
          </td>
          <td class="pages" role="cell">
            <router-link
              :to="{ name: 'deployment-list', query: { serviceId: service.id } }"
              :aria-label="`History of ${service.name}`"
            >History</router-link>
            <router-link
              :to="{ name: 'service-detail', params: { id: service.id } }"
              :aria-label="`Service token for ${service.name}`"
            >Token</router-link>
          </td>
          <td class="deploy" role="cell">
            <button class="primary" :aria-label="`Deploy ${service.name}`" :disabled="pendingStarts[service.id]"
              @click="startDeployment(service.id, service.name)">{{ pendingStarts[service.id] ? 'Starting…' : 'deploy' }}</button>
            <p v-if="startErrors[service.id]" role="alert">{{ startErrors[service.id] }}</p>
          </td>
          <td class="delete" role="cell">
            <button class="danger" :aria-label="`Delete ${service.name}`" :disabled="serviceStore.pendingDeletes.has(service.id)"
              @click="deleteService(service.id, service.name)">{{ serviceStore.pendingDeletes.has(service.id) ? 'Deleting…' : 'delete' }}</button>
            <p v-if="serviceStore.deleteErrors[service.id]" role="alert">{{ serviceStore.deleteErrors[service.id] }}</p>
          </td>
        </tr></tbody>
      </table>
      <p v-if="!serviceStore.getServices.length && !serviceStore.servicesLoading && !serviceStore.servicesError" class="empty muted">
        No services yet.
      </p>
    </div>
  </div>
</template>
<style scoped>
.notice-title { font-weight: 600; }
.sync-receipt ul { margin: 0.25rem 0 0; padding-left: 1.2rem; }
/* Keep the destructive choice away from the harmless one. */
.sync-refusal .notice-actions { justify-content: space-between; }

.empty { padding: 1.5rem 1rem; }

.name {
  font-weight: 650;
  font-size: 1rem;
  min-width: 11rem;
  overflow-wrap: anywhere;
}
.pages { width: 1%; white-space: nowrap; }
.pages a + a { margin-left: 1.1rem; }
.deploy, .delete { text-align: right; }
.deploy { width: 1%; }
/* Delete stands apart from deploy, behind a rule of its own. */
.delete {
  width: 1%;
  padding-left: 0.75rem;
  border-left: 1px solid var(--line);
}
.list-service [role="alert"] {
  min-width: 10rem;
  margin-top: 0.5rem;
  white-space: normal;
  text-align: left;
  font-size: 0.875rem;
}
.list-service:hover > td { background: var(--surface-sunk); }

@media (max-width: 65.99rem) {
  .service-list, .service-list tbody, .service-list tr, .service-list td { display: block; }
  /* Out of sight, still announced as column headers. */
  .service-list thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  /* Two lines per service: name and deploy, then the links and delete. */
  .service-list .list-service {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.15rem 1rem;
    padding: 0.7rem 1rem 0.4rem;
    border-bottom: 1px solid var(--line);
  }
  .service-list .list-service:last-child { border-bottom: 0; }
  .service-list td {
    width: auto;
    min-width: 0;
    padding: 0;
    border: 0;
  }
  .list-service:hover > td { background: none; }
  .service-list .name { order: 1; flex: 1 1 0; }
  .service-list .deploy { order: 2; flex: none; max-width: 100%; }
  .service-list .activity { order: 3; flex: 0 0 100%; }
  .service-list .pages { order: 4; flex: 1 1 0; }
  .pages a { display: inline-block; padding: 0.4rem 0; }
  /* Opposite corner from deploy, smaller and quiet. */
  .service-list .delete { order: 5; flex: none; max-width: 100%; }
  .delete button { min-height: 2rem; padding: 0.25rem 0.6rem; font-size: 0.875rem; }
  /* A cell with an error message takes a line of its own. */
  .service-list .deploy:has([role="alert"]),
  .service-list .delete:has([role="alert"]) { flex-basis: 100%; }
  .list-service [role="alert"] { min-width: 0; margin: 0.4rem 0; }
}
</style>
