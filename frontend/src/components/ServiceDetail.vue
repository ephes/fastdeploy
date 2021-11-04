<script setup lang="ts">
import { inject } from 'vue'
import { useRoute } from 'vue-router'
import { Client, Service } from '../typings'

const client: Client = inject("client") as Client
const route = useRoute()
const service: Service | undefined = client.services.get(Number(route.params.id))

</script>

<template>
    <div>
        <h1>Service {{ $route.params.id }}</h1>
        <div v-if="service">
            <h2>service name: {{ service.name }}</h2>
        </div>
    </div>
</template>
