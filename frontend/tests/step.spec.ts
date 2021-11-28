import { Step } from "../src/typings";
import { snakeToCamel } from "../src/converters";
import { createWebsocketClient } from "../src/websocket";
import { useSteps } from "../src/stores/step";
import { createEvent, initPinia } from "./conftest";

const apiStep: object = {
  id: 1,
  name: "Create unix user deploy",
  state: null,
  changed: true,
  in_progress: true,
  deployment_id: 1,
  done: false,
  created: "2021-11-23T10:03:01.276Z",
  started: "2021-11-23T10:04:01.276Z",
  finished: null,
  deleted: false,
  type: "step",
};

const step: Step = snakeToCamel(apiStep);

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
      async  get<T = unknown>(url: string | number): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve([apiStep]);
        });
      },
      options: {headers: {}},
    } as any;
    await stepsStore.fetchStepsFromDeployment(step.deploymentId);
    expect(stepsStore.steps[step.id]).toStrictEqual(step);
  });
});
