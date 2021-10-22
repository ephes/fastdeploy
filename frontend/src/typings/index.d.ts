import { App } from 'vue';

interface Message {
  name: string;
  state: string;
  changed: boolean;
}

interface Client {
  isAuthenticated: any;
  messages: Message[];
  /**
   * Called automatically by `app.use(client)`. Should not be called manually by
   * the user.
   *
   * @internal
   * @param app - Application that uses the client
   */
  install(app: App, options: any): void;
}
