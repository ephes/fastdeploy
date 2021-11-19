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
    <input v-model="serviceStore.new.name" placeholder="service name" />
    <input v-model="serviceStore.new.collect" placeholder="collect script" />
    <input v-model="serviceStore.new.deploy" placeholder="deploy script" />
    <button @click="serviceStore.addService()">add</button>
    <br />
    <table align="center">
      <tr>
        <th>name</th>
        <th>collect script</th>
        <th>deploy script</th>
        <th>link</th>
        <th>deploy</th>
        <th>delete</th>
      </tr>
      <tr v-for="[id, service] in serviceStore.services" :key="id" class="list-service">
        <td>{{ service.name }}</td>
        <td>{{ service.collect }}</td>
        <td>{{ service.deploy }}</td>
        <td>
          <router-link
            :to="{ name: 'service-detail', params: { id: service.id } }"
            >details for {{ service.name }}</router-link
          >
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
