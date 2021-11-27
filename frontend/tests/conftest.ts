import "pinia";

declare module "pinia" {
  export interface PiniaCustomProperties {
    client: Client;
  }
}

export class Connection {
  onmessage = (message: any) => {};
  send = (message: MessageEvent) => {
    this.onmessage(message);
  };
}

export function createStubWebsocketConnection() {
  const websocket = createWebsocketConnection();
  // replace actual connection with stub
  websocket.connection = new Connection();
  return websocket;
}

export function createEvent(data: any): MessageEvent {
  return { data: JSON.stringify(data) } as MessageEvent;
}
