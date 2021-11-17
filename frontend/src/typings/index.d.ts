import { App, Ref } from 'vue';

interface Environment {
  MODE: string;
  VITE_API_BASE_DEV: string;
  VITE_API_BASE_PROD: string;
  VITE_WEBSOCKET_URL_DEV: string;
  VITE_WEBSOCKET_URL_PROD: string;
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
  apiBase: string;
  errorMessage: Ref;
  isAuthenticated: Ref;
  accessToken: string | null;
  connection: any;
  steps: Map<number, Step>;
  services: Map<number | undefined, Service>;
  deployments: Map<number, Deployment>;
  /**
   * Called automatically by `app.use(client)`. Should not be called manually by
   * the user.
   *
   * @internal
   * @param app - Application that uses the client
   */
  install(app: App, options: any): void;
  getUrl(path: string): string;
  login(username: string, password: string): void;
  initWebsocketConnection(): void;
  authenticateWebsocketConnection(): void;
  startDeployment(serviceName: string): Promise<Deployment>;
  fetchServiceToken(serviceName: string, accessToken: string, origin: string): Promise<string>;
  fetchServices(): Promise<Service[]>;
  addService(service: Service): Promise<Service>;
  deleteService(serviceId: number): Promise<void>;
  fetchDeployments(): Promise<Deployment[]>;
  fetchStepsFromDeployment(deploymentId: number): Promise<Step[]>;
}
