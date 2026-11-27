<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuth } from './stores/auth';

import WebsocketStatus from './components/WebsocketStatus.vue';

const router = useRouter();
const authStore = useAuth();
const route = useRoute();
/** Which of the two areas the current page belongs to. */
const area = computed(() => route.path.startsWith('/deployments') ? 'deployments' : 'services');
</script>

<template>
  <div class="shell" :class="{ 'signed-out': !authStore.isAuthenticated }">
    <header class="masthead">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>FastDeploy
      </div>
      <nav v-if="authStore.isAuthenticated" class="main-nav" aria-label="Main">
        <router-link to="/" :class="{ current: area === 'services' }">Services</router-link>
        <router-link :to="{name: 'deployment-list'}" :class="{ current: area === 'deployments' }">Deployments</router-link>
      </nav>
    </header>
    <WebsocketStatus />
    <main>
      <router-view></router-view>
    </main>
  </div>
</template>

<style src="./assets/app.css"></style>
<style>
.shell {
  position: relative;
  max-width: 68rem;
  min-height: 100vh;
  min-height: 100dvh;
  margin: 0 auto;
  padding: 0 var(--gutter) 4rem;
}

.masthead {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--bg);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 2rem;
  min-height: 3.75rem;
  /* room for the connection indicator in the top right corner */
  padding-right: 5.5rem;
  margin-bottom: 1.75rem;
  border-bottom: 1px solid var(--line);
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 1.0625rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 3.75rem;
}
/* Three steps of a deployment: done, done, still to come. */
.brand-mark {
  display: inline-flex;
  gap: 2px;
}
.brand-mark i {
  width: 6px;
  height: 14px;
  border-radius: 1.5px;
  background: var(--accent);
}
.brand-mark i:last-child {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--accent);
}

.main-nav {
  display: flex;
  align-self: stretch;
  gap: 0.25rem;
}
.main-nav a {
  display: flex;
  align-items: center;
  padding: 0 0.75rem;
  /* sits on the masthead rule */
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  font-weight: 550;
}
.main-nav a:hover {
  color: var(--ink);
  text-decoration: none;
}
.main-nav a.current {
  border-bottom-color: var(--accent);
  color: var(--ink);
}

.signed-out .websocket,
.signed-out .blink_me { display: none; }

@media (max-width: 34rem) {
  /* Only the navigation row stays in view; the indicator moves into its free end. */
  .masthead { top: -2.75rem; margin-bottom: 1.25rem; }
  .brand { line-height: 2.75rem; }
  .main-nav {
    flex-basis: 100%;
    /* the nav row may use the full width, the indicator sits above it */
    margin-right: -5.5rem;
    margin-left: -0.75rem;
  }
  .main-nav a { min-height: 2.75rem; }
}
</style>
