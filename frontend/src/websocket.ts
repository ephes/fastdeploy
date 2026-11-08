import { v4 as uuidv4 } from "uuid";
import { pythonToJavascript } from "./converters";
import { WebsocketClient, Message, AuthenticationMessage } from "./typings";
import { useWebsocketStore } from "./stores/websocket";
import { useAuth } from "./stores/auth";

const readyState: { [key: number]: string } = {
  0: "CONNECTING",
  1: "OPEN",
  2: "CLOSING",
  3: "CLOSED",
};

function isRecord(value: unknown): value is Record<string, any> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// Validate the wire representation before date conversion or store dispatch.
function validMessage(value: unknown): value is Message {
  if (!isRecord(value)) return false;
  const id = (v: unknown) => typeof v === "number" && Number.isSafeInteger(v) && v > 0;
  const date = (v: unknown) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v) && Number.isFinite(Date.parse(v));
  const optionalDate = (v: unknown) => v === null || date(v);
  if (value.deleted !== undefined && typeof value.deleted !== "boolean") return false;
  switch (value.type) {
    case "authentication":
      return ["success", "failure"].includes(value.status) &&
        (value.detail == null || typeof value.detail === "string");
    case "service":
      return id(value.id) && typeof value.name === "string" && isRecord(value.data);
    case "deployment":
      return id(value.id) && id(value.service_id) && typeof value.origin === "string" &&
        typeof value.user === "string" && date(value.started) && optionalDate(value.finished);
    case "step":
      return id(value.id) && id(value.deployment_id) && typeof value.name === "string" &&
        ["pending", "running", "success", "failure"].includes(value.state) &&
        typeof value.message === "string" && optionalDate(value.started) && optionalDate(value.finished);
    case "user":
      return id(value.id) && typeof value.name === "string";
    case "warning":
      return typeof value.detail === "string";
    default:
      // Existing endpoint's informational control messages have no type.
      return value.type === undefined && typeof value.message === "string";
  }
}

