import Login from "./components/Login.vue";
import ServiceList from "./components/ServiceList.vue";
import ServiceDetail from "./components/ServiceDetail.vue";
import DeploymentList from "./components/DeploymentList.vue";
import DeploymentDetail from "./components/DeploymentDetail.vue";

export const routes = [
  { path: "/", component: ServiceList },
  { path: "/services/:id", name: "service-detail", component: ServiceDetail },
  {
    path: "/deployments",
    name: "deployment-list",
    component: DeploymentList,
  },
  {
    path: "/deployments/:id",
    name: "deployment-detail",
    component: DeploymentDetail,
  },
  { path: "/login", name: "login", component: Login },
];

