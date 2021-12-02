import { v4 as uuidv4 } from "uuid";
import { snakeToCamel } from "./converters";
import { WebsocketClient, Message } from "./typings";

// import { useAuth } from "./stores/auth";

export function createWebsocketClient(): WebsocketClient {
  /*
    * Create a websocket client

  */
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
    // onConnectionClose(event: CloseEvent) {
    //   console.log("Connection closed: ", event);
    //   // FIXME - dont reconnect if already connected
    //   // retry connection for n times
    //   let doBreak = false;
    //   const authStore = useAuth();
    //   for (const attempt of [1, 2, 3]) {
    //     const sleep = new Promise((resolve) => setTimeout(resolve, 1000));
    //     sleep.then(() => {
    //       if (authStore.initWebsocketClient()) {
    //         console.log("reconnected");
    //         doBreak = true;
    //       }
    //     });
    //     if (doBreak) {
    //       break;
    //     }
    //   }
    // },
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
      if (this.connection) {
        if (this.connection.readyState === WebSocket.OPEN) {
          console.log("Websocket connection already open");
        }
      }
      this.connection = new WebSocket(`${websocketUrl}/${this.uuid}`);
      this.registerWebsocketConnectionCallbacks(this.connection, accessToken);
    },
    registerWebsocketConnectionCallbacks(connection: any, accessToken: string) {
      connection.onopen = this.onConnectionOpen.bind(this, accessToken);
      // connection.onclose = this.onConnectionClose.bind(this); // FIXME
      connection.onmessage = this.onMessage.bind(this);
    },
    authenticateWebsocketConnection(connection: any, accessToken: string) {
      const credentials = JSON.stringify({ access_token: accessToken });
      connection.send(credentials);
    },
  };
  return client;
}
