<script setup lang="ts">
import { inject, reactive, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { createService } from '../client';
import { Client, Deployment } from '../typings';
import { useSettings } from '../stores/config';

const settings = useSettings();
console.log('store: ', settings);
console.log('base api: ', settings.api);
console.log('base websocket: ', settings.websocket);
console.log('store client: ', settings.client);

const client: Client = inject('client') as Client;
const router = useRouter();
const services = client.services;
const newService = reactive(
  createService({
    id: undefined,
    name: '',
    collect: '',
    deploy: '',
    deleted: false,
  })
);

async function fetchServices() {
  await client.fetchServices();
}

onMounted(async () => {
  // using onMounted to be able to define an async function
  // rather belongs to create lifecycle hook, but cannot await in setup
  await fetchServices();
});

async function addService() {
  await client.addService(newService);
}

async function deleteService(serviceId: number | undefined) {
  if (serviceId) {
    await client.deleteService(serviceId);
  }
}

async function startDeployment(serviceName: string) {
  const deployment: Deployment = await client.startDeployment(serviceName);
  router.push({ name: 'deployment-detail', params: { id: deployment.id } });
}
</script>

<template>
  <div>
    <h1>Services</h1>
    <input v-model="newService.name" placeholder="service name" />
    <input v-model="newService.collect" placeholder="collect script" />
    <input v-model="newService.deploy" placeholder="deploy script" />
    <button @click="addService()">add</button>
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
      <tr v-for="[id, service] in services" :key="id" class="list-service">
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
          <button @click="deleteService(service.id)">delete</button>
        </td>
      </tr>
    </table>
  </div>
</template>
