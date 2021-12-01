import { v4 as uuidv4 } from "uuid";
import { snakeToCamel } from "./converters";
import { WebsocketClient, Message } from "./typings";

export function createWebsocketClient(): WebsocketClient {
  const client: WebsocketClient = {
    uuid: uuidv4(),
    stores: [],
    registerStore(store: any) {
      this.stores.push(store);
    },
    onConnectionOpen(accessToken: string, event: MessageEvent) {
      console.log(event);
      console.log("Successfully connected to the echo websocket server..");
      console.log("using token: ", accessToken);
      this.authenticateWebsocketConnection(
        this.connection,
        String(accessToken)
      );
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
      this.registerWebsocketConnectionCallbacks(this.connection, accessToken);
    },
    registerWebsocketConnectionCallbacks(connection: any, accessToken: string) {
      connection.onopen = this.onConnectionOpen.bind(this, accessToken);
      connection.onmessage = this.onMessage.bind(this);
    },
    authenticateWebsocketConnection(connection: any, accessToken: string) {
      const credentials = JSON.stringify({ access_token: accessToken });
      connection.send(credentials);
    },
  };
  return client;
}
