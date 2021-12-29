import { defineStore, acceptHMRUpdate } from "pinia";

import { getClient, HttpClient } from "./httpClient";
import { useServices } from "./service";
import { useSteps } from "./step";
import { pythonToJavascript } from "../converters";
import { Deployment, Message, DeploymentById } from "../typings";

/**
 * This store can be used to start deployments and holds information
 * about deployments.
 */
export const useDeployments = defineStore("deployments", {
  state: () => {
    return {
      /**
       * Look up deployments by id.
       */
      deployments: {} as DeploymentById,
      client: getClient(),
    };
  },
  getters: {
    /**
     * Get deployments optionally filtered by service id.
     *
     * @param serviceId {number}
     * @returns {DeploymentById}
     */
    getDeploymentsByService:
      (state) =>
      (serviceId?: number): DeploymentById => {
        console.log("deployments: ", state.deployments);
        if (serviceId) {
          return Object.fromEntries(
            Object.entries(state.deployments).filter(
              ([deploymentId, deployment]) => deployment.serviceId === serviceId
            )
          );
        } else {
          return state.deployments;
        }
      },
  /**
   * Get currently active deployments by service id.
   *
   * @param serviceId {number}
   * @returns {DeploymentById}
   */
  getActiveDeploymentsByService:
    (state) => (serviceId: number): DeploymentById => {
      return Object.fromEntries(
        Object.entries(state.deployments).filter(
          ([deploymentId, deployment]) => deployment.serviceId === serviceId && !deployment.finished
        )
      );
    },
    /**
     * Get finished vs all step count by deployment id.
     *
     * @param deploymentId {number}
     * @returns [number, number]
     */
    getFinishedVsAllSteps: (state) => (deploymentId: number): [number, number] => {
      const stepsStore = useSteps();
      let [finishedSteps, allSteps] = [0, 0];
      const steps = stepsStore.getStepsByDeployment(deploymentId);
      for (const [stepId, step] of Object.entries(steps)) {
        if (step.finished) {
          finishedSteps++;
        }
        allSteps++;
      }
      return [finishedSteps, allSteps];
    }
  },
  actions: {
    /**
     * Support for HMR
     * @param {any} meta
     */
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useDeployments, meta.hot));
      }
    },
    /**
     * Start a deployment. First step is to fetch a service token
     * from the backend. The origin of the deployment is set to frontend.
     *
     * Then use the service token to start the deployment.
     *
     * @param serviceName {string} the name of the service to deploy
     * @param client {HttpClient} the http client to use - settable for testing
     * @returns deployment {Deployment} the started deployment
     */
    async startDeployment(
      serviceName: string,
      client: HttpClient = getClient()
    ) {
      const servicesStore = useServices();
      const serviceToken = await servicesStore.fetchServiceToken(
        serviceName,
        "frontend"
      );
      client.options.headers.Authorization = `Bearer ${serviceToken}`;
      const deployment = await client.post<Promise<Deployment>>("deployments/");
      this.deployments[deployment.id] = deployment;
      return deployment;
    },
    /**
     * Fetch all deployments from the backend and store them in the
     * store by id.
     */
    async fetchDeployments() {
      const deployments: Deployment[] = await this.client.get<Promise<Deployment[]>>("deployments/");
      for (const deployment of deployments) {
        this.deployments[deployment.id] = pythonToJavascript(deployment) as Deployment;
      }
    },
    /**
     * Event handler which is triggered by a message from the backend
     * which has the type "deployment". Deployments from other origins
     * like GitHub or other frontends should also be visible. They are
     * received by this event handler.
     *
     * @param message {Message} the message which is received from the backend
     */
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
