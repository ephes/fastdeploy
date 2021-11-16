import { defineStore } from "pinia";

export const useSettings = defineStore("settings", {
  state: () => {
    return {
      mode: String(import.meta.env.MODE),
      // backend api url
      productionApiVite: String(import.meta.env.VITE_API_BASE_PROD),
      developmentApiVite: String(import.meta.env.VITE_API_BASE_DEV),
      developmentApi: "http://localhost:8000",
      // websocket url
      productionWebsocketVite: String(import.meta.env.VITE_WEBSOCKET_URL_PROD),
      developmentWebsocketVite: String(import.meta.env.VITE_WEBSOCKET_URL_DEV),
      developmentWebsocket: "ws://localhost:8000/deployments/ws",
    };
  },
  getters: {
    api: (state) => {
      if (state.mode == 'production' && state.productionApiVite) {
        return state.productionApiVite
      } else if (state.mode == 'development', state.developmentApi) {
        return state.developmentApi
      } else {
        return state.developmentApi
      }
    },
    websocket: (state) => {
      if (state.mode == 'production' && state.productionWebsocketVite) {
        return state.productionWebsocketVite
      } else if (state.mode == 'development' && state.developmentWebsocketVite) {
        return state.developmentWebsocketVite
      } else {
        return state.developmentWebsocket
      }
    }
  }
});
