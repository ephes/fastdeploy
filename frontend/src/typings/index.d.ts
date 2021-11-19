import { App, Ref } from "vue";

interface Environment {
  MODE: string;
  VITE_API_BASE_DEV: string;
  VITE_API_BASE_PROD: string;
  VITE_WEBSOCKET_URL_DEV: string;
  VITE_WEBSOCKET_URL_PROD: string;
}

interface Message {
  type: string;
}

interface Step {
  id: number;
  name: string;
  state: string;
  changed: boolean;
  in_progress: boolean;
  deployment_id: number;
  done: boolean;
  created: Date;
  started: Date | null;
  finished: Date | null;
  deleted: boolean;
}

interface Service {
  id: number | undefined;
  name: string;
  collect: string;
  deploy: string;
  deleted: boolean;
}

interface Deployment {
  id: number;
  service_id: number;
  origin: string;
  user: string;
  created: Date;
  deleted: boolean;
}

interface Client {
  uuid: any;
  connection: any;
  steps: Map<number, Step>;
  deployments: Map<number, Deployment>;
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
  fetchServices(): Promise<Service[]>;
  addService(service: Service): Promise<any>;
  deleteService(serviceId: number): Promise<number | null>;
  fetchDeployments(): Promise<Deployment[]>;
  fetchStepsFromDeployment(deploymentId: number): Promise<Step[]>;
  registerStore(store: any): void;
  onMessage(event: any): void;
  onConnectionOpen(event: MessageEvent): void;
  registerWebsocketConnectionCallbacks(connection: any): void;
  notifyStores(message: Message): void;
}
