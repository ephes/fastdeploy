import { App, ref, Ref, reactive } from "vue";
import { v4 as uuidv4 } from "uuid";
import { Step, Client, Service, Deployment, Message } from "./typings";
import { useSettings } from "./stores/config";
import { useAuth } from "./stores/auth";

function toUtcDate(date: Date): Date {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000);
}

function createStep(message: any): Step {
  const step: Step = {
    id: message.id,
    name: message.name,
    state: message.state,
    changed: message.changed,
    in_progress: message.in_progress,
    deployment_id: message.deployment_id,
    done: message.done,
    created: toUtcDate(new Date(message.created)),
    started: message.started ? toUtcDate(new Date(message.started)) : null,
    finished: message.finished ? toUtcDate(new Date(message.finished)) : null,
    deleted: message.deleted,
  };
  return step;
}

function createDeployment(message: any): Deployment {
  const deployment: Deployment = {
    id: message.id,
    service_id: message.service_id,
    origin: message.origin,
    user: message.user,
    created: toUtcDate(new Date(message.created)),
    deleted: message.deleted,
  };
  return deployment;
}

export function createClient(): Client {
  const client: Client = {
    uuid: uuidv4(),
    connection: null,
    stores: [],
    steps: reactive(new Map<number, Step>()),
    deployments: reactive(new Map<number, Deployment>()),
    install(app: App, options: any) {
      app.provide("client", this);
    },
    registerStore(store: any) {
      this.stores.push(store);
    },
    getUrl(path: string): string {
      const settings = useSettings();
      console.log("base api: ", settings.api);
      return new URL(settings.api) + path;
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
      for (const store of this.stores) {
        store.onMessage(message);
      }
    },
    onMessage(event: any) {
      console.log("onMessage: ", event);
      const message = JSON.parse(event.data) as Message;
      this.notifyStores(message);
      console.log("in client.ts: ", message);
      if (message.type === "step") {
        const step = createStep(message) as Step;
        console.log("step: ", step);
        if (step.deleted) {
          this.steps.delete(step.id);
        } else {
          this.steps.set(step.id, step);
        }
      } else if (message.type === "service") {
        // const service = createService(message) as Service;
        // console.log("service: ", service);
        // if (service.deleted) {
        //   this.services.delete(service.id);
        // } else {
        //   this.services.set(service.id, service);
        // }
      } else if (message.type === "deployment") {
        const deployment = createDeployment(message) as Deployment;
        console.log("deployment: ", deployment);
        if (deployment.deleted) {
          this.deployments.delete(deployment.id);
        } else {
          this.deployments.set(deployment.id, deployment);
        }
      }
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
    async fetchServiceToken(
      serviceName: string,
      accessToken: string,
      origin: string
    ) {
      const headers = {
        authorization: `Bearer ${accessToken}`,
        "content-type": "application/json",
      };
      const body = JSON.stringify({
        service: serviceName,
        origin,
      });
      console.log("service token body: ", body);
      const response = await fetch(this.getUrl("service-token"), {
        method: "POST",
        headers: headers,
        body: body,
      });
      const json = await response.json();
      console.log("service token response: ", json);
      return String(json.service_token);
    },
    async startDeployment(serviceName: string) {
      if (!this.accessToken) {
        throw new Error("No access token");
      }
      const serviceToken = await this.fetchServiceToken(
        serviceName,
        this.accessToken,
        "frontend"
      );
      const headers = {
        authorization: `Bearer ${serviceToken}`,
        "content-type": "application/json",
      };
      const response = await fetch(this.getUrl("deployments"), {
        method: "POST",
        headers: headers,
      });
      const deployment = createDeployment(await response.json());
      console.log("start deployment response: ", deployment);
      this.deployments.set(deployment.id, deployment);
      return deployment;
    },
    async login(username: string, password: string) {
      let formData = new FormData();
      formData.append("username", username);
      formData.append("password", password);
      const response = await fetch(this.getUrl("token"), {
        method: "POST",
        body: formData,
      });
      const result = await response.json();
      if (!response.ok) {
        // error
        console.log("login error: ", result);
        return { accessToken: null, errorMessage: result.detail };
      } else {
        console.log("login success: ", result);
        return { accessToken: result.access_token, errorMessage: null };
      }
    },
    async fetchServices() {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        "content-type": "application/json",
      };
      const response = await fetch(this.getUrl("services"), {
        headers: headers,
      });
      const services = await response.json();
      console.log("fetchServices: ", services);
      for (const item of services) {
        const message = { ...item, type: "service" };
        console.log("notify with message: ", message);
        this.notifyStores(message);
      }
      return services;
    },
    async addService(service) {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        "content-type": "application/json",
      };
      const response = await fetch(this.getUrl("services"), {
        method: "POST",
        headers: headers,
        body: JSON.stringify(service),
      });
      return await response.json();
    },
    async deleteService(serviceId: number) {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        "content-type": "application/json",
      };
      const response = await fetch(this.getUrl(`services/${serviceId}`), {
        method: "DELETE",
        headers: headers,
      });
      console.log("delete service: ", await response.json());
      if (response.ok) {
        return serviceId;
      } else {
        return null;
      }
    },
    async fetchDeployments() {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        "content-type": "application/json",
      };
      const response = await fetch(this.getUrl("deployments"), {
        headers: headers,
      });
      const deployments = (await response.json()).map(createDeployment);
      for (const deployment of deployments) {
        client.deployments.set(deployment.id, deployment);
      }
      console.log("fetchDeployments: ", deployments);
      for (const deployment of deployments) {
        client.deployments.set(deployment.id, deployment);
      }
      return deployments;
    },
    async fetchStepsFromDeployment(deploymentId: number) {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        "content-type": "application/json",
      };
      console.log("fetchStepsFromDeployment: ", deploymentId);
      const params = {
        deployment_id: deploymentId.toString(),
      };
      const response = await fetch(
        this.getUrl("steps/?" + new URLSearchParams(params)),
        {
          headers: headers,
        }
      );
      const steps = (await response.json()).map(createStep);
      console.log("fetchSteps by deployment id: ", steps);
      for (const step of steps) {
        client.steps.set(step.id, step);
      }
      return steps;
    },
  };
  return client;
}
