<script setup lang="ts">
import { reactive } from 'vue';
import { useRouter } from 'vue-router';

import { useServices } from '../stores/service';
import { useDeployments } from '../stores/deployment';
import { rememberSession } from '../stores/session';
import ProgressCount from './ProgressCount.vue';

const serviceStore = useServices();
const deploymentStore = useDeployments();
const router = useRouter();
const pendingDeletes = reactive<Record<number, boolean>>({});
const pendingStarts = reactive<Record<number, boolean>>({});
const startErrors = reactive<Record<number, string>>({});

async function deleteService(id: number, name: string) {
  if (pendingDeletes[id]) return;
  if (!window.confirm(`Delete service "${name}" and its deployment history?`)) return;
  pendingDeletes[id] = true;
  try {
    await serviceStore.deleteService(id);
  } finally {
    delete pendingDeletes[id];
  }
}

async function forceSync() {
  const refusal = serviceStore.syncRefusal;
  const count = refusal ? refusal.wouldDelete.length : 0;
  const confirmed = window.confirm(
    `Force the services sync? This deletes ${count} service(s) together with their deployment history.`
  );
  if (confirmed) {
    await serviceStore.syncServices(true);
  }
}

async function startDeployment(id: number, serviceName: string) {
  if (pendingStarts[id]) return;
  pendingStarts[id] = true;
  startErrors[id] = '';
  const isCurrentSession = rememberSession();
  try {
    const deployment = await deploymentStore.startDeployment(serviceName, undefined, message => {
      if (isCurrentSession()) startErrors[id] = `Could not start ${serviceName}: ${message}`;
    });
    if (!isCurrentSession()) return;
    if (!deployment) {
      if (!startErrors[id]) startErrors[id] = `Could not obtain a deployment token for ${serviceName}. Check permissions and retry.`;
      return;
    }
    await router.push({ name: 'deployment-detail', params: { id: deployment.id } });
  } catch (error: any) {
    if (!isCurrentSession()) return;
    startErrors[id] = error?.response?.status === 409
      ? `A deployment is already running for ${serviceName}. Check its history before retrying.`
      : `Could not confirm deployment start for ${serviceName}. Check its history before retrying.`;
  } finally {
    delete pendingStarts[id];
  }
}
</script>

<template>
  <div>
    <h1>Services</h1>
    <div v-if="serviceStore.getAvailableServiceNames.length">
      <button @click="serviceStore.syncServices()">sync</button>
    </div>
    <div v-if="serviceStore.syncRefusal" class="sync-refusal" role="alert">
      <p>Services sync refused: {{ serviceStore.syncRefusal.message }}</p>
      <p v-if="serviceStore.syncRefusal.wouldDelete.length">
        Services that would be deleted: {{ serviceStore.syncRefusal.wouldDelete.join(", ") }}
      </p>
      <button @click="forceSync()">force sync</button>
      <button @click="serviceStore.syncRefusal = null">dismiss</button>
    </div>
    <div v-if="serviceStore.syncErrorMessage" class="sync-error" role="alert">
      {{ serviceStore.syncErrorMessage }}
    </div>
    <div v-if="serviceStore.serviceTokenErrorMessage" role="alert">
      {{ serviceStore.serviceTokenErrorMessage }}
    </div>
    <br />
    <table class="service-list">
      <tr>
        <th>name</th>
        <th>generate service token</th>
        <th>progress - finished vs all</th>
        <th>deployments</th>
        <th>deploy</th>
        <th>delete</th>
      </tr>
      <tr v-for="service of serviceStore.getServices" :key="service.id" class="list-service">
        <td>{{ service.name }}</td>
        <td>
          <router-link
            :to="{ name: 'service-detail', params: { id: service.id } }"
          >{{ service.name }}</router-link>
        </td>
        <td>
          <progress-count :service="service"/>
        </td>
        <td>
          <router-link
            :to="{ name: 'deployment-list', query: { serviceId: service.id } }"
          >{{ service.name }}</router-link>
        </td>
        <td>
          <button :aria-label="`Deploy ${service.name}`" :disabled="pendingStarts[service.id]"
            @click="startDeployment(service.id, service.name)">{{ pendingStarts[service.id] ? 'Starting…' : 'deploy' }}</button>
          <p v-if="startErrors[service.id]" role="alert">{{ startErrors[service.id] }}</p>
        </td>
        <td>
          <button :aria-label="`Delete ${service.name}`" :disabled="pendingDeletes[service.id]"
            @click="deleteService(service.id, service.name)">{{ pendingDeletes[service.id] ? 'Deleting…' : 'delete' }}</button>
          <p v-if="serviceStore.deleteErrors[service.id]" role="alert">{{ serviceStore.deleteErrors[service.id] }}</p>
        </td>
      </tr>
    </table>
  </div>
</template>
<style scoped>
.service-list {
  padding-top: 2em;
  margin: auto;
}
button {
  margin-left: 1em;
}
th,td {
  padding: 0.5em;
}
.sync-refusal,
.sync-error {
  color: #b00020;
}
</style>
