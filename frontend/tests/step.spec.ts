import { Step } from "../src/typings";
import { pythonToJavascript } from "../src/converters";
import { createWebsocketClient } from "../src/websocket";
import { useSteps } from "../src/stores/step";
import { createEvent, initPinia } from "./conftest";

const apiStep: object = {
  id: 1,
  name: "Create unix user deploy",
  state: "pending",
  changed: true,
  deployment_id: 1,
  created: "2021-11-23T10:03:01.276123",
  started: "2021-11-23T10:04:01.276123",
  finished: null,
  deleted: false,
  type: "step",
};

const step: Step = pythonToJavascript(apiStep) as Step;

describe("Steps Store Websocket", () => {
  beforeEach(() => {
    initPinia();
  });

  it("has no steps store registered", () => {
    const stepsStore = useSteps();
    const websocketClient = createWebsocketClient();
    websocketClient.onMessage(createEvent(apiStep));
    expect(stepsStore.steps).toStrictEqual({});
  });

  it("has a steps store registered", () => {
    const stepsStore = useSteps();
    const websocketClient = createWebsocketClient();
    websocketClient.registerStore(stepsStore);
    websocketClient.onMessage(createEvent(apiStep));
    expect(stepsStore.steps[step.id]).toStrictEqual(step);
  });
});

describe("Steps Store Actions", () => {
  beforeEach(() => {
    initPinia();
  });

  it("fetches the list of steps for a deployment", async () => {
    const stepsStore = useSteps();
    stepsStore.client = {
      async get<T = unknown>(url: string | number): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve([apiStep]);
        });
      },
      options: { headers: {} },
    } as any;
    await stepsStore.fetchStepsFromDeployment(step.deploymentId);
    expect(stepsStore.steps[step.id]).toStrictEqual(step);
  });
});

describe("Steps Store Getters", () => {
  beforeEach(() => {
    initPinia();
  });

  it("Steps by deployment returns a list of steps", () => {
    const stepsStore = useSteps();
    stepsStore.addStep(step);
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual([step]);
  });
});
