import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";
import { useServices } from "../src/stores/service";
import { Client } from "../src/typings";
import { createClient } from "../src/client";

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

describe("Services Store", () => {
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
    }
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
    }
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
});
