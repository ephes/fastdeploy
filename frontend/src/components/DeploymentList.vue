<script setup lang="ts">
import { inject, ref, reactive, onMounted } from 'vue';
import { Client, Deployment } from '../typings';

const client: Client = inject('client') as Client;
const deployments = ref([] as Deployment[]);

async function fetchDeployments() {
  deployments.value = await client.fetchDeployments();
}

onMounted(async () => {
  await fetchDeployments();
});
</script>

<template>
  <div>
    <h1>Deployments</h1>
    <table align="center">
      <tr>
        <th>id</th>
        <th>service_id</th>
        <th>origin</th>
        <th>user</th>
        <th>link</th>
      </tr>
      <tr v-for="deployment in deployments">
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
