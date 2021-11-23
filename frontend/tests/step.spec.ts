import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { Client, Step } from "../src/typings";
import { createClient, snakeToCamel } from "../src/client";
import { useSteps } from "../src/stores/step";

declare module "pinia" {
  export interface PiniaCustomProperties {
    client: Client;
  }
}

class Connection {
  onmessage = (message: any) => {};
  send = (message: MessageEvent) => {
    this.onmessage(message);
  };
}

function createEvent(data: any): MessageEvent {
  return { data: JSON.stringify(data) } as MessageEvent;
}

let client: Client;
let connection: Connection;
let stepsStore: any;

const step: Step = {
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
};

describe("Steps Store Websocket", () => {
  beforeEach(() => {
    const app = createApp({});
    client = createClient();
    connection = new Connection();
    client.connection = connection;
    client.registerWebsocketConnectionCallbacks(client.connection);
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
    });
    app.use(pinia);
    setActivePinia(pinia);
    stepsStore = useSteps();
  });

  it("has no steps store registered", () => {
    connection.send(createEvent({ ...step, type: "step" }));
    expect(stepsStore.steps).toStrictEqual({});
  });

  it("has a steps store registered", () => {
    client.registerStore(stepsStore);
    connection.send(createEvent({ ...step, type: "step" }));
    expect(stepsStore.steps[step.id]).toStrictEqual(
      snakeToCamel(step)
    );
  });
});

let stepsToFetch: Step[] = [];

function createStubClient() {
  // replace  functions from original
  // client with stub
  const client = createClient();
  client.fetchStepsFromDeployment = async (deploymentId: number) => {
    return stepsToFetch;
  };
  return client;
}

describe("Steps Store Actions", () => {
  beforeEach(() => {
    const app = createApp({});
    client = createStubClient();
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
    });
    app.use(pinia);
    setActivePinia(pinia);
    stepsStore = useSteps();
  });

  it("fetches the list of steps for a deployment", async () => {
    stepsToFetch = [step];
    await stepsStore.fetchStepsFromDeployment(step.deploymentId);
    expect(stepsStore.deployments[step.id]).toStrictEqual(
      step
    );
  });
});
