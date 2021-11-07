<script setup lang="ts">
import { inject, ref, reactive, onMounted } from 'vue';
import { createService } from '../client';
import { Client, Service } from '../typings';

const client: Client = inject('client') as Client;
const services = client.services;
const newService = reactive(
  createService({ id: null, name: '', collect: '', deploy: '' })
);

async function fetchServices() {
  await client.fetchServices();
}

onMounted(async () => {
  await fetchServices();
});

async function addService() {
  console.log(
    'adding: ',
    newService.name,
    newService.collect,
    newService.deploy
  );
  await client.addService(newService);
}

async function deleteService(serviceId: number | null) {
  if (serviceId) {
    await client.deleteService(serviceId);
  }
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
          <button @click="deleteService(service.id)">delete</button>
        </td>
      </tr>
    </table>
  </div>
</template>
