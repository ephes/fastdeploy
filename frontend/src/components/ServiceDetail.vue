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

watch([serviceId, () => service.value?.id, () => service.value?.name], () => {
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
  <div class="service-detail">
    <div class="page-head">
      <div>
        <h1>{{ service && !serviceStore.servicesLoading ? service.name : `Service ${serviceId}` }}</h1>
        <p v-if="service && !serviceStore.servicesLoading" class="sub">
          Service {{ serviceId }}.
          <router-link :to="{ path: '/deployments', query: { serviceId: service.id } }">Deployment history</router-link>
        </p>
      </div>
    </div>
    <p v-if="serviceStore.servicesLoading" role="status">Loading service…</p>
    <div v-else-if="service" class="panel token">
      <h2>Service token</h2>
      <p class="muted intro">
        With a service token another system, for example a CI job, can start deployments of this service.
      </p>
      <p v-if="tokenError" role="alert">{{ tokenError }}</p>
      <div class="fields">
        <div class="field origin">
          <label for="token-origin">Origin</label>
          <input id="token-origin" v-model="origin" placeholder="github" autocomplete="off" autocapitalize="off" spellcheck="false" />
        </div>
        <div class="field days">
          <label for="token-days">Expiration in days</label>
          <input id="token-days" v-model="expirationInDays" type="number" min="1" max="90" />
        </div>
        <button class="primary" :disabled="pending" @click="getServiceToken">{{ pending ? 'Issuing token…' : 'Get Service Token' }}</button>
      </div>
      <div v-if="serviceToken" class="issued">
        <h3>Service Token</h3>
        <pre>{{ serviceToken }}</pre>
        <p class="muted hint">Copy it now. It disappears when you leave this page.</p>
      </div>
    </div>
    <p v-else-if="serviceStore.servicesError" role="alert">{{ serviceStore.servicesError }}</p>
    <p v-else class="notice">Service not found.</p>
  </div>
</template>
<style scoped>
.token {
  max-width: 44rem;
  padding: 1.25rem;
}
.intro { margin: 0.2rem 0 1.1rem; max-width: 60ch; }
.token [role="alert"] { margin-bottom: 1rem; }
.fields {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1rem;
}
.field.origin { flex: 1 1 14rem; }
.field.days { flex: 0 1 10rem; }
.fields button { min-height: 2.5rem; }

.issued {
  margin-top: 1.25rem;
  padding-top: 1.1rem;
  border-top: 1px solid var(--line);
}
.issued h3 { font-size: 0.875rem; font-weight: 550; margin-bottom: 0.3rem; }
.issued pre {
  margin: 0;
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface-sunk);
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  /* one click selects the whole token */
  user-select: all;
  -webkit-user-select: all;
}
.hint { margin-top: 0.4rem; font-size: 0.875rem; }

@media (max-width: 34rem) {
  .field.days { flex-basis: 100%; }
  .fields button { width: 100%; }
}
</style>
