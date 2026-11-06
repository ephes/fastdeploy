<script setup lang="ts">
import { useRoute } from 'vue-router';
import { computed, watch } from 'vue';

import { useDeployments } from '../stores/deployment';

const deploymentStore = useDeployments();

const route = useRoute();
const serviceId = computed(() => Number(route.params.serviceId) || undefined);
watch(serviceId, (id) => deploymentStore.fetchDeployments(id), { immediate: true });
</script>

<template>
  <div>
    <h1>Deployments</h1>
    <table>
      <thead><tr>
        <th>id</th>
        <th>service_id</th>
        <th>origin</th>
        <th>user</th>
        <th>deployments</th>
      </tr></thead>
      <tbody><tr v-for="deployment of deploymentStore.historyDeployments" :key="deployment.id">
        <td>{{ deployment.id }}</td>
        <td>{{ deployment.serviceId }}</td>
        <td>{{ deployment.origin }}</td>
        <td>{{ deployment.user }}</td>
        <td>
          <router-link
            :to="{ name: 'deployment-detail', params: { id: deployment.id } }"
            >details for {{ deployment.id }}</router-link
          >
        </td>
      </tr></tbody>
    </table>
    <p v-if="deploymentStore.historyError" role="alert">{{ deploymentStore.historyError }}</p>
    <button v-if="deploymentStore.historyHasMore" :disabled="deploymentStore.historyLoading"
      @click="deploymentStore.fetchDeployments(serviceId, true)">
      {{ deploymentStore.historyLoading ? 'Loading…' : 'Load more' }}
    </button>
  </div>
</template>
