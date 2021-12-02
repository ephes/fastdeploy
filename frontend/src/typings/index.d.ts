import { App } from "vue";


type SnakeToCamel = {
  // FIXME this has to be better
  [key: string]: any;
}


type Environment = {
  MODE: string;
  VITE_API_BASE_DEV: string;
  VITE_API_BASE_PROD: string;
  VITE_WEBSOCKET_URL_DEV: string;
  VITE_WEBSOCKET_URL_PROD: string;
}

type Message = {
  type?: "service" | "deployment" | "step";
};

type Service = Message & {
  id?: number;
  name: string;
  data: object;
  deleted?: boolean;
};

type ServiceWithId = Service & {
  id: number;
}

type ServiceById = {
  [id: number]: ServiceWithId;
}

type Deployment = Message & {
  id: number;
  service_id: number;
  origin: string;
  user: string;
  created: string;
  deleted?: boolean;
};

type DeploymentById = {
  [id: number]: Deployment;
}

type Step = Message & {
  id: number;
  name: string;
  state: string | null;
  changed: boolean;
  inProgress: boolean;
  deploymentId: number;
  done: boolean;
  created: string;
  started: string | null;
  finished: string | null;
  deleted?: boolean;
};

type StepById = {
  [id: number]: Step;
}

type WebsocketClient = {
  uuid: any;
  stores: any[];
  connection?: WebSocket;
  initWebsocketConnection(websocketUrl: string, accessToken: string): void;
  authenticateWebsocketConnection(connection: any, accessToken: string): void;
  onMessage(event: any): void;
  onConnectionOpen(accessToken: string, event: MessageEvent): void;
  // onConnectionClose(event: CloseEvent): void;
  registerStore(store: any): void;
  registerWebsocketConnectionCallbacks(connection: WebSocket, accessToken: string): void;
  notifyStores(message: Message): void;
}
