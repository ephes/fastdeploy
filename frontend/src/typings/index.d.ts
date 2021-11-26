import { App, Ref } from "vue";
import { MandeInstance } from "mande";

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
  collect: string;
  deploy: string;
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
  install(app: App, options: any): void;  // vue plugin
  initWebsocketConnection(settings: any): void;
  authenticateWebsocketConnection(connection: any, accessToken: string): void;
  onMessage(event: any): void;
  onConnectionOpen(event: MessageEvent): void;
  registerStore(store: any): void;
  registerWebsocketConnectionCallbacks(connection: any): void;
  notifyStores(message: Message): void;
}

// interface Client {
//   websocket: WebsocketClient;
//   mande: MandeInstance;
//   setBackendUrl(apiBase: string): void;
//   setAccessToken(accessToken: string): void;
//   getUrl(path: string): string;
//   login(username: string, password: string): Promise<any>;
//   startDeployment(serviceName: string): Promise<Deployment>;
//   fetchServiceToken(
//     serviceName: string,
//     accessToken: string,
//     origin: string
//   ): Promise<string>;
//   fetchServices(): Promise<ServiceWithId[]>;
//   addService(service: Service): Promise<ServiceWithId>;
//   deleteService(serviceId: number): Promise<number | null>;
//   fetchDeployments(): Promise<Deployment[]>;
//   fetchStepsFromDeployment(deploymentId: number): Promise<Step[]>;
// }
