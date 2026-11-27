<script setup lang="ts">
import { useWebsocketStore } from '../stores/websocket';

const websocketStore = useWebsocketStore();
</script>

<template>
    <p v-if="websocketStore.connectionError || websocketStore.protocolError" role="alert" class="connection-notice">
      {{ websocketStore.connectionError || websocketStore.protocolError }}
    </p>
    <p v-if="websocketStore.serverWarning" role="alert" class="connection-notice">{{ websocketStore.serverWarning }}</p>
    <p v-if="websocketStore.resyncError" role="alert" class="connection-notice">{{ websocketStore.resyncError }}</p>
    <div v-if="websocketStore.recentlyReceivedMessage" class="blink_me" aria-hidden="true">&nbsp;</div>
    <div v-if="websocketStore.isOnline" class="websocket online" title="Live updates are connected"><span class="sr-only">Live updates: </span>Live</div>
    <div v-else class="websocket offline" title="Live updates are not connected"><span class="sr-only">Live updates: </span>Offline</div>
</template>
<style scoped>
.connection-notice { margin-bottom: 0.75rem; }

/* Connection indicator in the top right corner of the masthead; it stays in view while scrolling. */
.websocket {
  position: fixed;
  z-index: 6;
  top: 1.875rem;
  right: max(var(--gutter), calc((100vw - 68rem) / 2 + var(--gutter)));
  transform: translateY(-50%);
  display: flex;
  /* dot last, so it keeps its place when the label changes */
  flex-direction: row-reverse;
  align-items: center;
  gap: 0.45rem;
  color: var(--muted);
  font-size: 0.8125rem;
  font-weight: 550;
  line-height: 1;
}
.websocket::before {
  content: "";
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
}
.online::before { background: var(--ok); }
.offline { color: var(--fail); }
.offline::before {
  background: transparent;
  box-shadow: inset 0 0 0 2px var(--fail);
}

/* A ring that spreads from the dot while messages arrive. */
.blink_me {
  position: fixed;
  z-index: 6;
  top: 1.875rem;
  right: max(var(--gutter), calc((100vw - 68rem) / 2 + var(--gutter)));
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--ok);
  pointer-events: none;
  animation: ripple 1s ease-out infinite;
}

@keyframes ripple {
  from { opacity: 0.6; transform: translateY(-50%) scale(1); }
  to { opacity: 0; transform: translateY(-50%) scale(3.2); }
}

@media (max-width: 34rem) {
  .websocket, .blink_me { top: 1.375rem; }
}
</style>
