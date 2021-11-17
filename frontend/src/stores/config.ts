import { defineStore, acceptHMRUpdate } from "pinia";

export const useSettings = defineStore("settings", {
  state: () => {
    return {
      // env: {
      //   MODE: "foobar",
      // },
      // mode: String(import.meta.env.MODE),
      // backend api url
      // productionApiVite: String(import.meta.env.VITE_API_BASE_PROD),
      // developmentApiVite: String(import.meta.env.VITE_API_BASE_DEV),
      developmentApi: "http://localhost:8000",
      // websocket url
      // productionWebsocketVite: String(import.meta.env.VITE_WEBSOCKET_URL_PROD),
      // developmentWebsocketVite: String(import.meta.env.VITE_WEBSOCKET_URL_DEV),
      developmentWebsocket: "ws://localhost:8000/deployments/ws",
    };
  },
  getters: {
    api: (state) => {
      return state.developmentApi;
      // if (state.mode == "production" && state.productionApiVite) {
      //   return state.productionApiVite;
      // } else if ((state.mode == "development", state.developmentApi)) {
      //   return state.developmentApi;
      // } else {
      //   return state.developmentApi;
      // }
    },
    websocket: (state) => {
      return state.developmentWebsocket;
      // if (state.mode == "production" && state.productionWebsocketVite) {
      //   return state.productionWebsocketVite;
      // } else if (
      //   state.mode == "development" &&
      //   state.developmentWebsocketVite
      // ) {
      //   return state.developmentWebsocketVite;
      // } else {
      //   return state.developmentWebsocket;
      // }
    },
  },
});

// if (import.meta.hot) {
//   import.meta.hot.accept(acceptHMRUpdate(useSettings, import.meta.hot));
// }
