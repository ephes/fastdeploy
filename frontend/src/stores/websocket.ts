import { defineStore, acceptHMRUpdate } from "pinia";

/**
 *
 * This store holds status information about the websocket connection.
 * Users should be able to see whether the websocket is connected or not.
 */
export const useWebsocketStore = defineStore("websocket", {
  state: () => {
    return {
      /**
       * Information about the websocket connection status
       * (CLOSED, OPEN, CLOSING, CONNECTING).
       */
      connection: "not connected" as string,
      /**
       * Information about the websocket authentication status
       */
      authentication: "not authenticated" as string,
      /**
       * Information about the websocket handling process
       */
      handling: "not handling" as string,
    };
  },
  actions: {
    /**
     * Support for HMR
     * @param {any} meta
     */
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useWebsocketStore, meta.hot));
      }
    },
  },
});
