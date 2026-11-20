import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import { Environment } from "./typings";
import {
  useSettings,
  WEBSOCKET_URL_DEFAULT,
  API_BASE_DEFAULT,
} from "./stores/config";
import { useServices } from "./stores/service";
import { useAuth } from "./stores/auth";
import { useDeployments } from "./stores/deployment";
import { useSteps } from "./stores/step";
import { createPinia } from "pinia";
import { routes } from './routes';

const env: Environment = {
  MODE: import.meta.env.PROD ? "production" : import.meta.env.MODE || "development",
  VITE_API_BASE_PROD: import.meta.env.VITE_API_BASE_PROD?.trim() ?? "",
  VITE_WEBSOCKET_URL_PROD: import.meta.env.VITE_WEBSOCKET_URL_PROD?.trim() ?? "",
  VITE_API_BASE_DEV: import.meta.env.VITE_API_BASE_DEV || API_BASE_DEFAULT,
  VITE_WEBSOCKET_URL_DEV: import.meta.env.VITE_WEBSOCKET_URL_DEV || WEBSOCKET_URL_DEFAULT,
};
if (env.MODE === "production") {
  const missing = (["VITE_API_BASE_PROD", "VITE_WEBSOCKET_URL_PROD"] as const)
    .filter(key => !env[key]);
  if (missing.length) {
    throw new Error(`Missing frontend production configuration: ${missing.join(", ")}`);
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, from) => {
  const auth = useAuth();
  console.log("beforeEach: ", auth.isAuthenticated, to, from);
  if (!auth.isAuthenticated && to.name !== "login") {
    // redirect to login if not authenticated
    return { name: "login" };
  } else {
    return true;
  }
});

const app = createApp(App);
const pinia = createPinia();

import "pinia";

declare module "pinia" {
  export interface PiniaCustomProperties {
    env: Environment;
  }
}

pinia.use(({ store }) => {
  store.env = env;
});

app.use(router);
app.use(pinia);

// activate HMR for stores
const stores = [
  useAuth(),
  useSteps(),
  useServices(),
  useSettings(),
  useDeployments(),
];
for (const store of stores) {
  store.useHMRUpdate(import.meta);
}

app.mount("#app");
