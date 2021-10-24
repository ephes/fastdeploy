import { App, ref, Ref } from 'vue';
import { v4 as uuidv4 } from 'uuid';

interface Client {
  uuid: any;
  errorMessage: Ref;
  isAuthenticated: Ref;
  accessToken: string | null;
  connection: any;
  messages: Ref;
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
}

export function createClient(): Client {
  const client: Client = {
    uuid: uuidv4(),
    errorMessage: ref(false),
    connection: null,
    accessToken: null,
    isAuthenticated: ref(false),
    install(app: App, options: any) {
      app.provide('client', this);
    },
    messages: ref([]),
    initWebsocketConnection() {
      this.connection = new WebSocket(`ws://localhost:8000/deployments/ws/${this.uuid}`);
      this.connection.onopen = (event: MessageEvent) => {
        console.log(event);
        console.log('Successfully connected to the echo websocket server...');
        this.authenticateWebsocketConnection()
      };
      this.connection.onmessage = (event: MessageEvent) => {
        const message = JSON.parse(event.data);
        console.log('in client.ts: ', message);
        this.messages.value.push(message);
      };
    },
    authenticateWebsocketConnection() {
      const credentials = JSON.stringify({ access_token: this.accessToken })
      this.connection.send(credentials)
    },
    startDeployment() {
      const headers = { authorization: `Bearer ${this.accessToken}` };
      fetch('http://localhost:8000/deployments/deploy', {
        method: 'POST',
        headers: headers,
      })
        .then((response) => response.json())
        .then((data) => console.log('fetch response: ', data));
    },
    async login(username: string, password: string) {
      let formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      const response = await fetch('http://localhost:8000/token', {
        method: 'POST',
        body: formData,
      });
      const result = await response.json();
      if (!response.ok) {
        // error
        console.log("login error: ", result)
        client.isAuthenticated.value = false
        client.errorMessage.value = result.detail
      } else {
        console.log('login success: ', result);
        client.errorMessage.value = false;
        client.isAuthenticated.value = true;
        client.accessToken = result.access_token;
        client.initWebsocketConnection()
        // client.authenticateWebsocketConnection()
      }
    },
  };
  return client;
}
