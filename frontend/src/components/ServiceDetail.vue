<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useServices } from '../stores/service';
import { rememberSession } from '../stores/session';

const route = useRoute();
const serviceStore = useServices();
serviceStore.serviceTokenErrorMessage = "";
const serviceId = computed(() => Number(route.params.id));
const service = computed(() => serviceStore.services[serviceId.value]);
const origin = ref('');
const expirationInDays = ref(7);
const serviceToken = ref<string | null>(null);
const tokenError = ref('');
const pending = ref(false);
let generation = 0;

watch(serviceId, () => {
  generation++;
  serviceStore.serviceTokenErrorMessage = "";
  serviceToken.value = null;
  tokenError.value = '';
  origin.value = '';
  pending.value = false;
}, { flush: 'sync' });

async function getServiceToken() {
  if (!service.value || pending.value) return;
  const current = ++generation;
  const isCurrentSession = rememberSession();
  const name = service.value.name;
  pending.value = true;
  serviceToken.value = null;
  tokenError.value = '';
  try {
    const result = await serviceStore.fetchServiceToken(name, origin.value, expirationInDays.value, message => {
      if (current === generation && isCurrentSession()) tokenError.value = message;
    });
    if (current !== generation || !isCurrentSession()) return;
    serviceToken.value = result;
    if (!result && !tokenError.value) tokenError.value = 'Could not issue a service token. Check your permissions and inputs, then retry.';
  } catch {
    if (current === generation && isCurrentSession()) tokenError.value = 'Could not issue a service token. Try again.';
  } finally {
    if (current === generation) pending.value = false;
  }
}
</script>

<template>
  <div>
    <h1>Service {{ serviceId }}</h1>
    <p v-if="serviceStore.servicesLoading" role="status">Loading service…</p>
    <div v-else-if="service">
      <h2>service name: {{ service.name }}</h2>
      <p v-if="tokenError" role="alert">{{ tokenError }}</p>
      <label for="token-origin">Origin</label>
      <input id="token-origin" v-model="origin" />
      <label for="token-days">Expiration in days</label>
      <input id="token-days" v-model="expirationInDays" type="number" min="1" max="90" />
      <button :disabled="pending" @click="getServiceToken">{{ pending ? 'Issuing token…' : 'Get Service Token' }}</button>
      <div v-if="serviceToken">
        <h3>Service Token</h3>
        <pre>{{ serviceToken }}</pre>
      </div>
    </div>
    <p v-else-if="serviceStore.servicesError" role="alert">{{ serviceStore.servicesError }}</p>
    <p v-else>Service not found.</p>
  </div>
</template>
<style scoped>
input, button { margin: 10px; }
</style>
