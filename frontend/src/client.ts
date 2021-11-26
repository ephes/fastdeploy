import { App } from "vue";
import { v4 as uuidv4 } from "uuid";
import { WebsocketClient, Message } from "./typings";

function snakeToCamelStr(str: string): string {
  if (!/[_-]/.test(str)) {
    return str;
  }
  return str
    .toLowerCase()
    .replace(/[-_][a-z0-9]/g, (group) => group.slice(-1).toUpperCase());
};

export function snakeToCamel(obj: any): any {
  const newObj: any = {};
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      const newKey = snakeToCamelStr(key);
      newObj[newKey] = obj[key];
    }
  }
  return newObj;
};

export function createWebsocketClient(): WebsocketClient {
  const client: WebsocketClient = {
    uuid: uuidv4(),
    stores: [],
    install(app: App) {
      app.provide("websocketClient", this);
    },
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
};

// export function createClient(): Client {
//   const client: Client = {
//     mande: mande(""),
//     websocket: createWebsocketConnection(),
//     async addService(service) {
//       const authStore = useAuth();
//       const headers = {
//         authorization: `Bearer ${authStore.accessToken}`,
//         "content-type": "application/json",
//       };
//       const response = await fetch(this.getUrl("services"), {
//         method: "POST",
//         headers: headers,
//         body: JSON.stringify(service),
//       });
//       return await response.json();
//     },
//     async deleteService(serviceId: number) {
//       const authStore = useAuth();
//       const headers = {
//         authorization: `Bearer ${authStore.accessToken}`,
//         "content-type": "application/json",
//       };
//       const response = await fetch(this.getUrl(`services/${serviceId}`), {
//         method: "DELETE",
//         headers: headers,
//       });
//       console.log("delete service: ", await response.json());
//       if (response.ok) {
//         return serviceId;
//       } else {
//         return null;
//       }
//     },
//   };
//   return client;
// }
