import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { Client, Step } from "../src/typings";
import { createClient, snakeToCamel } from "../src/websocket";
import { useSteps } from "../src/stores/step";
import {
  createStubWebsocketConnection,
  Connection,
  createEvent,
} from "./conftest";

let client: Client;
let connection: Connection;
let stepsStore: any;

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
    const app = createApp({});
    client = createClient();
    client.websocket = createStubWebsocketConnection();
    connection = client.websocket.connection;
    client.websocket.registerWebsocketConnectionCallbacks(connection);
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
    });
    app.use(pinia);
    setActivePinia(pinia);
    stepsStore = useSteps();
  });

  it("has no steps store registered", () => {
    connection.send(createEvent(apiStep));
    expect(stepsStore.steps).toStrictEqual({});
  });

  it("has a steps store registered", () => {
    client.websocket.registerStore(stepsStore);
    connection.send(createEvent(apiStep));
    expect(stepsStore.steps[step.id]).toStrictEqual(step);
  });
});

let stepsToFetch: Object[] = [];

function createStubClient() {
  // replace  functions from original
  // client with stub
  const client = createClient();
  client.websocket = createStubWebsocketConnection();
  connection = client.websocket.connection;
  client.websocket.registerWebsocketConnectionCallbacks(connection);
  client.fetchStepsFromDeployment = async (deploymentId: number) => {
    return stepsToFetch.map((step) => snakeToCamel(step));
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
    stepsToFetch = [apiStep];
    await stepsStore.fetchStepsFromDeployment(step.deploymentId);
    expect(stepsStore.steps[step.id]).toStrictEqual(step);
  });
});
