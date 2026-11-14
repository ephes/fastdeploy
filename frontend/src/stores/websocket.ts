import { defineStore, acceptHMRUpdate } from "pinia";

function initialState() {
  return {
      /**
       * Information about the websocket connection status
       * (CLOSED, OPEN, CLOSING, CONNECTING).
       */
      connection: "not connected" as string,
      protocolError: "",
      /**
       * Information about the websocket authentication status
       */
      authentication: "not authenticated" as string,
      /**
       * Information about the websocket handling process
       */
      handling: "not handling" as string,
      /**
       * Timestamp of the last message received (initialize with 5 minutes past)
       * in milliseconds.
       *
       */
      messageActive: false,
      lastMessageReceived: Date.now() - 5 * 60 * 1000
  };
}

const activityTimers = new WeakMap<object, ReturnType<typeof setTimeout>>();

/**
 *
 * This store holds status information about the websocket connection.
 * Users should be able to see whether the websocket is connected or not.
 */
export const useWebsocketStore = defineStore("websocket", {
  state: initialState,
  getters: {
    /**
     * Returns whether the websocket is "online"
     * Online means that the websocket is connected and authenticated.
     *
     * @returns {boolean}
     */
    isOnline: (state): boolean => {
      console.log("is online? ", state.connection, state.authentication);
      return state.connection === "OPEN" && state.authentication === "authenticated";
    },
    /**
     * Returns whether the websocket has received a message recently.
     *
     * @returns {boolean}
     */
     recentlyReceivedMessage: (state): boolean => {
       return state.messageActive;
     }
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
    /**
     * Received a message from the websocket.
     */
    receivedMessage() {
      clearTimeout(activityTimers.get(this));
      this.lastMessageReceived = Date.now();
      this.messageActive = true;
      activityTimers.set(this, setTimeout(() => {
        activityTimers.delete(this);
        this.messageActive = false;
      }, 1000));
    },
    $reset() {
      clearTimeout(activityTimers.get(this));
      activityTimers.delete(this);
      this.$patch(initialState());
    }
  },
});
