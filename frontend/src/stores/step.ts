import { defineStore, acceptHMRUpdate } from "pinia";
import { getClient } from "./httpClient";
import { pythonToJavascript } from "../converters";
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
     * @param deploymentId {number} The deployment id
     * @returns steps {Step[]} The steps for the deployment
     */
    getStepsByDeployment: (state) => (deploymentId: number) => {
      if (state.stepsByDeployment[deploymentId]) {
        return Object.values(state.stepsByDeployment[deploymentId]);
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
        const scrollToStep = byDeploymentId[2];
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
      this.steps[step.id] = step;
      if (step.deploymentId) {
        if (!this.stepsByDeployment[step.deploymentId]) {
          this.stepsByDeployment[step.deploymentId] = {};
        }
        this.stepsByDeployment[step.deploymentId][step.id] = step;
        if (step.state == "running") {
          if (!(step.deploymentId in this.stepsInProgressByDeployment)) {
            this.stepsInProgressByDeployment[step.deploymentId] = [step];
          } else {
            // Add step to the list of steps in progress
            // to be able to scroll to the step before last step in progress.
            this.stepsInProgressByDeployment[step.deploymentId] = [step, ...this.stepsInProgressByDeployment[step.deploymentId]];
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
     * Fetch all steps for a deployment. This is used to fetch
     * all steps for a deployment after a deployment has been finished
     * and all steps are stored in the backend database.
     *
     * @param deploymentId {number} The deployment id
     */
    async fetchStepsFromDeployment(deploymentId: number) {
      const url =
        "steps/?" +
        new URLSearchParams({ deployment_id: deploymentId.toString() });
      const steps = await this.client.get<Promise<Object[]>>(url);
      for (const apiStep of steps) {
        this.addStep(pythonToJavascript(apiStep) as Step);
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
        if (step.deleted) {
          this.deleteStep(step);
        } else {
          this.addStep(step);
        }
      }
      if (message.type === "deployment") {
        const deployment = message as Deployment;
        if (deployment.finished) {
          // Deployment has finished -> remove scroll to metadata
          delete(this.stepsInProgressByDeployment[deployment.id]);
        }
      }
    },
  },
});
