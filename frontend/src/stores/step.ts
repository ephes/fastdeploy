import { defineStore, acceptHMRUpdate } from "pinia";
import { Step, StepById, Message } from "../typings";

export const useSteps = defineStore("steps", {
  state: () => {
    return {
      steps: {} as StepById,
    };
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useSteps, meta.hot));
      }
    },
    async fetchStepsFromDeployment(deploymentId: number) {
      const steps = await this.client.fetchStepsFromDeployment(deploymentId);
      for (const step of steps) {
        this.steps[step.id] = step;
      }
    },
    onMessage(message: Message) {
      if (message.type === "step") {
        const step = message as Step;
        if (step.deleted) {
          delete this.steps[step.id];
        } else {
          this.steps[step.id] = step;
        }
      }
    },
  },
});
