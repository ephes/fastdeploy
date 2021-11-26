import "pinia";
import { createApp, markRaw } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { Client } from "../src/typings";
import { useAuth } from "../src/stores/auth";
import { createClient } from "../src/websocket";
import {
  createStubWebsocketConnection,
  Connection,
  createEvent,
} from "./conftest";

let client: Client;
let connection: Connection;
let authStore: any;
let loginResponse: any;

function createStubClient() {
  // replace login function from original client with stub
  const client = createClient();
  client.websocket = createStubWebsocketConnection();
  connection = client.websocket.connection;
  client.websocket.registerWebsocketConnectionCallbacks(connection);
  client.login = async (username: string, password: string) => {
    return loginResponse;
  };
  client.websocket.initWebsocketConnection = (settings: any) => {
    // initWebsocketConnection is called after login
  };
  client.fetchServices = async () => {
    // fetchServices is called via authStore.onLogin
    return []
  };
  return client;
}

describe("Auth Store Actions", () => {
  beforeEach(() => {
    const app = createApp({});
    client = createStubClient();
    const pinia = createPinia().use(({ store }) => {
      store.client = markRaw(client);
    });
    app.use(pinia);
    setActivePinia(pinia);
    authStore = useAuth();
  });

  it("calls login with error", async () => {
    authStore.username = "user";
    authStore.password = "password";
    loginResponse = {accessToken: null, errorMessage: "Incorrect username or password"};
    await authStore.login();
    expect(authStore.accessToken).toBe(null);
    expect(authStore.isAuthenticated).toBe(false);
    expect(authStore.errorMessage).toBe("Incorrect username or password");
  });

  it("calls login successfully", async () => {
    authStore.username = "user";
    authStore.password = "password";
    loginResponse = {accessToken: "accessToken", errorMessage: null};
    await authStore.login();
    expect(authStore.accessToken).toBe("accessToken");
    expect(authStore.isAuthenticated).toBe(true);
    expect(authStore.errorMessage).toBe(null);
  });
});
