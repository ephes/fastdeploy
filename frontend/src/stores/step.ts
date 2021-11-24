import { defineStore, acceptHMRUpdate } from "pinia";
import { Step, StepById, Message } from "../typings";

export const useSteps = defineStore("steps", {
  state: () => {
    return {
      steps: {} as StepById,
      stepsByDeployment: {} as { [deploymentId: number]: StepById },
    };
  },
  getters: {
    getStepByDeployment: (state) => (deploymentId: number) => {
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
      if(step.deploymentId) {
        if(!this.stepsByDeployment[step.deploymentId]) {
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
      const steps = await this.client.fetchStepsFromDeployment(deploymentId);
      for (const step of steps) {
        this.addStep(step);
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
