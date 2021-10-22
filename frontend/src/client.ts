import { App, ref, Ref } from 'vue';

// class Client {
//   name = 'websocket client..';
//   connection: any;
//   messages: any;
//   access_token: string = '';
//   is_authenticated: any;

//   constructor() {
//     this.messages = ref([]);
//     this.is_authenticated = ref(false);
//     this.initWebsocketConnection();
//   }

//   initWebsocketConnection() {
//     //document.cookie = 'auth=' + this.access_token + '; path="/deployments"'
//     this.connection = new WebSocket('ws://localhost:8000/deployments/ws/1');
//     this.connection.onopen = (event: MessageEvent) => {
//       console.log(event);
//       console.log('Successfully connected to the echo websocket server...');
//     };
//     this.connection.onmessage = (event: MessageEvent) => {
//       const message = JSON.parse(event.data);
//       console.log('in client.ts: ', message);
//       this.messages.value.push(message);
//     };
//   }
//   sendMessage() {
//     this.connection.send(
//       JSON.stringify({ message: 'message from client client!' })
//     );
//   }
//   startDeployment() {
//     const headers = { authorization: `Bearer ${this.access_token}` };
//     fetch('http://localhost:8000/deployments/deploy', {
//       method: 'POST',
//       headers: headers,
//     })
//       .then((response) => response.json())
//       .then((data) => console.log('fetch response: ', data));
//   }
//   login = async (username: string, password: string) => {
//     let formData = new FormData();
//     formData.append('username', username);
//     formData.append('password', password);
//     const response = await fetch('http://localhost:8000/token', {
//       method: 'POST',
//       body: formData,
//     });
//     const result = await response.json();
//     console.log('username, password: ', username, password);
//     console.log('returned data: ', result);
//     this.access_token = result.access_token;
//     this.is_authenticated.value = true;
//   };
// }

interface Client {
  isAuthenticated: Ref;
  accessToken: string | null;
  connection: any;
  messages: Ref;
  // messages: Message[];
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
  startDeployment(): void;
}

let isAuthenticated = false;

export function createClient(): Client {
  const client: Client = {
    connection: null,
    accessToken: null,
    isAuthenticated: ref(false),
    install(app: App, options: any) {
      app.provide('client', this);
    },
    messages: ref([]),
    // login: async (username: string, password: string) => {
    initWebsocketConnection() {
      //document.cookie = 'auth=' + this.access_token + '; path="/deployments"'
      this.connection = new WebSocket('ws://localhost:8000/deployments/ws/1');
      this.connection.onopen = (event: MessageEvent) => {
        console.log(event);
        console.log('Successfully connected to the echo websocket server...');
      };
      this.connection.onmessage = (event: MessageEvent) => {
        const message = JSON.parse(event.data);
        console.log('in client.ts: ', message);
        this.messages.value.push(message);
      };
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
      } else {
        console.log('login success: ', result);
        client.isAuthenticated.value = true;
        client.accessToken = result.access_token;
        client.initWebsocketConnection()
      }
    },
  };
  return client;
}
