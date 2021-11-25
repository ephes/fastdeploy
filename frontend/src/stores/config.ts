import { defineStore, acceptHMRUpdate } from "pinia";
import { Environment } from "../typings";

export const API_BASE_DEFAULT = "http://localhost:8000";
export const WEBSOCKET_URL_DEFAULT = "ws://localhost:8000/deployments/ws";

export const ENV_DEFAULT: Environment = {
  MODE: "",
  VITE_API_BASE_PROD: "",
  VITE_API_BASE_DEV: "",
  VITE_WEBSOCKET_URL_DEV: "",
  VITE_WEBSOCKET_URL_PROD: "",
};

export const useSettings = defineStore("settings", {
  state: () => {
    return {
      env: { ...ENV_DEFAULT },
      developmentApi: API_BASE_DEFAULT,
      developmentWebsocket: WEBSOCKET_URL_DEFAULT,
    };
  },
  getters: {
    api: (state) => {
      if (state.env.MODE == "production" && state.env.VITE_API_BASE_PROD) {
        return state.env.VITE_API_BASE_PROD;
      } else if (
        state.env.MODE == "development" &&
        state.env.VITE_API_BASE_DEV
      ) {
        return state.env.VITE_API_BASE_DEV;
      } else {
        return state.developmentApi;
      }
    },
    websocket: (state) => {
      if (state.env.MODE == "production" && state.env.VITE_WEBSOCKET_URL_PROD) {
        return state.env.VITE_WEBSOCKET_URL_PROD;
      } else if (
        state.env.MODE == "development" &&
        state.env.VITE_WEBSOCKET_URL_DEV
      ) {
        return state.env.VITE_WEBSOCKET_URL_DEV;
      } else {
        return state.developmentWebsocket;
      }
    },
  },
  actions: {
    useHMRUpdate: (meta: any) => {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useSettings, meta.hot));
      }
    },
    setClientBaseUrl() {
      this.client.setBackendUrl(this.api);
    },
  },
});
