import { markRaw } from "vue";
import { defineStore, acceptHMRUpdate } from "pinia";
import { getClient } from "./httpClient";
import { rememberSession } from "./session";
import { stepPage } from "../restAdmission";
import { Step, StepById, Message, Deployment } from "../typings";

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
      deletedSteps: {} as Record<number, boolean>,
      finishedDeployments: {} as Record<number, boolean>,
      pendingFetches: [] as Set<number>[],
      fetchGenerations: {} as Record<number, number>,
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
      const byDeploymentId = state.stepsInProgressByDeployment[step.deploymentId];
      if (byDeploymentId) {
        const scrollToStep = byDeploymentId[4];
        if (scrollToStep) {
          if (scrollToStep.id === step.id) {
            return true;
          }
        }
      }
      return false;
    }
  },
  actions: {
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
    addStep(step: Step) {
      const current = this.steps[step.id];
      if (this.deletedSteps[step.id] || (current && current.deploymentId !== step.deploymentId)) return;
      // One persisted id is one lifecycle; a rerun receives a fresh id.
      const rank = (state: string) => state === "pending" ? 0 : state === "running" ? 1 : 2;
      if (current && (rank(step.state) < rank(current.state) ||
          (rank(current.state) === 2 && step.state !== current.state))) return;
      this.steps[step.id] = step;
      if (step.deploymentId) {
        if (!this.stepsByDeployment[step.deploymentId]) {
          this.stepsByDeployment[step.deploymentId] = {};
        }
        this.stepsByDeployment[step.deploymentId][step.id] = step;
        if (step.state == "running" && current?.state !== "running" && !this.finishedDeployments[step.deploymentId]) {
          if (!(step.deploymentId in this.stepsInProgressByDeployment)) {
            this.stepsInProgressByDeployment[step.deploymentId] = [step];
          } else if (!this.stepsInProgressByDeployment[step.deploymentId].some(existing => existing.id === step.id)) {
            // Add step to the list of steps in progress
            // to be able to scroll to the step before last step in progress.
            this.stepsInProgressByDeployment[step.deploymentId] = [step, ...this.stepsInProgressByDeployment[step.deploymentId]].slice(0, 5);
          }
        }
      } else {
        console.log("step without deploymentId", step);
      }
    },
    /**
     * Delete step from store. Deleted steps are just normal steps
     * with an attribute "deleted" set to true.
     *
     * @param step {Step} The step to delete
     */
    deleteStep(step: Step) {
      this.deletedSteps[step.id] = true;
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
        }
      }
    },
    /**
     * Traverse bounded step pages and publish only a completed inventory.
     * WebSocket changes remain authoritative throughout the traversal.
     *
     * @param deploymentId {number} The deployment id
     */
    async fetchStepsFromDeployment(deploymentId: number, ownsRefresh: () => boolean = () => true) {
      const isCurrentSession = rememberSession();
      const generation = (this.fetchGenerations[deploymentId] ?? 0) + 1;
      this.fetchGenerations[deploymentId] = generation;
      const changed = markRaw(new Set<number>());
      this.pendingFetches.push(changed);
      try {
        this.inventoryComplete[deploymentId] = false;
        const steps: Step[] = [];
        let beforeId: number | null = null;
        while (true) {
          const params = new URLSearchParams({ deployment_id: deploymentId.toString(), limit: "25" });
          if (beforeId !== null) params.set("before_id", beforeId.toString());
          const response = await this.client.get<unknown>("steps/?" + params);
          if (!isCurrentSession() || !ownsRefresh() || this.fetchGenerations[deploymentId] !== generation) return;
          const page = stepPage(response, deploymentId, beforeId);
          if (page.some(step => this.steps[step.id] && this.steps[step.id].deploymentId !== deploymentId)) {
            throw new Error("Invalid REST snapshot");
          }
          steps.push(...page);
          if (page.length < 25) break;
          beforeId = page[page.length - 1].id;
        }
        const present = new Set(steps.map(step => step.id));
        for (const step of Object.values(this.stepsByDeployment[deploymentId] ?? {})) {
          if (!present.has(step.id) && !changed.has(step.id)) this.deleteStep(step);
        }
        for (const step of steps) {
          if (!changed.has(step.id)) this.addStep(step);
        }
        this.inventoryComplete[deploymentId] = true;
      } finally {
        this.pendingFetches = this.pendingFetches.filter(pending => pending !== changed);
      }
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
        for (const pending of this.pendingFetches) pending.add(step.id);
        if (step.deleted) {
          this.deleteStep(step);
        } else {
          this.addStep(step);
        }
      }
      if (message.type === "deployment") {
        const deployment = message as Deployment;
        if (deployment.finished || deployment.deleted) {
          this.finishedDeployments[deployment.id] = true;
          // Deployment has finished -> remove scroll to metadata
          delete(this.stepsInProgressByDeployment[deployment.id]);
        }
      }
    },
  },
});
