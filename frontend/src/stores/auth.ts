import { createWebsocketClient } from "../websocket";
import { defineStore, acceptHMRUpdate } from "pinia";

import { getClientWithoutAuth } from "./httpClient";
import { useSteps } from "./step";
import { useSettings } from "./config";
import { useServices } from "./service";
import { useDeployments } from "./deployment";

export const useAuth = defineStore("auth", {
  state: () => {
    return {
      accessToken: null as string | null,
      username: "" as string,
      password: "" as string,
      errorMessage: null as string | null,
      client: getClientWithoutAuth(),
    };
  },
  getters: {
    isAuthenticated: (state) => {
      return !!state.accessToken;
    },
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useAuth, meta.hot));
      }
    },
    async initWebsocketClient() {
      const settings = useSettings();
      const websocketClient = createWebsocketClient();
      if (this.accessToken) {
        websocketClient.initWebsocketConnection(
          settings.websocket,
          this.accessToken
        );
      }

      // register store hooks for websocket events
      const stores = [useSteps(), useServices(), useDeployments()];
      for (const store of stores) {
        websocketClient.registerStore(store);
      }
    },
    async onLoginSuccess() {
      await this.initWebsocketClient();
      const serviceStore = useServices();
      serviceStore.fetchServices();
    },
    async login() {
      if (!this.username || !this.password) {
        this.errorMessage = "Please enter a username and password";
        return;
      }
      let formData = new FormData();
      formData.append("username", this.username);
      formData.append("password", this.password);
      const body =
        "grant_type=password&" +
        new URLSearchParams(formData as any).toString();
      const client = this.client;
      const options: any = client.options;
      options["body"] = body;
      options.headers["Content-Type"] =
        "application/x-www-form-urlencoded";
      await client
        .post<{ access_token: string }>("/token")
        .then((response) => {
          this.accessToken = response.access_token;
          if (this.isAuthenticated) {
            this.onLoginSuccess();
          }
        })
        .catch(() => {
          // response.json().detail is not included -> use own error message
          this.errorMessage = "Incorrect username or password";
        });
    },
  },
});
