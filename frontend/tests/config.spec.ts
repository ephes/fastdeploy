import "pinia";
import { createApp } from "vue";
import { setActivePinia, createPinia } from "pinia";
import {
  useSettings,
  API_BASE_DEFAULT,
  WEBSOCKET_URL_DEFAULT,
  ENV_DEFAULT,
} from "../src/stores/config";

describe("Settings Store", () => {
  beforeEach(() => {
    const app = createApp({});
    const pinia = createPinia().use(({ store }) => {
      store.env = { ...ENV_DEFAULT };
    });
    app.use(pinia);
    setActivePinia(pinia);
  });

  it("has right backend api url", () => {
    const testCases = [
      // [prod, vite_api_base_dev, vite_api_base_prod, expected]
      [false, "", "", API_BASE_DEFAULT], // default
      [
        false,
        "",
        "http://production.example.com:9999",
        API_BASE_DEFAULT,
      ],
      [
        // happy path
        false,
        "http://localhost:9999",
        "http://production.example.com:9999",
        "http://localhost:9999",
      ],
      [true, "", "", API_BASE_DEFAULT], // default
      [true, "http://localhost:9999", "", API_BASE_DEFAULT],
      [
        // happy path
        true,
        "http://localhost:9999",
        "http://production.example.com:9999",
        "http://production.example.com:9999",
      ],
    ] as const;
    const settings = useSettings();
    for (const [
      prod,
      vite_api_base_dev,
      vite_api_base_prod,
      expected,
    ] of testCases) {
      settings.env.PROD = prod;
      settings.env.VITE_API_BASE_DEV = vite_api_base_dev;
      settings.env.VITE_API_BASE_PROD = vite_api_base_prod;
      expect(settings.api).toBe(expected);
    }
  });
  it("has right websocket url", () => {
    const testCases = [
      // [prod, vite_websocket_url_dev, vite_websocket_url_prod, expected]
      [false, "", "", WEBSOCKET_URL_DEFAULT], // default
      [
        false,
        "",
        "ws://production.example.com/deployments/ws",
        WEBSOCKET_URL_DEFAULT,
      ],
      [
        // happy path
        false,
        "ws://localhost:9999/deployments/ws",
        "ws://production.example.com/deployments/ws",
        "ws://localhost:9999/deployments/ws",
      ],
      [true, "", "", WEBSOCKET_URL_DEFAULT], // default
      [
        true,
        "ws://localhost:9999/deployments/ws",
        "",
        WEBSOCKET_URL_DEFAULT,
      ],
      [
        // happy path
        true,
        "ws://localhost:9999/deployments/ws",
        "ws://production.example.com/deployments/ws",
        "ws://production.example.com/deployments/ws",
      ],
    ] as const;
    const settings = useSettings();
    for (const [
      prod,
      vite_websocket_url_dev,
      vite_websocket_url_prod,
      expected,
    ] of testCases) {
      settings.env.PROD = prod;
      settings.env.VITE_WEBSOCKET_URL_DEV = vite_websocket_url_dev;
      settings.env.VITE_WEBSOCKET_URL_PROD = vite_websocket_url_prod;
      expect(settings.websocket).toBe(expected);
    }
  });
});
