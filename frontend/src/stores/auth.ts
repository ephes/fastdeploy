import { computed, markRaw, reactive, toRefs, watch } from "vue";
import { createWebsocketClient } from "../websocket";
import { defineStore, acceptHMRUpdate, getActivePinia } from "pinia";
import { WebsocketClient } from "../typings";

import { getClientWithoutAuth, getClient } from "./httpClient";
import { useSteps } from "./step";
import { useSettings } from "./config";
import { useServices } from "./service";
import { useDeployments } from "./deployment";
import { useWebsocketStore } from "./websocket";

export const useAuth = defineStore("auth", () => {
  const pinia = getActivePinia();
  const settings = useSettings(pinia);
  const createLoginClient = () => {
    const api = settings.api;
    return getClientWithoutAuth(api, () => settings.api === api);
  };
  const initialState = () => {
    return {
      accessToken: null as string | null,
      authenticatedApi: null as string | null,
      username: "" as string,
      password: "" as string,
      errorMessage: null as string | null,
      client: createLoginClient(),
      router: null as any,
      /**
       * Counts login sessions: incremented whenever one ends or a new
       * one begins. Requests remember it (see rememberSession) and drop
       * their response if it changed while they were waiting.
       */
      sessionId: 0 as number,
      loginAttemptId: 0 as number,
      /**
       * The websocket client of the current session, kept to be able
       * to dispose it on logout.
       */
      websocketClient: null as WebsocketClient | null,
    };
  };
  const state = reactive(initialState());
  const isAuthenticated = computed(() => !!state.accessToken);

  // The store's effect scope owns this watcher, including after recreation
  // from retained state. A destination change retires pending logins too.
  watch(
    [() => settings.api, () => settings.websocket],
    () => useAuth(pinia).endSession(),
    { flush: "sync" },
  );

  const actions = {
    $reset(): void {
      const auth = useAuth(pinia);
      auth.$patch(state => {
        auth.endSession();
        state.username = "";
        state.errorMessage = null;
        state.router = null;
      });
    },
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
      if (state.websocketClient) {
        state.websocketClient.dispose();
      }
      const websocketClient = markRaw(createWebsocketClient());
      state.websocketClient = websocketClient;
      if (state.accessToken) {
        websocketClient.initWebsocketConnection(
          settings.websocket,
          state.accessToken
        );
      }

      // register store hooks for websocket events
      const stores = [useSteps(pinia), useServices(pinia), useDeployments(pinia)];
      for (const store of stores) {
        websocketClient.registerStore(store);
      }
    },
    /**
     * After successful authentication, set the http clients
     * of the stores to the authenticated client.
     */
    async setAuthenticatedClients() {
      const stores = [useSteps(pinia), useServices(pinia), useDeployments(pinia)];
      const authenticatedClient = getClient();
      for (const store of stores) {
        store.client = authenticatedClient;
      }
    },
    /**
     * Functions that have to be called after successful authentication
     */
    async onLoginSuccess(): Promise<void> {
      await useAuth(pinia).initWebsocketClient();
      await useAuth(pinia).setAuthenticatedClients();
      const serviceStore = useServices(pinia);
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
      const attemptId = ++state.loginAttemptId;
      const api = settings.api;
      state.errorMessage = null;
      if (!state.username || !state.password) {
        state.errorMessage = "Please enter a username and password";
        return;
      }
      let formData = new FormData();
      formData.append("username", state.username);
      formData.append("password", state.password);
      const body =
        "grant_type=password&" +
        new URLSearchParams(formData as any).toString();
      const client = state.client;
      const options: any = {
        body,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      };
      await client
        .post<{ access_token: string }>("/token", undefined, options)
        .then((response) => {
          if (state.loginAttemptId !== attemptId || settings.api !== api) {
            // a logout or another login happened meanwhile: this
            // response belongs to an attempt that is over
            return;
          }
          // whatever a previous session left behind goes first
          useAuth(pinia).endSession();
          state.authenticatedApi = api;
          state.accessToken = response.access_token;
          if (isAuthenticated.value) {
            useAuth(pinia).onLoginSuccess();
          }
        })
        .catch((err) => {
          if (state.loginAttemptId !== attemptId || settings.api !== api) {
            return;
          }
          if (err.response === undefined) {
            state.errorMessage = err.message;
          } else if (err.response.status === 401) {
            state.errorMessage = "Invalid username or password";
          } else if (err.response.status === 429) {
            state.errorMessage = "Too many failed login attempts, try again later";
          } else {
            state.errorMessage = "Unknown error";
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
    endSession(): void {
      state.loginAttemptId++;
      state.sessionId++;
      state.accessToken = null;
      state.authenticatedApi = null;
      state.password = "";
      if (state.websocketClient) {
        state.websocketClient.dispose();
        state.websocketClient = null;
      }
      state.client = createLoginClient();
      const stores = [useSteps(pinia), useServices(pinia), useDeployments(pinia), useWebsocketStore(pinia)];
      for (const store of stores) {
        store.$reset();
      }
    },
    /**
     * Log out: end the session and go to the login page.
     */
    logout() {
      useAuth(pinia).endSession();
      state.errorMessage = null;
      if (state.router) {
        state.router.push("/login")
      }
    },
  };
  return { ...toRefs(state), isAuthenticated, ...actions };
});
