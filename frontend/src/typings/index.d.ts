import { App, Ref } from "vue";

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

interface Client {
  uuid: any;
  connection: any;
  steps: Map<number, Step>;
  stores: any[];
  /**
   * Called automatically by `app.use(client)`. Should not be called manually by
   * the user.
   *
   * @internal
   * @param app - Application that uses the client
   */
  install(app: App, options: any): void;
  getUrl(path: string): string;
  login(username: string, password: string): Promise<any>;
  initWebsocketConnection(settings: any): void;
  authenticateWebsocketConnection(connection: any, accessToken: string): void;
  startDeployment(serviceName: string): Promise<Deployment>;
  fetchServiceToken(
    serviceName: string,
    accessToken: string,
    origin: string
  ): Promise<string>;
  fetchServices(): Promise<ServiceWithId[]>;
  addService(service: Service): Promise<ServiceWithId>;
  deleteService(serviceId: number): Promise<number | null>;
  fetchDeployments(): Promise<Deployment[]>;
  fetchStepsFromDeployment(deploymentId: number): Promise<Step[]>;
  registerStore(store: any): void;
  onMessage(event: any): void;
  onConnectionOpen(event: MessageEvent): void;
  registerWebsocketConnectionCallbacks(connection: any): void;
  notifyStores(message: Message): void;
}
