import { createApp, markRaw } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import { Client } from "./typings";
import { createClient } from "./client";
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
  console.log("beforeEach: ", client.isAuthenticated.value, to, from);
  if (!client.isAuthenticated.value && to.name !== "login") {
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
  }
}

pinia.use(({ store }) => {
  store.client = markRaw(client);
});

app.use(router);
app.use(client);
app.use(pinia);
app.mount("#app");
