import { markRaw } from "vue";
import { createWebsocketClient } from "../websocket";
import { defineStore, acceptHMRUpdate } from "pinia";
import { WebsocketClient } from "../typings";

import { getClientWithoutAuth, getClient } from "./httpClient";
import { useSteps } from "./step";
import { useSettings } from "./config";
import { useServices } from "./service";
import { useDeployments } from "./deployment";
import { useWebsocketStore } from "./websocket";

export const useAuth = defineStore("auth", {
  state: () => {
    return {
      accessToken: null as string | null,
      username: "" as string,
      password: "" as string,
      errorMessage: null as string | null,
      client: getClientWithoutAuth(),
      router: null as any,
      /**
       * Counts login sessions: incremented whenever one ends or a new
       * one begins. Requests remember it (see rememberSession) and drop
       * their response if it changed while they were waiting.
       */
      sessionId: 0 as number,
      /**
       * The websocket client of the current session, kept to be able
       * to dispose it on logout.
       */
      websocketClient: null as WebsocketClient | null,
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
      if (this.websocketClient) {
        this.websocketClient.dispose();
      }
      const websocketClient = markRaw(createWebsocketClient());
      this.websocketClient = websocketClient;
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
      const sessionId = this.sessionId;
      await client
        .post<{ access_token: string }>("/token")
        .then((response) => {
          if (this.sessionId !== sessionId) {
            // a logout or another login happened meanwhile: this
            // response belongs to an attempt that is over
            return;
          }
          // whatever a previous session left behind goes first
          this.endSession();
          this.accessToken = response.access_token;
          if (this.isAuthenticated) {
            this.onLoginSuccess();
          }
        })
        .catch((err) => {
          if (this.sessionId !== sessionId) {
            return;
          }
          if (err.response === undefined) {
            this.errorMessage = err.message;
          } else if (err.response.status === 401) {
            this.errorMessage = "Invalid username or password";
          } else if (err.response.status === 429) {
            this.errorMessage = "Too many failed login attempts, try again later";
          } else {
            this.errorMessage = "Unknown error";
          }
        })
        .finally(() => {
          // the request body holds the password
          delete options["body"];
        });
    },
    /**
     * End the current login session and everything that could still
     * act or speak for it:
     *
     * - the access token and the password are forgotten,
     * - the websocket client is disposed (no reconnect with the old token),
     * - the stores are reset, which also replaces their http clients
     *   by ones without Authorization header,
     * - requests still in flight will find a different sessionId and
     *   drop their response.
     */
    endSession() {
      this.sessionId++;
      this.accessToken = null;
      this.password = "";
      if (this.websocketClient) {
        this.websocketClient.dispose();
        this.websocketClient = null;
      }
      this.client = getClientWithoutAuth();
      const stores = [useSteps(), useServices(), useDeployments(), useWebsocketStore()];
      for (const store of stores) {
        store.$reset();
      }
    },
    /**
     * Log out: end the session and go to the login page.
     */
    logout() {
      this.endSession();
      this.errorMessage = null;
      if (this.router) {
        this.router.push("/login")
      }
    },
  },
});
