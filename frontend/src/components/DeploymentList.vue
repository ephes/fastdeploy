<script setup lang="ts">
import { useDeployments } from '../stores/deployment';

const deploymentStore = useDeployments();
deploymentStore.fetchDeployments();
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
      <tr v-for="deployment of deploymentStore.deployments" :key="deployment.id">
        <td>{{ deployment.id }}</td>
        <td>{{ deployment.service_id }}</td>
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
