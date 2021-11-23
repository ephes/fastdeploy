import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { Client, Deployment } from "../src/typings";
import { createClient, snakeToCamel } from "../src/client";
import { useDeployments } from "../src/stores/deployment";

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
let deploymentsStore: any;

const deployment: Deployment = {
  id: 1,
  service_id: 1,
  origin: "GitHub",
  user: "deploy",
  created: "2021-11-23T10:03:01.276Z",
  type: "deployment",
};

describe("Deployment Store Websocket", () => {
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
    deploymentsStore = useDeployments();
  });

  it("has no deployments store registered", () => {
    connection.send(createEvent({ ...deployment, type: "deployment" }));
    expect(deploymentsStore.deployments).toStrictEqual({});
  });

  it("has a deployments store registered", () => {
    client.registerStore(deploymentsStore);
    connection.send(createEvent({ ...deployment, type: "deployment" }));
    expect(deploymentsStore.deployments[deployment.id]).toStrictEqual(
      snakeToCamel(deployment)
    );
  });
});

let deploymentsToFetch: Deployment[] = [];

function createStubClient() {
  // replace startDeployment, fetchDeployments functions from original
  // client with stubs
  const client = createClient();
  client.startDeployment = async (serviceName: string) => {
    return deployment;
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
    deploymentsStore = useDeployments();
  });

  it("starts a deployment", async () => {
    await deploymentsStore.startDeployment("fastdeploy");
    expect(deploymentsStore.deployments[deployment.id]).toStrictEqual(
      deployment
    );
  });

  it("fetches the list of deployments", async () => {
    deploymentsToFetch = [deployment];
    await deploymentsStore.fetchDeployments();
    expect(deploymentsStore.deployments[deployment.id]).toStrictEqual(
      deployment
    );
  });
});
