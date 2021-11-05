import {App, Ref} from 'vue';

interface Step {
  name: string;
  state: string;
  changed: boolean;
  in_progress: boolean;
  done: boolean;
  created: Date;
  started: Date | null;
  finished: Date | null;
}

interface Service {
  id: number;
  name: string;
  origin: string;
  user: string;
}


interface Client {
  uuid: any;
  errorMessage: Ref;
  isAuthenticated: Ref;
  accessToken: string | null;
  connection: any;
  steps: Map<string, Step>;
  services: Map<number, Service>;
  /**
   * Called automatically by `app.use(client)`. Should not be called manually by
   * the user.
   *
   * @internal
   * @param app - Application that uses the client
   */
  install(app: App, options: any): void;
  login(username: string, password: string): void;
  initWebsocketConnection(): void;
  authenticateWebsocketConnection(): void;
  startDeployment(): void;
  fetchServiceToken(accessToken: string): any;
  fetchServices(): Promise<Service[]>;
}
