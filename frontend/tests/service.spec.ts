import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { Client, Service, ServiceWithId } from "../src/typings";
import { createClient } from "../src/client";
import { useServices } from "../src/stores/service";

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

function createEvent(data: object): MessageEvent {
  return { data: JSON.stringify(data) } as MessageEvent;
}

let client: Client;
let connection: Connection;
let serviceStore: any;

const service: ServiceWithId = {
  id: 1,
  name: "fastdeploy",
  collect: "collect.py",
  deploy: "deploy.sh",
  type: "service",
}

describe("Services via Store Websocket", () => {
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
    serviceStore = useServices();
  });

  it("has no service store registered", () => {
    connection.send(createEvent(service));
    expect(serviceStore.services).toStrictEqual({});
  });

  it("received create or update service", () => {
    client.registerStore(serviceStore);
    connection.send(createEvent(service));
    expect(serviceStore.services[service.id]).toStrictEqual(service);
  });

  it("received delete service", () => {
    client.registerStore(serviceStore);
    serviceStore.services[service.id] = service;
    connection.send(createEvent({...service, deleted: true}));
    expect(serviceStore.services).toStrictEqual({});
  });
});

let servicesToFetch: ServiceWithId[] = [];

function createStubClient() {
  // replace addService, deleteService functions from original
  // client with stubs
  const client = createClient();
  client.addService = async (service: any) => {
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
    const newService: Service = {
      name: "fastdeploy",
      collect: "collect.py",
      deploy: "deploy.sh",
    };
    serviceStore.new = newService;
    await serviceStore.addService();
    expect(serviceStore.services[1]).toStrictEqual({ ...newService, id: 1 });
  });

  it("deletes a service from the store", async () => {
    serviceStore.services[service.id] = service;
    await serviceStore.deleteService(service.id);
    expect(serviceStore.services).toStrictEqual({});
  });

  it("fetches the list of services", async () => {
    servicesToFetch = [service];
    await serviceStore.fetchServices();
    expect(serviceStore.services[service.id]).toStrictEqual(service);
  });
});
