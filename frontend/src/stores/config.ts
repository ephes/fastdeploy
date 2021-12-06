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
    /**
     * Uses the MODE from environment to determine which API base to use.
     * If MODE is not set, returns the default API base.
     *
     * @param state
     * @returns baseApiUrl {string} for the current environment
     */
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
    /**
     * Uses the MODE from environment to determine which websocket url to use.
     *
     * @param state
     * @returns websocketUrl {string} for the current environment
     */
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
