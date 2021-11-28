import { defineStore, acceptHMRUpdate } from "pinia";

import { getClient, HttpClient } from "./httpClient";
import { useServices } from "./service";
import { Deployment, Message, DeploymentById } from "../typings";

export const useDeployments = defineStore("deployments", {
  state: () => {
    return {
      deployments: {} as DeploymentById,
      client: getClient(),
    };
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useDeployments, meta.hot));
      }
    },
    async startDeployment(serviceName: string, client: HttpClient = getClient()) {
      const servicesStore = useServices();
      const serviceToken = await servicesStore.fetchServiceToken(
        serviceName,
        "frontend"
      );
      client.options.headers.Authorization = `Bearer ${serviceToken}`;
      const deployment = await client.post<Promise<Deployment>>("deployments");
      this.deployments[deployment.id] = deployment;
      return deployment;
    },
    async fetchDeployments() {
      const deployments: Deployment[] = await this.client.get(
        "deployments"
      );
      for (const deployment of deployments) {
        this.deployments[deployment.id] = deployment;
      }
    },
    onMessage(message: Message) {
      if (message.type === "deployment") {
        const deployment = message as Deployment;
        if (deployment.deleted) {
          delete this.deployments[deployment.id];
        } else {
          this.deployments[deployment.id] = deployment;
        }
      }
    },
  },
});
