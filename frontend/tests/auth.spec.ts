import { createApp } from "vue";
import { setActivePinia, createPinia } from "pinia";

import { useAuth } from "../src/stores/auth";
// import {
//   createStubWebsocketConnection,
//   Connection,
//   createEvent,
// } from "./conftest";

// function createStubClient() {
//   // replace login function from original client with stub
//   client.websocket = createStubWebsocketConnection();
//   connection = client.websocket.connection;
//   client.websocket.registerWebsocketConnectionCallbacks(connection);
//   client.login = async (username: string, password: string) => {
//     return loginResponse;
//   };
//   client.websocket.initWebsocketConnection = (settings: any) => {
//     // initWebsocketConnection is called after login
//   };
//   client.fetchServices = async () => {
//     // fetchServices is called via authStore.onLogin
//     return []
//   };
//   return client;
// }

describe("Auth Store Actions", () => {
  beforeEach(() => {
    const app = createApp({});
    const pinia = createPinia();
    app.use(pinia);
    setActivePinia(pinia);
  });

  it("returns early if username or password are not set", async () => {
    const authStore = useAuth();
    authStore.username = "user";
    authStore.password = "";
    expect(authStore.errorMessage).toBe(null);
    await authStore.login();
    expect(authStore.errorMessage).toBe("Please enter a username and password");
  });

  it("calls login with error", async () => {
    const authStore = useAuth();
    authStore.username = "user";
    authStore.password = "password";
    authStore.client = {
      async post<T = unknown>(): Promise<T> {
        return new Promise<any>(() => {
          throw Error("Incorrect username or password")
        });
      },
      options: {headers: {}, body: ""},
    };
    expect(authStore.errorMessage).toBe(null);
    await authStore.login();
    expect(authStore.errorMessage).toBe("Incorrect username or password");
  });

  it("calls login successfully", async () => {
    const authStore = useAuth();
    authStore.username = "user";
    authStore.password = "password";
    authStore.client = {
      async post<T = unknown>(): Promise<T> {
        return new Promise<any>((resolve, reject) => {
          resolve({access_token: "access_token"});
        });
      },
      options: {headers: {}, body: ""},
    };
    authStore.onLoginSuccess = jest.fn();  // mock onLoginSuccess action
    expect(authStore.isAuthenticated).toBe(false);
    await authStore.login();
    expect(authStore.isAuthenticated).toBe(true);
  });
});
