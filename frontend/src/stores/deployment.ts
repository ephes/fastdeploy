import { defineStore, acceptHMRUpdate } from "pinia";

import { toUtcDate } from "./datetime";
import { Deployment, Message, DeploymentById } from "../typings";

export const useDeployments = defineStore("deployments", {
  state: () => {
    return {
      deployments: {} as DeploymentById,
    };
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useDeployments, meta.hot));
      }
    },
    async startDeployment(serviceName: string) {
      const deployment = await this.client.startDeployment(serviceName);
      console.log("started deployment: ", deployment);
      this.deployments[deployment.id] = deployment;
      return deployment;
    },
    async fetchDeployments() {
        const deployments = await this.client.fetchDeployments();
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
