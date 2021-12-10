<script setup lang="ts">
import { useWebsocketStore } from '../stores/websocket';

const websocketStore = useWebsocketStore();
</script>

<template>
    <div v-if="websocketStore.recentlyReceivedMessage" class="blink_me">&nbsp;</div>
    <div v-if="websocketStore.isOnline" class="websocket online"></div>
    <div v-else class="websocket offline"></div>
</template>
<style scoped>
.websocket {
    position: fixed;
    bottom: 10px;
    right: 10px;
}
.online {
    background-color: green;
    color: white;
    padding: 5px;
    font-size: 20px;
}
.offline {
    background-color: red;
    color: white;
    padding: 5px;
    font-size: 20px;
}
.blink_me {
  animation: blinker 0.5s linear infinite;
  background-color: aquamarine;
  position: fixed;
  bottom: 10px;
  right: 22px;
  width: 10px;
  height: 10px;
}

@keyframes blinker {
  50% { opacity: 0; }
}
</style>
