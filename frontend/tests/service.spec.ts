import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { Client, Service } from "../src/typings";
import { createClient } from "../src/client";
import { useServices, createService } from "../src/stores/service";

declare module "pinia" {
  export interface PiniaCustomProperties {
    client: Client;
    logMessages: boolean;
    messages: any[];
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
let serviceStore: any;

describe("Services Store Websocket", () => {
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
    serviceStore = useServices();
  });

  it("has no store registered", () => {
    connection.send(createEvent({ foo: "bar" }));
    expect(serviceStore.messages).toEqual([]);
  });

  it("has a store registered", () => {
    client.registerStore(serviceStore);
    const payload = { foo: "bar" };
    connection.send(createEvent(payload));
    expect(serviceStore.messages[0]).toStrictEqual(payload);
  });

  it("received create or update service", () => {
    client.registerStore(serviceStore);
    const service = {
      id: 1,
      name: "fastdeploy",
      collect: "collect.py",
      deploy: "deploy.sh",
      deleted: false,
    };
    const payload = {
      ...service,
      type: "service",
    };
    connection.send(createEvent(payload));
    expect(serviceStore.messages[0]).toStrictEqual(payload);
    expect(serviceStore.services.get(1)).toStrictEqual(service);
  });

  it("received delete service", () => {
    client.registerStore(serviceStore);
    const service = {
      id: 1,
      name: "fastdeploy",
      collect: "collect.py",
      deploy: "deploy.sh",
      deleted: false,
    };
    serviceStore.services.set(1, service);
    const payload = {
      ...service,
      type: "service",
      deleted: true,
    };
    connection.send(createEvent(payload));
    expect(serviceStore.messages[0]).toStrictEqual(payload);
    expect(serviceStore.services.size).toBe(0);
  });

  it("adds a service to the store", () => {
    client.registerStore(serviceStore);
    const payload = { foo: "bar" };
    connection.send(createEvent(payload));
    expect(serviceStore.messages[0]).toStrictEqual(payload);
  });
});

let servicesToFetch: Service[] = [];

function createStubClient() {
  // replace addService, deleteService functions from original
  // client with stubs
  const client = createClient();
  client.addService = async (service: any) => {
    console.log("add service in dummy client: ", service);
    return { ...service, id: 1 };
  };
  client.deleteService = async (id: number) => {
    return id;
  };
  client.fetchServices = async () => {
    return servicesToFetch;
  };
  return client;
}

describe("Services Store Actions", () => {
  beforeEach(() => {
    const app = createApp({});
    client = createStubClient();
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
    });
    app.use(pinia);
    setActivePinia(pinia);
    serviceStore = useServices();
  });

  it("adds a service to the store", async () => {
    const service = createService({
      name: "fastdeploy",
      collect: "collect.py",
      deploy: "deploy.sh",
    });
    serviceStore.new = service;
    await serviceStore.addService();
    expect(serviceStore.services.get(1)).toStrictEqual({ ...service, id: 1 });
  });

  it("deletes a service from the store", async () => {
    const service = createService({
      id: 1,
      name: "fastdeploy",
      collect: "collect.py",
      deploy: "deploy.sh",
    });
    serviceStore.services.set(1, service);
    expect(serviceStore.services.get(1)).toStrictEqual(service);
    await serviceStore.deleteService(service.id);
    expect(serviceStore.services.size).toBe(0);
  });

  it("fetches the list of services", async () => {
    const service = createService({
      id: 1,
      name: "fastdeploy",
      collect: "collect.py",
      deploy: "deploy.sh",
    });
    servicesToFetch = [service];
    await serviceStore.fetchServices();
    expect(serviceStore.services.get(1)).toStrictEqual(service);
  });
});
