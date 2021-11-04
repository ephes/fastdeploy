<script setup lang="ts">
import { inject, ref, onMounted } from 'vue'
import { Client, Service } from '../typings'

const services = ref([] as Service[])

async function setServices(fetchedServices: Service[]) {
    services.value = fetchedServices
}

onMounted(async () => {
  const client: Client = inject("client") as Client
  await setServices(await client.fetchServices())
})
</script>

<template>
    <div>
        <h1>Services</h1>
        len: {{ services.length }}
        <ul>
            <li v-for="service in services">
                service: {{ service.name }}
                <router-link :to="{ name: 'service-detail', params: { id: service.id }}">Link to service {{ service.id }}</router-link>
            </li>
        </ul>
    </div>
</template>
