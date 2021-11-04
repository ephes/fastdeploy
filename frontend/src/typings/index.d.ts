import {App, Ref} from 'vue';

interface Step {
  name: string;
  state: string;
  changed: boolean;
  in_progress: boolean;
  done: boolean;
  created: string;
  started: string | null;
  finished: string | null;
}


interface Client {
  uuid: any;
  errorMessage: Ref;
  isAuthenticated: Ref;
  accessToken: string | null;
  connection: any;
  steps: Map<string, Step>;
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
}
