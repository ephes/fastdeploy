import { markRaw } from "vue";
import { defineStore, acceptHMRUpdate } from "pinia";
import { getClient, type BoundedOptions } from "./httpClient";
import { useDeployments } from "./deployment";
import { rememberSession } from "./session";
import { stepPage } from "../restAdmission";
import { Step, StepById, Message, Deployment } from "../typings";

export const INVENTORY_MAX_ROWS = 1000;
export const INVENTORY_MAX_BYTES = 8 * 1024 * 1024;
export const INVENTORY_TIMEOUT_MS = 30_000;

/** Await a traversal until it settles or the caller cancels; resolves whether it published. */
async function joinTraversal(traversal: Promise<boolean>, signal: AbortSignal): Promise<boolean> {
  let cancel!: () => void;
  const cancelled = new Promise<never>((_resolve, reject) => {
    cancel = () => reject(signal.reason);
    signal.addEventListener("abort", cancel, { once: true });
  });
  try {
    return await Promise.race([traversal, cancelled]);
  } finally {
    signal.removeEventListener("abort", cancel);
  }
}

/**
 * This store is used to store deployment steps. They are stored
 * by deployment and by step id.
 */
export const useSteps = defineStore("steps", {
  state: () => {
    return {
      /**
       * Stores all steps by step id.
       */
      steps: {} as StepById,
      inventoryComplete: {} as Record<number, boolean>,
      deletedSteps: {} as Record<number, number>,
      /** Per-deployment tombstone ids and step counts so pruning/eviction never scan every row. */
      deletedByDeployment: {} as Record<number, number[]>,
      stepCounts: {} as Record<number, number>,
      pruneSuspended: 0,
      finishedDeployments: {} as Record<number, boolean>,
      pendingFetches: {} as Partial<Record<number, Set<Set<number>>>>,
      fetchGenerations: {} as Record<number, number>,
      /** The newest in-flight traversal without a caller signal (e.g. WebSocket resync), per deployment. */
      liveResyncs: {} as Partial<Record<number, Promise<boolean>>>,
      /** Generation of the traversal that last published an inventory, per deployment. */
      publishedGenerations: {} as Record<number, number>,
      fetchSequence: 0,
      retainedDeploymentIds: [] as number[],
      retiredThrough: 0,
      retiredStepThrough: 0,
      stepEventFloors: {} as Record<number, number>,
      fetching: {} as Record<number, number>,
      /**
       * Stores all steps by deployment id.
       */
      stepsByDeployment: {} as { [deploymentId: number]: StepById },
      /**
       * Stores steps that were in progress per deployment id.
       * To be able to scroll to the step before last step in progress.
       */
      stepsInProgressByDeployment: {} as { [deploymentId: number]: Step[] },
      /**
       * The http client.
       */
      client: getClient(),
    };
  },
  getters: {
    /**
     * Used in component to show all steps for a deployment after
     * a deployment has been selected. Shows also steps that are
     * arriving during a deployment.
     *
     * The array of steps is sorted first by finished, then by started.
     * If neither finished nor started is set, insertion order is used.
     *
     * @param deploymentId {number} The deployment id
     * @returns steps {Step[]} The steps for the deployment
     */
    getStepsByDeployment: (state) => (deploymentId: number) => {
      if (state.stepsByDeployment[deploymentId]) {
        return Object.values(state.stepsByDeployment[deploymentId]).sort(
          (a, b) => {
            for (const key of ["finished" as const, "started" as const]) {
              if (a[key]) {
                if (b[key]) {
                  return (a[key] as Date).getTime() - (b[key] as Date).getTime();
                } else {
                  return -1;
                }
              } else {
                if (b[key]) {
                  return 1;
                }
              }
            }
            return 0;
          }
        );
      } else {
        return [];
      }
    },
    /**
     * Given a step return whether the view should scroll to the step.
     * This is true when the next step in line is inProgress. We don't
     * use inProgress directly because it would scroll to far.
     *
     * @param step {Step} The step to check
     * @returns {boolean} Whether the view should scroll to the step
     */
    shouldScrollToStep: (state) => (step: Step) => {
      if (useDeployments().deployments[step.deploymentId]?.finished) return false;
      return state.stepsInProgressByDeployment[step.deploymentId]?.[4]?.id === step.id;
    }
  },
  actions: {
    evictDeployment(id: number) {
      this.retiredThrough = Math.max(this.retiredThrough, id);
      for (const stepId in this.stepsByDeployment[id] ?? {}) {
        this.retiredStepThrough = Math.max(this.retiredStepThrough, Number(stepId));
        delete this.steps[stepId];
      }
      for (const stepId of this.deletedByDeployment[id] ?? []) {
        this.retiredStepThrough = Math.max(this.retiredStepThrough, stepId);
        delete this.deletedSteps[stepId];
      }
      delete this.deletedByDeployment[id];
      delete this.stepCounts[id];
      delete this.stepsByDeployment[id];
      delete this.stepsInProgressByDeployment[id];
      delete this.inventoryComplete[id];
      delete this.finishedDeployments[id];
      delete this.fetchGenerations[id];
      delete this.publishedGenerations[id];
      delete this.stepEventFloors[id];
      this.retainedDeploymentIds = this.retainedDeploymentIds.filter(existing => existing !== id);
    },
    pruneHistory() {
      // Batched publishes prune once when they finish instead of once per row.
      if (this.pruneSuspended) return;
      const pinned = useDeployments().pinnedIds();
      const inactive = this.retainedDeploymentIds.filter(id => !pinned.has(id) && !this.fetching[id]);
      const retired = new Set(inactive.slice(0, Math.max(0, inactive.length - 100)));
      for (const id of inactive) {
        if ((this.deletedByDeployment[id]?.length ?? 0) > 1000 || (this.stepCounts[id] ?? 0) > 1000) retired.add(id);
      }
      for (const id of retired) this.evictDeployment(id);
    },
    retainDeployment(id: number, refresh = false): boolean {
      if (!this.retainedDeploymentIds.includes(id)) {
        // A compact high-water fence prevents late events reopening evicted histories.
        // Explicit REST refreshes can reopen them with current authoritative data.
        // Live deployments are pinned and never evicted, so the fence cannot apply to them.
        const deployment = useDeployments().deployments[id];
        const live = !!deployment && !deployment.finished;
        if (!refresh && !live && id <= this.retiredThrough) return false;
        this.stepEventFloors[id] = !live && id <= this.retiredThrough ? this.retiredStepThrough : 0;
        this.retainedDeploymentIds.push(id);
      }
      return true;
    },
    /**
     * Support for HMR
     * @param {any} meta
     */
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useSteps, meta.hot));
      }
    },
    /**
     * Add/update a step. If the step already exists, it will be updated.
     *
     * @param step {Step} The step to add/update
     */
    addStep(step: Step): boolean {
      if (!this.retainDeployment(step.deploymentId)) return false;
      const current = this.steps[step.id];
      if (this.deletedSteps[step.id] || (current && current.deploymentId !== step.deploymentId)) return false;
      // One persisted id is one lifecycle; a rerun receives a fresh id.
      const rank = (state: string) => state === "pending" ? 0 : state === "running" ? 1 : 2;
      if (current && (rank(step.state) < rank(current.state) ||
          (rank(current.state) === 2 && step.state !== current.state))) return false;
      this.steps[step.id] = step;
      if (step.deploymentId) {
        if (!this.stepsByDeployment[step.deploymentId]) {
          this.stepsByDeployment[step.deploymentId] = {};
        }
        if (!(step.id in this.stepsByDeployment[step.deploymentId])) {
          this.stepCounts[step.deploymentId] = (this.stepCounts[step.deploymentId] ?? 0) + 1;
        }
        this.stepsByDeployment[step.deploymentId][step.id] = step;
        if (step.state === "running" && current?.state !== "running" &&
            !this.finishedDeployments[step.deploymentId] && !useDeployments().deployments[step.deploymentId]?.finished) {
          if (!(step.deploymentId in this.stepsInProgressByDeployment)) {
            this.stepsInProgressByDeployment[step.deploymentId] = [step];
          } else if (!this.stepsInProgressByDeployment[step.deploymentId].some(existing => existing.id === step.id)) {
            // Add step to the list of steps in progress
            // to be able to scroll to the step before last step in progress.
            this.stepsInProgressByDeployment[step.deploymentId] = [step, ...this.stepsInProgressByDeployment[step.deploymentId]].slice(0, 5);
          }
        }
      }
      this.pruneHistory();
      return true;
    },
    /**
     * Delete step from store. Deleted steps are just normal steps
     * with an attribute "deleted" set to true.
     *
     * @param step {Step} The step to delete
     */
    deleteStep(step: Step): boolean {
      const owner = this.steps[step.id]?.deploymentId ?? this.deletedSteps[step.id];
      if (owner !== undefined && owner !== step.deploymentId) return false;
      if (!this.retainDeployment(step.deploymentId)) return false;
      if (!(step.id in this.deletedSteps)) {
        (this.deletedByDeployment[step.deploymentId] ??= []).push(step.id);
        this.deletedSteps[step.id] = step.deploymentId;
      }
      if (step.deploymentId && this.stepsInProgressByDeployment[step.deploymentId]) {
        this.stepsInProgressByDeployment[step.deploymentId] = this.stepsInProgressByDeployment[step.deploymentId]
          .filter(existing => existing.id !== step.id);
      }
      if (step.id in this.steps) {
        delete this.steps[step.id];
      }
      if (step.deploymentId && step.deploymentId in this.stepsByDeployment) {
        if (step.id in this.stepsByDeployment[step.deploymentId]) {
          delete this.stepsByDeployment[step.deploymentId][step.id];
          this.stepCounts[step.deploymentId]--;
        }
      }
      this.pruneHistory();
      return true;
    },
    /**
     * Traverse bounded step pages and publish only a completed inventory.
     * Accepted WebSocket changes remain authoritative throughout the traversal.
     *
     * @param deploymentId {number} The deployment id
     * @param ownsRefresh Whether the caller still owns this traversal
     * @param callerSignal Cancels the traversal and its active HTTP request
     */
    async fetchStepsFromDeployment(
      deploymentId: number, ownsRefresh: () => boolean = () => true, callerSignal?: AbortSignal,
    ): Promise<void> {
      if (!callerSignal) {
        const traversal = this.traverseStepInventory(deploymentId, ownsRefresh);
        const resyncs = this.liveResyncs;
        resyncs[deploymentId] = traversal;
        void traversal.catch(() => false).finally(() => {
          if (resyncs[deploymentId] === traversal) delete resyncs[deploymentId];
        });
        await traversal;
        return;
      }
      // A cancellable refresh joins an in-flight resync instead of superseding it, so
      // cancelling the refresh never drops the resync's inventory. Until an inventory
      // is published, or the caller cancels or loses ownership, the refresh joins the
      // newest resync it has not joined yet or traverses again itself. An inventory
      // published by a traversal that started after this refresh also completes it.
      const since = this.fetchSequence;
      let joined: Promise<boolean> | undefined;
      while (!callerSignal.aborted && ownsRefresh() && (this.publishedGenerations[deploymentId] ?? 0) <= since) {
        const resync = this.liveResyncs[deploymentId];
        if (resync && resync !== joined) {
          joined = resync;
          if (await joinTraversal(resync, callerSignal)) return;
        } else if (await this.traverseStepInventory(deploymentId, ownsRefresh, callerSignal)) {
          return;
        }
      }
    },
    async traverseStepInventory(
      deploymentId: number, ownsRefresh: () => boolean, callerSignal?: AbortSignal,
    ): Promise<boolean> {
      const isCurrentSession = rememberSession();
      this.retainDeployment(deploymentId, true);
      this.fetching[deploymentId] = (this.fetching[deploymentId] ?? 0) + 1;
      const generation = ++this.fetchSequence;
      this.fetchGenerations[deploymentId] = generation;
      const changed = new Set<number>();
      const pendingFetches = this.pendingFetches;
      const pending = pendingFetches[deploymentId] ??= markRaw(new Set<Set<number>>());
      pending.add(changed);
      const controller = new AbortController();
      let timer: ReturnType<typeof setTimeout> | undefined;
      let cancel!: () => void;
      const interrupted = new Promise<never>((_resolve, reject) => {
        const abort = (reason: unknown) => {
          reject(reason);
          controller.abort(reason);
        };
        cancel = () => abort(callerSignal?.reason);
        callerSignal?.addEventListener("abort", cancel, { once: true });
        timer = setTimeout(() => {
          abort(new DOMException("Step inventory timed out. Try again.", "TimeoutError"));
        }, INVENTORY_TIMEOUT_MS);
      });
      try {
        this.inventoryComplete[deploymentId] ??= false;
        const steps: Step[] = [];
        let beforeId: number | null = null;
        let bytes = 0;
        // Count the bytes actually received on the wire, not a re-serialization of parsed JSON.
        const countBytes = (received: number) => {
          bytes += received;
          if (bytes > INVENTORY_MAX_BYTES) throw new Error("Step inventory is too large.");
        };
        while (true) {
          const params = new URLSearchParams({ deployment_id: deploymentId.toString(), limit: "25" });
          if (beforeId !== null) params.set("before_id", beforeId.toString());
          const options: BoundedOptions<"json"> = { signal: controller.signal, onBodyBytes: countBytes };
          const response = await Promise.race([interrupted, this.client.get<unknown>("steps/?" + params, options)]);
          if (controller.signal.aborted || !isCurrentSession() || !ownsRefresh() ||
              this.fetchGenerations[deploymentId] !== generation) return false;
          const page = stepPage(response, deploymentId, beforeId);
          if (steps.length + page.length > INVENTORY_MAX_ROWS) throw new Error("Step inventory is too large.");
          if (page.some(step => this.steps[step.id] && this.steps[step.id].deploymentId !== deploymentId)) {
            throw new Error("Invalid REST snapshot");
          }
          steps.push(...page);
          if (page.length < 25) break;
          beforeId = page[page.length - 1].id;
        }
        const present = new Set(steps.map(step => step.id));
        this.pruneSuspended++;
        try {
          for (const step of Object.values(this.stepsByDeployment[deploymentId] ?? {})) {
            if (!present.has(step.id) && !changed.has(step.id)) this.deleteStep(step);
          }
          for (const step of steps) {
            if (!changed.has(step.id)) this.addStep(step);
          }
        } finally {
          this.pruneSuspended--;
        }
        this.inventoryComplete[deploymentId] = true;
        this.publishedGenerations[deploymentId] = generation;
        return true;
      } finally {
        if (isCurrentSession()) {
          if (--this.fetching[deploymentId] === 0) delete this.fetching[deploymentId];
          this.pruneHistory();
        }
        clearTimeout(timer);
        callerSignal?.removeEventListener("abort", cancel);
        controller.abort();
        pending.delete(changed);
        if (!pending.size) delete pendingFetches[deploymentId];
      }
    },
    finishDeployment(id: number) {
      if (!this.retainedDeploymentIds.includes(id)) return;
      this.finishedDeployments[id] = true;
      delete this.stepsInProgressByDeployment[id];
    },
    /**
     * Event handler which is triggered by a message from the backend
     * which has the type "step". Steps can be added, updated or deleted.
     *
     * @param message {Message} the message which is received from the backend
     */
    onMessage(message: Message) {
      if (message.type === "step") {
        const step = message as Step;
        if (!step.deleted && !this.steps[step.id] && step.id <= (this.stepEventFloors[step.deploymentId] ?? 0)) return;
        const accepted = step.deleted ? this.deleteStep(step) : this.addStep(step);
        if (!accepted) return;
        for (const changed of this.pendingFetches[step.deploymentId] ?? []) changed.add(step.id);
      }
      if (message.type === "deployment") {
        const deployment = message as Deployment;
        if ((deployment.finished || deployment.deleted) && this.retainDeployment(deployment.id)) {
          this.finishDeployment(deployment.id);
        }
        this.pruneHistory();
      }
    },
  },
});
