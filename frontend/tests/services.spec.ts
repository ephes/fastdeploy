import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";
import { useServices } from "../src/stores/services";
import { Client } from "../src/typings";
import { createClient } from "../src/client";

declare module "pinia" {
  export interface PiniaCustomProperties {
    client: Client;
  }
}

const connection = {};

describe("Services Store", () => {
  beforeEach(() => {
    const app = createApp({});
    const client = createClient();
    client.connection = connection;
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
    });
    app.use(pinia);
    setActivePinia(pinia);
  });

  it("dummy test", () => {
    const services = useServices();
    console.debug("connection: ", services.client.connection);
    services.client.connection.onMessage({"foo": "bar"});
    expect("foo").toBe("foo");
  });
});
