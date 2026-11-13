import { defineStore, acceptHMRUpdate } from "pinia";
import { markRaw } from "vue";

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
      pendingFetches: [] as Set<number>[],
      historyIds: [] as number[],
      historyBeforeId: null as number | null,
      historyServiceId: undefined as number | undefined,
      historyHasMore: true,
      historyLoading: false,
      historyError: "",
      historyGeneration: 0,
      client: getClient(),
    };
  },
  getters: {
    historyDeployments: (state): Deployment[] => state.historyIds
      .map((id) => state.deployments[id])
      .filter((deployment) => !!deployment)
      .sort((a, b) => b.id - a.id),
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
     * @param onTokenError optional request-local token error feedback
     * @returns deployment {Deployment | null} the started deployment, null on issuance failure or session end
     */
    async startDeployment(
      serviceName: string,
      client: HttpClient = getClient(),
      onTokenError?: (message: string) => void
    ): Promise<Deployment | null> {
      const isCurrentSession = rememberSession();
      const servicesStore = useServices();
      const serviceToken = await servicesStore.fetchServiceToken(
        serviceName,
        "frontend",
        1,
        onTokenError
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
    /** Fetch a bounded history page; only an explicit load-more extends it. */
    async fetchDeployments(serviceId?: number, loadMore = false, ownsRefresh: () => boolean = () => true) {
      if (loadMore && (this.historyLoading || !this.historyHasMore)) return;
      const isCurrentSession = rememberSession();
      if (!loadMore) {
        this.historyGeneration++;
        this.historyIds = [];
        this.historyBeforeId = null;
        this.historyServiceId = serviceId;
        this.historyHasMore = true;
      }
      const generation = this.historyGeneration;
      const isCurrent = () => isCurrentSession() && ownsRefresh() && generation === this.historyGeneration;
      const changed = markRaw(new Set<number>());
      this.pendingFetches.push(changed);
      this.historyLoading = true;
      this.historyError = "";
      const params = new URLSearchParams({ limit: "50" });
      if (this.historyServiceId !== undefined) params.set("service_id", String(this.historyServiceId));
      if (this.historyBeforeId !== null) params.set("before_id", String(this.historyBeforeId));
      try {
        const deployments = await this.client.get<Deployment[]>(`deployments/?${params}`);
        if (!isCurrent()) return;
        const present = new Set(deployments.map(deployment => deployment.id));
        const oldest = deployments.length === 50 ? deployments[deployments.length - 1].id : 0;
        const upper = loadMore ? this.historyBeforeId : null;
        for (const deployment of Object.values(this.deployments)) {
          if ((this.historyServiceId === undefined || deployment.serviceId === this.historyServiceId)
              && deployment.id >= oldest && (upper === null || deployment.id < upper)
              && !present.has(deployment.id) && !changed.has(deployment.id)) {
            delete this.deployments[deployment.id];
            this.historyIds = this.historyIds.filter(id => id !== deployment.id);
          }
        }
        for (const deployment of deployments) {
          if (!changed.has(deployment.id)) {
            this.deployments[deployment.id] = pythonToJavascript(deployment) as Deployment;
          }
          if (this.deployments[deployment.id] && !this.historyIds.includes(deployment.id)) {
            this.historyIds.push(deployment.id);
          }
        }
        // Advance using the server page even when an event deleted its last row.
        if (deployments.length) this.historyBeforeId = deployments[deployments.length - 1].id;
        this.historyHasMore = deployments.length === 50;
        if (this.historyHasMore && this.historyBeforeId !== null) {
          // First-page events arrived before a cursor existed: hide older gaps.
          const oldestId = this.historyBeforeId;
          this.historyIds = this.historyIds.filter((id) => id >= oldestId);
        }
      } catch {
        if (isCurrent()) this.historyError = "Could not load deployment history. Try again.";
      } finally {
        this.pendingFetches = this.pendingFetches.filter((pending) => pending !== changed);
        if (isCurrentSession() && generation === this.historyGeneration) this.historyLoading = false;
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
        for (const pending of this.pendingFetches) pending.add(deployment.id);
        if (deployment.deleted) {
          delete this.deployments[deployment.id];
          this.historyIds = this.historyIds.filter((id) => id !== deployment.id);
        } else {
          this.deployments[deployment.id] = deployment;
          if ((this.historyServiceId === undefined || deployment.serviceId === this.historyServiceId)
              && (this.historyBeforeId === null || deployment.id > this.historyBeforeId)
              && !this.historyIds.includes(deployment.id)) {
            this.historyIds.push(deployment.id);
          }
        }
      }
    },
  },
});
