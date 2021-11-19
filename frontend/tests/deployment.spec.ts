import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { Client, Deployment } from "../src/typings";
import { createClient } from "../src/client";
import { useDeployments, createDeployment } from "../src/stores/deployment";

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
let deploymentStore: any;

describe("Deployment Store Websocket", () => {
  beforeEach(() => {
    const app = createApp({});
    client = createClient();
    connection = new Connection();
    client.connection = connection;
    client.registerWebsocketConnectionCallbacks(client.connection);
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
      store.logMessages = true;
      store.messages = [];
    });
    app.use(pinia);
    setActivePinia(pinia);
    deploymentStore = useDeployments();
  });

  it("has no deployment store registered", () => {
    const deployment = createDeployment({
      id: 1,
      service_id: 1,
      origin: "GitHub",
      user: "deploy",
      created: new Date(),
    });
    connection.send(createEvent({ ...deployment, type: "deployment" }));
    expect(deploymentStore.deployments.size).toEqual(0);
  });

  it("has a deployment store registered", () => {
    client.registerStore(deploymentStore);
    const deployment = createDeployment({
      id: 1,
      service_id: 1,
      origin: "GitHub",
      user: "deploy",
      created: new Date(),
    });
    connection.send(createEvent({ ...deployment, type: "deployment" }));
    expect(deploymentStore.deployments.get(1).id).toBe(deployment.id);
  });
});

let deploymentsToFetch: Deployment[] = [];
let startedDeployment: Deployment;

function createStubClient() {
  // replace addService, deleteService functions from original
  // client with stubs
  const client = createClient();
  client.startDeployment = async (serviceName: string) => {
    return startedDeployment;
  };
  client.fetchDeployments = async () => {
    return deploymentsToFetch;
  };
  return client;
}

describe("Deployment Store Actions", () => {
  beforeEach(() => {
    const app = createApp({});
    client = createStubClient();
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
    });
    app.use(pinia);
    setActivePinia(pinia);
    deploymentStore = useDeployments();
  });

  it("starts a deployment", async () => {
    const deployment = createDeployment({
      id: 1,
      service_id: 1,
      origin: "GitHub",
      user: "deploy",
      created: new Date(),
    });
    startedDeployment = deployment;
    await deploymentStore.startDeployment("fastdeploy");
    expect(deploymentStore.deployments.get(1)).toStrictEqual(deployment);
  });
  it("fetches the list of deployments", async () => {
    const deployment = createDeployment({
      id: 1,
      service_id: 1,
      origin: "GitHub",
      user: "deploy",
      created: new Date(),
    });
    deploymentsToFetch = [deployment];
    await deploymentStore.fetchDeployments();
    expect(deploymentStore.deployments.get(1).id).toBe(deployment.id);
  });
});
