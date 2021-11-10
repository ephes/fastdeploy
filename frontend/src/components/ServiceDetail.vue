<script setup lang="ts">
import { inject, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Client, Service } from '../typings'

const client: Client = inject("client") as Client
const route = useRoute()
const service: Service | undefined = client.services.get(Number(route.params.id))

const origin = ref('');
const serviceToken = ref('');

async function getServiceToken(serviceName: string) {
    if (client.accessToken) {
        serviceToken.value = await client.fetchServiceToken(serviceName, client.accessToken, origin.value);
    }
}
</script>

<template>
    <div>
        <h1>Service {{ $route.params.id }}</h1>
        <div v-if="service">
            <h2>service name: {{ service.name }}</h2>
            <input v-model="origin" placeholder="origin" />
            <button @click="getServiceToken(service.name)">Get Service Token</button>
            <div v-if="serviceToken">
                <h3>Service Token</h3>
                <pre>{{ serviceToken }}</pre>
            </div>
        </div>
    </div>
</template>
