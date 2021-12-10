import { createWebsocketClient } from "../websocket";
import { defineStore, acceptHMRUpdate } from "pinia";

import { getClientWithoutAuth, getClient } from "./httpClient";
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
      router: null as any,
    };
  },
  getters: {
    /**
     * This is used by vue router to determine whether the user is logged in or not.
     * @returns true if the user is logged in, false otherwise.
     * @param state just the auth store state
     */
    isAuthenticated: (state) => {
      return !!state.accessToken;
    },
  },
  actions: {
    /**
     * Support for hot module reloading.
     * @param meta
     */
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useAuth, meta.hot));
      }
    },
    /**
     * Create the websocket client and try to authenticate the
     * websocket connection.
     */
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
    /**
     * After successful authentication, set the http clients
     * of the stores to the authenticated client.
     */
    async setAuthenticatedClients() {
      const stores = [useSteps(), useServices(), useDeployments()];
      const authenticatedClient = getClient();
      for (const store of stores) {
        store.client = authenticatedClient;
      }
    },
    /**
     * Functions that have to be called after successful authentication
     */
    async onLoginSuccess() {
      await this.initWebsocketClient();
      await this.setAuthenticatedClients();
      const serviceStore = useServices();
      serviceStore.fetchServices();
      serviceStore.fetchServiceNames();
    },
    /**
     * Logs in the user with the given credentials. Need to use
     * form encoded body to post to token endpoint. The mande wrapper
     * is not really helpful here, so we set the body manually.
     *
     * Dunno how to get the detail error message from the response on
     * 401, so we just show a generic message.
     */
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
      options.headers["Content-Type"] = "application/x-www-form-urlencoded";
      await client
        .post<{ access_token: string }>("/token")
        .then((response) => {
          this.accessToken = response.access_token;
          if (this.isAuthenticated) {
            this.onLoginSuccess();
          }
        })
        .catch((err) => {
          if (err.response === undefined) {
            this.errorMessage = err.message;
          } else if (err.response.status === 401) {
            this.errorMessage = "Invalid username or password";
          } else {
            this.errorMessage = "Unknown error";
          }
        });
    },
    /**
     * Throw away the current access token.
     */
    logout() {
      this.accessToken = null;
      this.errorMessage = null;
      if (this.router) {
        this.router.push("/login")
      }
    },
  },
});