export function createWebsocketClient(): WebsocketClient {
  /**
   * Create a websocket client
   */
  let generation = 0;
  const client: WebsocketClient = {
    /**
     * The websocket client id which is used to identify the websocket client
     * by the server.
     *
     */
    uuid: uuidv4(),
    /**
     * List of all stores which should be notified when messages are received.
     */
    stores: [],
    /**
     * Count the number of connection attempts since last successful connection.
     */
    retryCount: 0,
    /**
     * Set by dispose(). A disposed client never connects, reconnects,
     * authenticates or passes on a message again.
     */
    disposed: false,
    /**
     * End this client for good: called on logout. Detaches the event
     * handlers before closing, so the close does not start the
     * reconnect loop, and a reconnect timer that is already waiting
     * finds the client disposed. The stores are dropped so no late
     * message can reach them.
     */
    dispose() {
      this.disposed = true;
      this.stores = [];
      const connection = this.connection;
      if (connection !== undefined) {
        connection.onclose = null;
        connection.onopen = null;
        connection.onmessage = null;
        try {
          connection.close();
        } catch (err) {
          console.log("closing websocket failed: ", err);
        }
      }
    },
    /**
     * Register a store to be notified when a message is received.
     *
     * @param store
     */
    registerStore(store: any) {
      this.stores.push(store);
    },
    /**
     * Callback for when the websocket is opened. Passes information
     * about connection state to websocketStore and calls a method
     * to authenticate the websocket connection.
     *
     * @param accessToken {string}
     * @param event {Event}
     */
    onConnectionOpen(accessToken: string, event: Event) {
      if (this.disposed) {
        // opened after logout: do not send the old token, just hang up
        const lateConnection = event.target as WebSocket | null;
        if (lateConnection && typeof lateConnection.close === "function") {
          lateConnection.close();
        }
        return;
      }
      console.log("Successfully connected to the echo websocket server..");
      const websocketStore = useWebsocketStore();
      websocketStore.handling = "on open";
      const connection: WebSocket = event.target as WebSocket;
      if (connection !== undefined) {
        websocketStore.connection = readyState[connection.readyState];
        this.authenticateWebsocketConnection(connection, accessToken);
      }
    },
    /**
     * React to the websocket connection being closed. This
     * usually happens when the server is restarted.
     *
     * @param accessToken {string} The access token to use for authentication
     * @param event {CloseEvent} The close event
     */
    async onConnectionClose(
      accessToken: string,
      websocketUrl: string,
      event: CloseEvent
    ) {
      if (this.connection === undefined || this.disposed) {
        // undefined should never happen. It's just a type guard to make
        // typescript happy. Disposed: logged out, do not reconnect.
        return;
      }
      const connection = this.connection;
      const closingGeneration = generation;
      const websocketStore = useWebsocketStore();
      websocketStore.handling = "on close";
      websocketStore.connection = readyState[this.connection.readyState];
      websocketStore.authentication = "not authenticated";
      while (this.retryCount < 3) {
        this.retryCount++;
        await new Promise((resolve) => setTimeout(resolve, 1000));
        if (this.disposed || generation !== closingGeneration || this.connection !== connection) {
          // logged out while waiting: the token of this loop is void
          return;
        }
        console.log(
          "Attempting to reconnect to websocket server: ",
          this.retryCount
        );
        if (this.connection.readyState === WebSocket.CLOSED) {
          // only try to reconnect if the connection is closed
          // skip on OPEN, CONNECTING and CLOSING
          this.initWebsocketConnection(websocketUrl, accessToken);
          // stop retrying after initWebsocketConnection is called
          // because if it fails, it will call onConnectionClose again
          // and we are using a global retryCount
          break;
        } else {
          console.log(
            "Skipping reconnection attempt because of readyState: ",
            readyState[this.connection.readyState]
          );
        }
      }
    },
    /**
     * Pass message to the different stores.
     *
     * @param message {Message} The message to pass to the stores
     */
    notifyStores(message: Message) {
      if (this.disposed) {
        return;
      }
      const newMessage = pythonToJavascript(message);
      for (const store of this.stores) {
        store.onMessage(newMessage);
      }
    },
    /**
     * Handle received authentication message from the server.
     * It's either a success or failure response.
     *
     * @param authenticationMessage: {AuthenticationMessage} The authentication message received from the server
     */
    onAuthenticationMessage(authenticationMessage: AuthenticationMessage) {
      const websocketStore = useWebsocketStore();
      if (authenticationMessage.status === "success") {
        websocketStore.handling = "on authentication message";
        websocketStore.authentication = "authenticated";
        this.retryCount = 0; // reset retry count for next onConnectionClose event
      } else {
        websocketStore.handling = "on authentication message";
        websocketStore.authentication = "authentication failure";
        const auth = useAuth();
        auth.logout();
      }
    },
    /**
     * All messages received from the websocket server are passed to this
     * method and eventually dispatched to the stores.
     *
     * @param event {MessageEvent} The url of the websocket server
     */
    onMessage(event: MessageEvent) {
      if (this.disposed) {
        return;
      }
      let message: any;
      try {
        if (typeof event.data !== "string") throw new Error();
        message = JSON.parse(event.data);
        if (!validMessage(message)) throw new Error();
      } catch {
        // Retire queued callbacks as well as installed handlers. Recovery is an
        // explicit refresh, avoiding a reconnect loop on a broken protocol.
        generation++;
        const connection = this.connection;
        if (connection) {
          connection.onopen = connection.onclose = connection.onmessage = null;
          try { connection.close(); } catch { /* Already unavailable. */ }
        }
        useWebsocketStore().protocolError = "Invalid websocket message; refresh to resynchronize.";
        useWebsocketStore().handling = useWebsocketStore().protocolError;
        useWebsocketStore().connection = "CLOSED";
        useWebsocketStore().authentication = "not authenticated";
        console.warn("Invalid websocket message; refresh to resynchronize.");
        return;
      }
      if (!("type" in message) || message.type === "warning") return;
      useWebsocketStore().receivedMessage();
      if (message.type === "authentication") {
        // special handling for authentication response
        this.onAuthenticationMessage(message as AuthenticationMessage);
      } else {
        this.notifyStores(message);
      }
    },
    /**
     * Initialize the websocket connection. This is called when a websocket
     * connection should be established.
     *
     * @param websocketUrl {string} The url of the websocket server
     * @param accessToken {string} The access token to use for authentication
     */
    initWebsocketConnection(websocketUrl: string, accessToken: string) {
      if (this.disposed) {
        return;
      }
      // create the websocket connection
      const websocketStore = useWebsocketStore();
      websocketStore.protocolError = "";
      websocketStore.handling = "init connection";
      const previous = this.connection;
      if (previous) {
        previous.onclose = previous.onopen = previous.onmessage = null;
        previous.close();
      }
      const currentGeneration = ++generation;
      this.connection = new WebSocket(`${websocketUrl}/${this.uuid}`);
      websocketStore.connection = readyState[this.connection.readyState];
      console.log("connecting to websocket: ", this.connection);

      // register event listeners for the websocket connection
      const isCurrent = () => !this.disposed && generation === currentGeneration;
      this.connection.onclose = (event) => {
        if (isCurrent()) return this.onConnectionClose(accessToken, websocketUrl, event);
      };
      this.connection.onopen = (event) => {
        if (isCurrent()) this.onConnectionOpen(accessToken, event);
      };
      this.connection.onmessage = (event) => {
        if (isCurrent()) this.onMessage(event);
      };
    },
    /**
     * Send access token as message (json string) to the websocket server.
     *
     * @param connection {WebSocket} The websocket connection
     * @param accessToken {string} The access token to use for authentication
     */
    authenticateWebsocketConnection(connection: any, accessToken: string) {
      const credentials = JSON.stringify({ access_token: accessToken });
      connection.send(credentials);
      const websocketStore = useWebsocketStore();
      websocketStore.handling = "send credentials";
      websocketStore.authentication = "authenticating...";
    },
  };
  return client;
}
