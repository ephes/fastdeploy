<script setup lang="ts">
import { useWebsocketStore } from '../stores/websocket';

const websocketStore = useWebsocketStore();
</script>

<template>
    <div class="websocket">
        Websocket status:
        <p>Handling: {{ websocketStore.handling }}</p>
        <p>Connection: {{ websocketStore.connection }}</p>
        <p>Authentication: {{ websocketStore.authentication }}</p>
    </div>
</template>
<style scoped>
.websocket {
    position: fixed;
    bottom: 0;
    right: 0;
}
</style>
