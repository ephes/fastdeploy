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

export function createWebsocketClient(): WebsocketClient {
  /**
   * Create a websocket client
   */
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
      console.log(event);
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
      if (this.connection === undefined) {
        // This should never happen. It's just a type guard to make
        // typescript happy.
        return;
      }
      const websocketStore = useWebsocketStore();
      websocketStore.handling = "on close";
      websocketStore.connection = readyState[this.connection.readyState];
      websocketStore.authentication = "not authenticated";
      while (this.retryCount < 3) {
        this.retryCount++;
        await new Promise((resolve) => setTimeout(resolve, 1000));
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
      console.log("Received message from websocket server: ", event.data);
      const message = JSON.parse(event.data) as Message;
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
      // create the websocket connection
      const websocketStore = useWebsocketStore();
      websocketStore.handling = "init connection";
      this.connection = new WebSocket(`${websocketUrl}/${this.uuid}`);
      websocketStore.connection = readyState[this.connection.readyState];
      console.log("connecting to websocket: ", this.connection);

      // register event listeners for the websocket connection
      this.connection.onclose = this.onConnectionClose.bind(
        this,
        accessToken,
        websocketUrl
      );
      this.connection.onopen = this.onConnectionOpen.bind(this, accessToken);
      this.connection.onmessage = this.onMessage.bind(this);
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
