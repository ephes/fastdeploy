import { defineStore, acceptHMRUpdate } from "pinia";

import { getClient, HttpClient } from "./httpClient";
import { rememberSession } from "./session";
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
     * The response is converted like every other deployment (camel case
     * keys, dates), so the new row is found by its serviceId right away.
     * It is the oldest state the deployment ever had: if the websocket
     * (or a list fetch) already delivered the row, that one is kept and
     * returned instead of being replaced by the start response.
     *
     * The service token is only set on the client of this one call.
     *
     * Returns null if token issuance fails; the services store keeps the error.
     * Also returns null when the login session ended while waiting (logout,
     * or another login): the caller belongs to a session that is over
     * and must not act on the result, e.g. navigate to the deployment.
     * If that happens before the request was sent, it is not sent.
     *
     * @param serviceName {string} the name of the service to deploy
     * @param client {HttpClient} the http client to use - settable for testing
     * @returns deployment {Deployment | null} the started deployment, null on issuance failure or session end
     */
    async startDeployment(
      serviceName: string,
      client: HttpClient = getClient()
    ): Promise<Deployment | null> {
      const isCurrentSession = rememberSession();
      const servicesStore = useServices();
      const serviceToken = await servicesStore.fetchServiceToken(
        serviceName,
        "frontend"
      );
      if (!isCurrentSession() || !serviceToken) {
        return null;
      }
      client.options.headers.Authorization = `Bearer ${serviceToken}`;
      const started = pythonToJavascript(
        await client.post<Promise<Deployment>>("deployments/")
      ) as Deployment;
      if (!isCurrentSession()) {
        // started, but the session it was started in is over
        return null;
      }
      const known = this.deployments[started.id];
      if (known) {
        return known;
      }
      this.deployments[started.id] = started;
      return started;
    },
    /**
     * Fetch all deployments from the backend and store them in the
     * store by id.
     */
    async fetchDeployments() {
      const isCurrentSession = rememberSession();
      const deployments: Deployment[] = await this.client.get<Promise<Deployment[]>>("deployments/");
      if (!isCurrentSession()) {
        return;
      }
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
