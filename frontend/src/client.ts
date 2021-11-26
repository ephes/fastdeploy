import { App } from "vue";
import { mande, defaults as mandeDefaults } from 'mande'
import { v4 as uuidv4 } from "uuid";
import { WebsocketClient, Deployment, Message } from "./typings";
import { useSettings } from "./stores/config";
import { useAuth } from "./stores/auth";

function snakeToCamelStr(str: string): string {
  if (!/[_-]/.test(str)) {
    return str;
  }
  return str
    .toLowerCase()
    .replace(/[-_][a-z0-9]/g, (group) => group.slice(-1).toUpperCase());
};

export function snakeToCamel(obj: any): any {
  const newObj: any = {};
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      const newKey = snakeToCamelStr(key);
      newObj[newKey] = obj[key];
    }
  }
  return newObj;
};

export function createWebsocketClient(): WebsocketClient {
  const client: WebsocketClient = {
    uuid: uuidv4(),
    stores: [],
    install(app: App) {
      app.provide("websocketClient", this);
    },
    registerStore(store: any) {
      this.stores.push(store);
    },
    onConnectionOpen(event: MessageEvent) {
      console.log(event);
      console.log("Successfully connected to the echo websocket server...");
      const authStore = useAuth();
      this.authenticateWebsocketConnection(
        this.connection,
        String(authStore.accessToken)
      );
    },
    notifyStores(message: Message) {
      const newMessage = snakeToCamel(message);
      for (const store of this.stores) {
        store.onMessage(newMessage);
      }
    },
    onMessage(event: any) {
      const message = JSON.parse(event.data) as Message;
      this.notifyStores(message);
    },
    initWebsocketConnection(settings: any) {
      let websocketUrl = settings.websocket;
      this.connection = new WebSocket(`${websocketUrl}/${this.uuid}`);
      this.registerWebsocketConnectionCallbacks(this.connection);
    },
    registerWebsocketConnectionCallbacks(connection: any) {
      connection.onopen = this.onConnectionOpen.bind(this);
      connection.onmessage = this.onMessage.bind(this);
    },
    authenticateWebsocketConnection(connection: any, accessToken: string) {
      const credentials = JSON.stringify({ access_token: accessToken });
      connection.send(credentials);
    },
  };
  return client;
};

// export function createClient(): Client {
//   const client: Client = {
//     mande: mande(""),
//     websocket: createWebsocketConnection(),
//     install(app: App) {
//       app.provide("client", this);
//     },
//     setBackendUrl(apiBase: string) {
//       console.log("set api backend: ", apiBase);
//       this.mande = mande(apiBase);
//       console.log("set mande: ", this.mande);
//     },
//     setAccessToken(accessToken: string) {
//       //mandeDefaults.headers.Authorization = `Bearer ${accessToken}`;
//       //this.mande.options.headers = mandeDefaults.headers;
//       this.mande.options.headers.Authorization = `Bearer ${accessToken}`;
//     },
//     getUrl(path: string): string {
//       const settings = useSettings();
//       console.log("base api: ", settings.api);
//       return new URL(settings.api) + path;
//     },
//     async fetchServiceToken(
//       serviceName: string,
//       accessToken: string,
//       origin: string
//     ) {
//       const headers = {
//         authorization: `Bearer ${accessToken}`,
//         "content-type": "application/json",
//       };
//       const body = JSON.stringify({
//         service: serviceName,
//         origin,
//       });
//       console.log("service token body: ", body);
//       const response = await fetch(this.getUrl("service-token"), {
//         method: "POST",
//         headers: headers,
//         body: body,
//       });
//       const json = await response.json();
//       console.log("service token response: ", json);
//       return String(json.service_token);
//     },
//     async startDeployment(serviceName: string) {
//       const authStore = useAuth();
//       if (!authStore.accessToken) {
//         throw new Error("No access token");
//       }
//       const serviceToken = await this.fetchServiceToken(
//         serviceName,
//         authStore.accessToken,
//         "frontend"
//       );
//       const headers = {
//         authorization: `Bearer ${serviceToken}`,
//         "content-type": "application/json",
//       };
//       const response = await fetch(this.getUrl("deployments"), {
//         method: "POST",
//         headers: headers,
//       });
//       const deployment: Deployment = await response.json();
//       console.log("start deployment response: ", deployment);
//       return deployment;
//     },
//     async login(username: string, password: string) {
//       let formData = new FormData();
//       formData.append("username", username);
//       formData.append("password", password);
//       const response = await fetch(this.getUrl("token"), {
//         method: "POST",
//         body: formData,
//       });
//       const result = await response.json();
//       if (!response.ok) {
//         // error
//         console.log("login error: ", result);
//         return { accessToken: null, errorMessage: result.detail };
//       } else {
//         console.log("login success: ", result);
//         return { accessToken: result.access_token, errorMessage: null };
//       }
//     },
//     async fetchServices() {
//       const authStore = useAuth();
//       const headers = {
//         authorization: `Bearer ${authStore.accessToken}`,
//         "content-type": "application/json",
//       };
//       const response = await fetch(this.getUrl("services"), {
//         headers: headers,
//       });
//       const services = await response.json();
//       console.log("fetchServices: ", services);
//       return services;
//     },
//     async addService(service) {
//       const authStore = useAuth();
//       const headers = {
//         authorization: `Bearer ${authStore.accessToken}`,
//         "content-type": "application/json",
//       };
//       const response = await fetch(this.getUrl("services"), {
//         method: "POST",
//         headers: headers,
//         body: JSON.stringify(service),
//       });
//       return await response.json();
//     },
//     async deleteService(serviceId: number) {
//       const authStore = useAuth();
//       const headers = {
//         authorization: `Bearer ${authStore.accessToken}`,
//         "content-type": "application/json",
//       };
//       const response = await fetch(this.getUrl(`services/${serviceId}`), {
//         method: "DELETE",
//         headers: headers,
//       });
//       console.log("delete service: ", await response.json());
//       if (response.ok) {
//         return serviceId;
//       } else {
//         return null;
//       }
//     },
//     async fetchDeployments() {
//       // const authStore = useAuth();
//       // const headers = {
//       //   authorization: `Bearer ${authStore.accessToken}`,
//       //   "content-type": "application/json",
//       // };
//       // const response = await fetch(this.getUrl("deployments"), {
//       //   headers: headers,
//       // });
//       // const deployments: Deployment[] = await response.json();
//       // console.log("fetchDeployments: ", deployments);
//       // return deployments;
//       const authStore = useAuth();
//       const settings = useSettings();
//       const foo = mande(settings.api);
//       foo.options.headers.Authorization = `Bearer ${authStore.accessToken}`;
//       console.log("mande options: ", foo.options);
//       const deployments: Deployment[] = await foo.get("deployments");
//       console.log("fetchDeployments: ", deployments);
//       return deployments;
//     },
//     async fetchStepsFromDeployment(deploymentId: number) {
//       const authStore = useAuth();
//       const headers = {
//         authorization: `Bearer ${authStore.accessToken}`,
//         "content-type": "application/json",
//       };
//       console.log("fetchStepsFromDeployment: ", deploymentId);
//       const params = {
//         deployment_id: deploymentId.toString(),
//       };
//       const response = await fetch(
//         this.getUrl("steps/?" + new URLSearchParams(params)),
//         {
//           headers: headers,
//         }
//       );
//       const steps = (await response.json() as Object[]).map(step => snakeToCamel(step));
//       console.log("fetchSteps by deployment id: ", steps);
//       return steps;
//     },
//   };
//   return client;
// }
