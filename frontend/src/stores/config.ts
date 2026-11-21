import { defineStore, acceptHMRUpdate } from "pinia";
import { Environment } from "../typings";

export const API_BASE_DEFAULT = "http://localhost:8000";
export const WEBSOCKET_URL_DEFAULT = "ws://localhost:8000/deployments/ws";

export const ENV_DEFAULT: Environment = {
  MODE: "",
  PROD: false,
  VITE_API_BASE_PROD: "",
  VITE_API_BASE_DEV: "",
  VITE_WEBSOCKET_URL_DEV: "",
  VITE_WEBSOCKET_URL_PROD: "",
};

/**
 * Config store holding values defined by environment variables
 * or .env.development.ts/.env.production.ts files.
 */
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
      const endpoint = state.env.PROD ? state.env.VITE_API_BASE_PROD : state.env.VITE_API_BASE_DEV;
      return endpoint || state.developmentApi;
    },
    websocket: (state) => {
      const endpoint = state.env.PROD ? state.env.VITE_WEBSOCKET_URL_PROD : state.env.VITE_WEBSOCKET_URL_DEV;
      return endpoint || state.developmentWebsocket;
    },
  },
  actions: {
    /**
     * Support for hot module reloading.
     * @param meta
     */
    useHMRUpdate: (meta: any) => {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useSettings, meta.hot));
      }
    },
  },
});
