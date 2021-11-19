import { defineStore, acceptHMRUpdate } from "pinia";

import { toUtcDate } from "./datetime";
import { Deployment, Message } from "../typings";

export function createDeployment(message: any): Deployment {
  const deployment: Deployment = {
    id: message.id,
    service_id: message.service_id,
    origin: message.origin,
    user: message.user,
    created: toUtcDate(new Date(message.created)),
    deleted: message.deleted,
  };
  return deployment;
}

export const useDeployments = defineStore("deployments", {
  state: () => {
    return {
      deployments: new Map<number | undefined, Deployment>(),
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
      this.deployments.set(deployment.id, deployment);
      return deployment;
    },
    async fetchDeployments() {
        const deployments = await this.client.fetchDeployments();
        for (const deployment of deployments) {
          this.deployments.set(deployment.id, deployment);
        }
    },
    onMessage(message: Message) {
      console.debug("on message in deployments store: ", message);
      if (message.type === "deployment") {
        const deployment = createDeployment(message);
        if (deployment.deleted) {
          this.deployments.delete(deployment.id);
        } else {
          this.deployments.set(deployment.id, deployment);
        }
      }
    },
  },
});
