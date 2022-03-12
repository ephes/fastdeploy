import { Step } from "../src/typings";
import { pythonToJavascript } from "../src/converters";
import { createWebsocketClient } from "../src/websocket";
import { useSteps } from "../src/stores/step";
import { createEvent, initPinia } from "./conftest";

const apiStep: object = {
  id: 1,
  name: "Create unix user deploy",
  state: "pending",
  deployment_id: 1,
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
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual([
      step,
    ]);
  });

  it("Steps by deployment sorts finished above not finished", async () => {
    const stepsStore = useSteps();
    const withoutFinished = step;
    stepsStore.addStep(withoutFinished);
    const withFinished = {
      ...withoutFinished,
      id: 2,
      finished: withoutFinished.started,
    };
    stepsStore.addStep(withFinished);
    const expected = [withFinished, withoutFinished];
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual(
      expected
    );
  });

  it("Steps by deployment sorts earlier finished above later", async () => {
    const stepsStore = useSteps();
    const earlier = {...step, finished: step.started};
    const laterDate = new Date((earlier.finished as Date).getTime() + 1000);
    const later = {...earlier, id: 2, finished: laterDate};
    stepsStore.addStep(later);
    stepsStore.addStep(earlier);
    const expected = [earlier, later];
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual(
      expected
    );
  });

  it("Steps by deployment sorts started above not started", async () => {
    const stepsStore = useSteps();
    const withStarted = step;
    const withoutStarted = {...withStarted, id: 2, started: null};
    stepsStore.addStep(withoutStarted);
    stepsStore.addStep(withStarted);
    const expected = [withStarted, withoutStarted];
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual(
      expected
    );
  });
});
