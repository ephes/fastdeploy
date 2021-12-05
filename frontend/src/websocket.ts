import { v4 as uuidv4 } from "uuid";
import { snakeToCamel } from "./converters";
import { WebsocketClient, Message } from "./typings";

export function createWebsocketClient(): WebsocketClient {
  /**
   * Create a websocket client
   */
  const client: WebsocketClient = {
    uuid: uuidv4(),
    stores: [],
    registerStore(store: any) {
      this.stores.push(store);
    },
    onConnectionOpen(accessToken: string, event: Event) {
      console.log(event);
      console.log("Successfully connected to the echo websocket server..");
      this.authenticateWebsocketConnection(this.connection, accessToken);
    },
    /**
     * React to the websocket connection being closed. This
     * usually happens when the server is restarted.
     *
     * @param accessToken {string} The access token to use for authentication
     * @param event {CloseEvent} The close event
     */
    onConnectionClose(
      accessToken: string,
      websocketUrl: string,
      event: CloseEvent
    ) {
      console.log("Connection closed: ", event);
      console.log("access token: ", accessToken);
      console.log("websocket url: ", websocketUrl);
      for (const attempt of [1, 2, 3]) {
        const sleep = new Promise((resolve) => setTimeout(resolve, 1000));
        sleep.then(() => {
          console.log("Attempting to reconnect to websocket server..");
          if (this.connection !== undefined) {
            if (this.connection.readyState === WebSocket.CLOSED) {
              // only try to reconnect if the connection is closed
              // skip on OPEN, CONNECTING and CLOSING
              this.initWebsocketConnection(websocketUrl, accessToken);
            } else {
              console.log("Skipping reconnection attempt..");
            }
          }
        });
      }
    },
    notifyStores(message: Message) {
      const newMessage = snakeToCamel(message);
      for (const store of this.stores) {
        store.onMessage(newMessage);
      }
    },
    onMessage(event: any) {
      const message = JSON.parse(event.data) as Message;
      this.notifyStores(message);
    },
    initWebsocketConnection(websocketUrl: string, accessToken: string) {
      this.connection = new WebSocket(`${websocketUrl}/${this.uuid}`);
      console.log("connecting to websocket: ", this.connection);
      this.connection.onclose = this.onConnectionClose.bind(
        this,
        accessToken,
        websocketUrl
      );
      this.connection.onopen = this.onConnectionOpen.bind(this, accessToken);
      this.connection.onmessage = this.onMessage.bind(this);
    },
    authenticateWebsocketConnection(connection: any, accessToken: string) {
      const credentials = JSON.stringify({ access_token: accessToken });
      connection.send(credentials);
    },
  };
  return client;
}
