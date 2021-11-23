import { createApp, markRaw } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import { Client, Environment } from "./typings";
import { createClient } from "./client";
import {
  useSettings,
  ENV_DEFAULT,
  WEBSOCKET_URL_DEFAULT,
  API_BASE_DEFAULT,
} from "./stores/config";
import { useServices } from "./stores/service";
import { useAuth } from "./stores/auth";
import { useDeployments } from "./stores/deployment";
import { useSteps } from "./stores/step";
import { createPinia } from "pinia";
import Login from "./components/Login.vue";
import ServiceList from "./components/ServiceList.vue";
import ServiceDetail from "./components/ServiceDetail.vue";
import DeploymentList from "./components/DeploymentList.vue";
import DeploymentDetail from "./components/DeploymentDetail.vue";

const client = createClient();

const routes = [
  { path: "/", component: ServiceList },
  { path: "/services/:id", name: "service-detail", component: ServiceDetail },
  { path: "/deployments", component: DeploymentList },
  {
    path: "/deployments/:id",
    name: "deployment-detail",
    component: DeploymentDetail,
  },
  { path: "/login", name: "login", component: Login },
];

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
    client: Client;
    env: Environment;
  }
}

function getEnv(): Environment {
  const env = ENV_DEFAULT;
  env.MODE = import.meta.env.MODE || "development";
  env.VITE_API_BASE_DEV = String(
    import.meta.env.VITE_API_BASE_DEV || API_BASE_DEFAULT
  );
  env.VITE_API_BASE_PROD = String(
    import.meta.env.VITE_API_BASE_PROD ||
      "https://deploy.staging.wersdoerfer.de"
  );
  env.VITE_WEBSOCKET_URL_DEV = String(
    import.meta.env.VITE_WEBSOCKET_URL_DEV || WEBSOCKET_URL_DEFAULT
  );
  env.VITE_WEBSOCKET_URL_PROD = String(
    import.meta.env.VITE_WEBSOCKET_URL_PROD ||
      "ws://deploy.staging.wersdoerfer.de/deployments/ws"
  );
  return env;
}

pinia.use(({ store }) => {
  store.client = markRaw(client);
  store.env = getEnv();
  console.log("store env: ", store.env);
});

app.use(router);
app.use(client);
app.use(pinia);

// activate HMR for stores
const settings = useSettings();
settings.useHMRUpdate(import.meta);
const services = useServices();
services.useHMRUpdate(import.meta);
client.registerStore(services);
const auth = useAuth();
auth.useHMRUpdate(import.meta);
const deployments = useDeployments();
deployments.useHMRUpdate(import.meta);
client.registerStore(deployments);
const steps = useSteps();
steps.useHMRUpdate(import.meta);
client.registerStore(steps);

app.mount("#app");
