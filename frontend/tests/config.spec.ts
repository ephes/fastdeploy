import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";
import { useSettings } from "../src/stores/config";
import { Environment, Client } from "../src/typings";
import { createClient } from "../src/client";

declare module "pinia" {
  export interface PiniaCustomProperties {
    env: Environment;
    client: Client;
  }
}

const app = createApp({});
// const client = createClient();
const client = {} as Client;

describe("Settings Store", () => {
  beforeEach(() => {
    const pinia = createPinia().use(({ store }) => {
      store.env = {
        MODE: "development",
      };
      store.client = markRaw(client);
      store.client.connection = {};
      store.client.connection["registered"] = [store];
    });
    app.use(pinia);
    setActivePinia(pinia);
  });

  it("has localhost backend by default", () => {
    const settings = useSettings();
    console.debug("settings env? ", settings.env);
    console.debug("settings env MODE? ", settings.env.MODE);
    expect(settings.api).toBe("http://localhost:8000");
    expect(settings.env.MODE).toBe("development");
    settings.env.MODE = "production";
    console.debug("settings env MODE? ", settings.env.MODE);
    console.debug("settings client ", settings.client);
  });
});
