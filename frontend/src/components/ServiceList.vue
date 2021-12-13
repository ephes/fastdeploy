<script setup lang="ts">
import { useRouter } from 'vue-router';

import { useServices } from '../stores/service';
import { useDeployments } from '../stores/deployment';
import { Deployment } from '../typings';

const serviceStore = useServices();
const deploymentStore = useDeployments();
const router = useRouter();

async function startDeployment(serviceName: string) {
  const deployment: Deployment = await deploymentStore.startDeployment(serviceName);
  router.push({ name: 'deployment-detail', params: { id: deployment.id } });
}
</script>

<template>
  <div>
    <h1>Services</h1>
    <div v-if="serviceStore.getAvailableServiceNames.length">
      <select v-model="serviceStore.new.name">
        <option disabled value>Please select service to add</option>
        <option v-for="name in serviceStore.getAvailableServiceNames" :value="name">{{ name }}</option>
      </select>
      <button @click="serviceStore.addService()">add</button>
    </div>
    <br />
    <table class="service-list">
      <tr>
        <th>name</th>
        <th>generate service token</th>
        <th>deploy</th>
        <th>delete</th>
      </tr>
      <tr v-for="service of serviceStore.services" :key="service.id" class="list-service">
        <td>{{ service.name }}</td>
        <td>
          <router-link
            :to="{ name: 'service-detail', params: { id: service.id } }"
          >{{ service.name }}</router-link>
        </td>
        <td>
          <button @click="startDeployment(service.name)">deploy</button>
        </td>
        <td>
          <button @click="serviceStore.deleteService(service.id)">delete</button>
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
</style>
