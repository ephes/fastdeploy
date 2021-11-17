import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";
import { useSettings, API_BASE_DEFAULT, WEBSOCKET_URL_DEFAULT, ENV_DEFAULT } from "../src/stores/config";
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
      store.env = {...ENV_DEFAULT};
      store.client = markRaw(client);
      store.client.connection = {};
      store.client.connection["registered"] = [store];
    });
    app.use(pinia);
    setActivePinia(pinia);
  });

  it("has right backend api url", () => {
    const testCases = [
      // [mode, vite_api_base_dev, vite_api_base_prod, expected]
      ["development", "", "", API_BASE_DEFAULT], // default
      ["", "http://localhost:9999", "", API_BASE_DEFAULT],
      [
        "development",
        "",
        "http://production.example.com:9999",
        API_BASE_DEFAULT,
      ],
      [
        // happy path
        "development",
        "http://localhost:9999",
        "http://production.example.com:9999",
        "http://localhost:9999",
      ],
      ["production", "", "", API_BASE_DEFAULT], // default
      ["", "", "http://production.example.com:9999", API_BASE_DEFAULT],
      [
        "production",
        "http://localhost:9999",
        "",
        API_BASE_DEFAULT,
      ],
      [
        // happy path
        "production",
        "http://localhost:9999",
        "http://production.example.com:9999",
        "http://production.example.com:9999",
      ],
    ];
    const settings = useSettings();
    // settings.env = ENV_DEFAULT;  // dunno why this is needed
    for (const [
      mode,
      vite_api_base_dev,
      vite_api_base_prod,
      expected,
    ] of testCases) {
      settings.env.MODE = mode;
      settings.env.VITE_API_BASE_DEV = vite_api_base_dev;
      settings.env.VITE_API_BASE_PROD = vite_api_base_prod;
      expect(settings.api).toBe(expected);
    }
  });
  it("has right websocket url", () => {
    const testCases = [
      // [mode, vite_websocket_url_dev, vite_websocket_url_prod, expected]
      ["development", "", "", WEBSOCKET_URL_DEFAULT], // default
      ["", "ws://localhost:9999/deployments/ws", "", WEBSOCKET_URL_DEFAULT],
      [
        "development",
        "",
        "ws://production.example.com/deployments/ws",
        WEBSOCKET_URL_DEFAULT,
      ],
      [
        // happy path
        "development",
        "ws://localhost:9999/deployments/ws",
        "ws://production.example.com/deployments/ws",
        "ws://localhost:9999/deployments/ws",
      ],
      ["production", "", "", WEBSOCKET_URL_DEFAULT], // default
      ["", "", "ws://production.example.com/deployments/ws", WEBSOCKET_URL_DEFAULT],
      [
        "production",
        "ws://localhost:9999/deployments/ws",
        "",
        WEBSOCKET_URL_DEFAULT,
      ],
      [
        // happy path
        "production",
        "ws://localhost:9999/deployments/ws",
        "ws://production.example.com/deployments/ws",
        "ws://production.example.com/deployments/ws",
      ],
    ];
    const settings = useSettings();
    for (const [
      mode,
      vite_websocket_url_dev,
      vite_websocket_url_prod,
      expected,
    ] of testCases) {
      settings.env.MODE = mode;
      settings.env.VITE_WEBSOCKET_URL_DEV = vite_websocket_url_dev;
      settings.env.VITE_WEBSOCKET_URL_PROD = vite_websocket_url_prod;
      expect(settings.websocket).toBe(expected);
    }
  });
});
