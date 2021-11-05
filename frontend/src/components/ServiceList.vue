<script setup lang="ts">
import { inject, ref, onMounted } from 'vue'
import { Client, Service } from '../typings'

const client: Client = inject("client") as Client
const services = ref([] as Service[])
const serviceName = ref('')
const collect = ref('')
const deploy = ref('')

async function fetchServices() {
    services.value= await client.fetchServices()
}

onMounted(async () => {
    await fetchServices()
})

function addService() {
    console.log("adding: ", serviceName.value, collect.value, deploy.value)
}
</script>

<template>
    <div>
        <h1>Services</h1>
        <input v-model="serviceName" placeholder="service name" />
        <input v-model="collect" placeholder="collect script" />
        <input v-model="deploy" placeholder="deploy script" />
        <button @click="addService()">add</button>
        <br />
        len: {{ services.length }}
        <ul>
            <li v-for="service in services">
                service: {{ service.name }}
                <router-link
                    :to="{ name: 'service-detail', params: { id: service.id } }"
                >Link to service {{ service.id }}</router-link>
            </li>
        </ul>
    </div>
</template>
