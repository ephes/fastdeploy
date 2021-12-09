import { App } from "vue";

type HasStringKeys = {
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
  type?: "service" | "deployment" | "step" | "authentication";
};

type AuthenticationMessage = Message & {
  type: "authentication";
  status: "success" | "failure";
  detail?: string;
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
  serviceId: number;
  origin: string;
  user: string;
  created: Date;
  finished: Date | null;
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
  created: Date;
  started: Date | null;
  finished: Date | null;
  deleted?: boolean;
};

type StepById = {
  [id: number]: Step;
}

type WebsocketClient = {
  uuid: any;
  stores: any[];
  connection?: WebSocket;
  retryCount: number;
  initWebsocketConnection(websocketUrl: string, accessToken: string): void;
  onAuthenticationMessage(message: AuthenticationMessage): void;
  authenticateWebsocketConnection(connection: WebSocket, accessToken: string): void;
  onMessage(event: any): void;
  onConnectionOpen(accessToken: string, event: Event): void;
  onConnectionClose(accessToken: string, websocketUrl: string, event: CloseEvent): void;
  registerStore(store: any): void;
  notifyStores(message: Message): void;
}
