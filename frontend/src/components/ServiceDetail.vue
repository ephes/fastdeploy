<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'

import { ServiceWithId } from '../typings'
import { useServices } from '../stores/service';

const route = useRoute()
const serviceStore = useServices()
const service: ServiceWithId | undefined = serviceStore.services[Number(route.params.id)]

const origin = ref('');
const expirationInDays = ref(30);
const serviceToken = ref('');

async function getServiceToken() {
    if (service) {
        serviceToken.value = await serviceStore.fetchServiceToken(service.name, origin.value, expirationInDays.value)
    }
}
</script>

<template>
    <div>
        <h1>Service {{ $route.params.id }}</h1>
        <div v-if="service">
            <h2>service name: {{ service.name }}</h2>
            <input v-model="origin" placeholder="origin" />
            <input v-model="expirationInDays" placeholder="expirationInDays" type="number" min="1" max="180"/>
            <button @click="getServiceToken()">Get Service Token</button>
            <div v-if="serviceToken">
                <h3>Service Token</h3>
                <pre>{{ serviceToken }}</pre>
            </div>
        </div>
    </div>
</template>
