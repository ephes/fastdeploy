import { defineStore, acceptHMRUpdate } from "pinia";
import { getClient } from "./sharedGetters";
import { snakeToCamel } from "../converters";
import { Step, StepById, Message } from "../typings";

export const useSteps = defineStore("steps", {
  state: () => {
    return {
      steps: {} as StepById,
      stepsByDeployment: {} as { [deploymentId: number]: StepById },
    };
  },
  getters: {
    getClient: () => getClient,
    getStepsByDeployment: (state) => (deploymentId: number) => {
      if (state.stepsByDeployment[deploymentId]) {
        return state.stepsByDeployment[deploymentId];
      } else {
        return {};
      }
    },
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useSteps, meta.hot));
      }
    },
    addStep(step: Step) {
      this.steps[step.id] = step;
      if (step.deploymentId) {
        if (!this.stepsByDeployment[step.deploymentId]) {
          this.stepsByDeployment[step.deploymentId] = {};
        }
        this.stepsByDeployment[step.deploymentId][step.id] = step;
      } else {
        console.log("step without deploymentId", step);
      }
    },
    deleteStep(step: Step) {
      delete this.steps[step.id];
      delete this.stepsByDeployment[step.deploymentId][step.id];
    },
    async fetchStepsFromDeployment(deploymentId: number) {
      const url =
        "steps/?" +
        new URLSearchParams({ deployment_id: deploymentId.toString() });
      const steps = await this.getClient().get<Promise<Object[]>>(url);
      for (const apiStep of steps) {
        this.addStep(snakeToCamel(apiStep));
      }
    },
    onMessage(message: Message) {
      if (message.type === "step") {
        const step = message as Step;
        if (step.deleted) {
          this.deleteStep(step);
        } else {
          this.addStep(step);
        }
      }
    },
  },
});
