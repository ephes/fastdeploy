import { defineStore, acceptHMRUpdate } from "pinia";
import { Service, Message } from "../typings";
import { useSettings } from "./config";

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
    async onLogin() {
      const settings = useSettings();
      this.client.initWebsocketConnection(settings);

    },
    async login() {
      const { accessToken, errorMessage } = await this.client.login(this.username, this.password);
      this.accessToken = accessToken;
      this.errorMessage = errorMessage;
      if (this.isAuthenticated) {
        this.onLogin();
      }
    },
  },
});
