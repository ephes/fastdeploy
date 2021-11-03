import { App, ref, Ref, reactive } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import { Step, Client } from "./typings";


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
    steps: reactive({}),
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
        if (message.type === "step") {
          const step = message
          this.steps[step.name] = step
        }
      };
    },
    authenticateWebsocketConnection() {
      const credentials = JSON.stringify({ access_token: this.accessToken })
      this.connection.send(credentials)
    },
    async fetchServiceToken(accessToken: string) {
      const headers = { authorization: `Bearer ${accessToken}`, 'content-type': 'application/json' }
      const body = JSON.stringify({
        service: "fastdeploy",
        origin: "GitHub",
      })
      console.log("service token body: ", body)
      const response = await fetch('http://localhost:8000/service-token', {
        method: 'POST',
        headers: headers,
        body: body,
      });
      const json = await response.json();
      console.log("service token response: ", json)
      return json.service_token;
    },
    async startDeployment() {
      if (!this.accessToken) {
        return false
      }
      const serviceToken = await this.fetchServiceToken(this.accessToken);
      const headers = { authorization: `Bearer ${serviceToken}`, 'content-type': 'application/json'};
      fetch('http://localhost:8000/deployments/', {
        method: 'POST',
        headers: headers,
      })
        .then((response) => response.json())
        .then((data) => console.log('fetch response: ', data));
    },
    async login(username: string, password: string) {
      let formData = new FormData();
      console.log("login! ", username, password);
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
      }
    },
  };
  return client;
}
