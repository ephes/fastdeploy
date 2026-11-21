import { defineStore, acceptHMRUpdate } from "pinia";
import { markRaw } from "vue";

import { getClient, HttpClient } from "./httpClient";
import { rememberSession } from "./session";
import { useServices } from "./service";
import { useSteps } from "./step";
import { deploymentSnapshot, deploymentPage } from "../restAdmission";
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
      displayedDeploymentId: null as number | null,
      retiredThrough: 0,
      pendingFetches: [] as Set<number>[],
      pendingStarts: [] as Set<number>[],
      pendingStartDeletions: markRaw(new Set<Set<number>>()),
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
      .filter((deployment) => !!deployment && (state.historyServiceId === undefined || deployment.serviceId === state.historyServiceId))
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
      const steps = stepsStore.stepsByDeployment[deploymentId] ?? {};
      for (const stepId in steps) {
        const step = steps[stepId];
        if (step.finished) {
          finishedSteps++;
        }
        allSteps++;
      }
      return [finishedSteps, allSteps];
    }
  },
  actions: {
    /** All pinned ids at once, so pruning checks membership without rescanning history. */
    pinnedIds(): Set<number> {
      const pinned = new Set(this.historyIds);
      if (this.displayedDeploymentId !== null) pinned.add(this.displayedDeploymentId);
      for (const id in this.deployments) {
        if (!this.deployments[id].finished) pinned.add(Number(id));
      }
      return pinned;
    },
    pruneHistory() {
      // The displayed window is finite even when live events keep arriving.
      this.historyIds = this.historyIds.sort((a, b) => b - a).slice(0, 200);
      const pinned = this.pinnedIds();
      const inactive = Object.keys(this.deployments).map(Number).filter(id => !pinned.has(id));
      for (const id of inactive.slice(0, Math.max(0, inactive.length - 100))) {
        delete this.deployments[id];
        this.retiredThrough = Math.max(this.retiredThrough, id);
        useSteps().evictDeployment(id);
      }
      useSteps().pruneHistory();
    },
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
     * A deletion observed while the POST is pending rejects the acknowledgement.
     *
     * The service token authorizes only this request.
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
      const requestedServiceId = Object.values(servicesStore.services).find(service => service.name === serviceName)?.id;
      if (requestedServiceId === undefined) {
        // Without the service identity the started row cannot be admitted; never launch blind.
        throw new Error("Service is not loaded. Refresh services before deploying.");
      }
      const serviceToken = await servicesStore.fetchServiceToken(
        serviceName,
        "frontend",
        1,
        onTokenError
      );
      if (!isCurrentSession() || !serviceToken) {
        return null;
      }
      const pending = this.pendingStartDeletions;
      const deletedMeanwhile = new Set<number>();
      pending.add(deletedMeanwhile);
      let response: unknown;
      try {
        response = await client.post<unknown>("deployments/", undefined, {
          headers: { Authorization: `Bearer ${serviceToken}` },
        });
      } finally {
        pending.delete(deletedMeanwhile);
      }
      if (!isCurrentSession()) {
        // started, but the session it was started in is over
        return null;
      }
      let started: Deployment;
      try {
        started = deploymentSnapshot(response, requestedServiceId);
        if (started.deleted) throw new Error();
      } catch {
        throw new Error("Deployment outcome is uncertain. Refresh history before retrying.");
      }
      if (deletedMeanwhile.has(started.id)) {
        throw new Error("Deployment was deleted. Refresh history before retrying.");
      }
      // A history request already in flight must not delete the new row, but it
      // may still replace it with the (newer) server state of that row.
      for (const pending of this.pendingStarts) pending.add(started.id);
      const known = this.deployments[started.id];
      if (known) {
        return known;
      }
      this.deployments[started.id] = started;
      this.pruneHistory();
      return started;
    },
    /** Fetch a bounded history page; only an explicit load-more extends it. */
    async fetchDeployments(serviceId?: number, loadMore = false, ownsRefresh: () => boolean = () => true) {
      if (loadMore && (this.historyLoading || !this.historyHasMore)) return;
      if (loadMore && this.historyIds.length >= 200) {
        this.historyError = "History limit reached. Select a service or refresh history.";
        return;
      }
      const isCurrentSession = rememberSession();
      if (!loadMore) {
        this.historyGeneration++;
        this.historyServiceId = serviceId;
      }
      const generation = this.historyGeneration;
      const ownsHistory = () => isCurrentSession() && generation === this.historyGeneration;
      const isCurrent = () => ownsHistory() && ownsRefresh();
      // A refresh that loses its owner must settle with retry feedback.
      const historyError = "Could not load deployment history. Try again.";
      const changed = markRaw(new Set<number>());
      const startedMeanwhile = markRaw(new Set<number>());
      this.pendingFetches.push(changed);
      this.pendingStarts.push(startedMeanwhile);
      this.historyLoading = true;
      this.historyError = "";
      const requestedServiceId = this.historyServiceId;
      const beforeId = loadMore ? this.historyBeforeId : null;
      const params = new URLSearchParams({ limit: "50" });
      if (requestedServiceId !== undefined) params.set("service_id", String(requestedServiceId));
      if (beforeId !== null) params.set("before_id", String(beforeId));
      try {
        const response = await this.client.get<unknown>(`deployments/?${params}`);
        if (!isCurrent()) {
          if (ownsHistory()) this.historyError = historyError;
          return;
        }
        const deployments = deploymentPage(response, requestedServiceId, beforeId);
        const historyIds = new Set(this.historyIds);
        if (!loadMore) {
          for (const id of historyIds) {
            const matchesService = requestedServiceId === undefined || this.deployments[id]?.serviceId === requestedServiceId;
            if (!matchesService || (!changed.has(id) && !startedMeanwhile.has(id))) historyIds.delete(id);
          }
          this.historyBeforeId = null;
        }
        const present = new Set(deployments.map(deployment => deployment.id));
        const oldest = deployments.length === 50 ? deployments[deployments.length - 1].id : 0;
        const upper = beforeId;
        for (const deployment of Object.values(this.deployments)) {
          if ((this.historyServiceId === undefined || deployment.serviceId === this.historyServiceId)
              && deployment.id >= oldest && (upper === null || deployment.id < upper)
              && !present.has(deployment.id) && !changed.has(deployment.id)
              && !startedMeanwhile.has(deployment.id)) {
            historyIds.delete(deployment.id);
            if (deployment.id !== this.displayedDeploymentId) {
              delete this.deployments[deployment.id];
              useSteps().evictDeployment(deployment.id);
            }
          }
        }
        for (const deployment of deployments) {
          if (!changed.has(deployment.id)) {
            this.deployments[deployment.id] = deployment;
          }
          if (this.deployments[deployment.id]) historyIds.add(deployment.id);
        }
        this.historyIds = [...historyIds];
        this.pruneHistory();
        // Advance using the server page even when an event deleted its last row.
        if (deployments.length) this.historyBeforeId = deployments[deployments.length - 1].id;
        this.historyHasMore = deployments.length === 50;
        if (this.historyHasMore && this.historyBeforeId !== null) {
          // First-page events arrived before a cursor existed: hide older gaps.
          const oldestId = this.historyBeforeId;
          this.historyIds = this.historyIds.filter((id) => id >= oldestId);
        }
      } catch {
        if (ownsHistory()) this.historyError = historyError;
      } finally {
        this.pendingFetches = this.pendingFetches.filter((pending) => pending !== changed);
        this.pendingStarts = this.pendingStarts.filter((pending) => pending !== startedMeanwhile);
        if (ownsHistory()) this.historyLoading = false;
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
          for (const pending of this.pendingStartDeletions) pending.add(deployment.id);
          this.retiredThrough = Math.max(this.retiredThrough, deployment.id);
          useSteps().evictDeployment(deployment.id);
          delete this.deployments[deployment.id];
          this.historyIds = this.historyIds.filter((id) => id !== deployment.id);
        } else {
          if (!this.deployments[deployment.id] && deployment.id <= this.retiredThrough) return;
          // Starts can publish after another request has already committed/published a finish.
          if (this.deployments[deployment.id]?.finished && !deployment.finished) return;
          this.deployments[deployment.id] = deployment;
          if ((this.historyServiceId === undefined || deployment.serviceId === this.historyServiceId)
              && (this.historyBeforeId === null || deployment.id > this.historyBeforeId)
              && !this.historyIds.includes(deployment.id)) {
            this.historyIds.push(deployment.id);
          }
        }
        this.pruneHistory();
      }
    },
  },
});
