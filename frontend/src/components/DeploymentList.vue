<script setup lang="ts">
import { useRoute } from 'vue-router';

import { useDeployments } from '../stores/deployment';

const deploymentStore = useDeployments();
deploymentStore.fetchDeployments();

const route = useRoute();
</script>

<template>
  <div>
    <h1>Deployments</h1>
    <table>
      <tr>
        <th>id</th>
        <th>service_id</th>
        <th>origin</th>
        <th>user</th>
        <th>deployments</th>
      </tr>
      <tr v-for="deployment of deploymentStore.getDeploymentsByService(Number(route.params.serviceId))" :key="deployment.id">
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
      </tr>
    </table>
  </div>
</template>
