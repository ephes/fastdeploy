import { inject } from 'vue'
import { defineStore, acceptHMRUpdate } from "pinia";
import { useSettings } from "./config";
import { useServices } from "./service";

export const useAuth = defineStore("auth", {
  state: () => {
    return {
      accessToken: null as string | null,
      username: "" as string,
      password: "" as string,
      errorMessage: null as string | null,
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
    async onLoginSuccess() {
      const settings = useSettings();
      const websocketClient = inject("websocketClient");
      // this.websocketClient.initWebsocketConnection(settings);
      console.log("websocket client? ", websocketClient);
      websocketClient.initWebsocketConnection(settings);
      const serviceStore = useServices();
      serviceStore.fetchServices();

    },
    async login() {
      if (!this.username || !this.password) {
        this.errorMessage = "Please enter a username and password";
        return;
      }
      const settings = useSettings();
      let formData = new FormData();
      formData.append("username", this.username);
      formData.append("password", this.password);
      const response = await fetch( new URL(settings.api) + "token", {
        method: "POST",
        body: formData,
      });
      const result = await response.json();
      if (!response.ok) {
        // error
        console.log("login error: ", result);
        this.accessToken = null;
        this.errorMessage = result.detail;
      } else {
        console.log("login success: ", result);
        this.accessToken = result.access_token;
        this.errorMessage = null;
      }
      if (this.isAuthenticated) {
        this.onLoginSuccess();
      }
    },
  },
});
