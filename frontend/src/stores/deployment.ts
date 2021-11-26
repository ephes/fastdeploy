import { defineStore, acceptHMRUpdate } from "pinia";

import { mande } from "mande";
import { toUtcDate } from "./datetime";
import { useAuth } from "./auth";
import { useSettings } from "./config";
import { Deployment, Message, DeploymentById } from "../typings";

export const useDeployments = defineStore("deployments", {
  state: () => {
    return {
      deployments: {} as DeploymentById,
    };
  },
  getters: {
    mande: (state) => () => {
      const auth = useAuth();
      const settings = useSettings();
      const client = mande(settings.api);
      console.log("mande client: ", client);
      client.options.headers.Authorization = `Bearer ${auth.accessToken}`;
      console.log("mande client options: ", client.options);
      return client;
    },
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useDeployments, meta.hot));
      }
    },
    async startDeployment(serviceName: string) {
      const deployment = await this.client.startDeployment(serviceName);
      this.deployments[deployment.id] = deployment;
      return deployment;
    },
    async fetchDeployments() {
      const client = this.mande();
      console.log("mande options: ", client.options);
      const deployments: Deployment[] = await client.get("deployments");
      console.log("fetched deployments asdf: ", deployments);
      // const deployments = await this.client.fetchDeployments();
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
