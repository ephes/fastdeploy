<script setup lang="ts">
import { inject } from 'vue'
import { useRoute } from 'vue-router'
import { Client, Deployment } from '../typings'

const client: Client = inject("client") as Client
const route = useRoute()
const deployment: Deployment | undefined = client.deployments.get(Number(route.params.id))

</script>

<template>
    <div>
        <h1>Service {{ $route.params.id }}</h1>
        <div v-if="deployment">
            <h2>deployment origin: {{ deployment.origin }}</h2>
        </div>
    </div>
</template>
