import { App, ref, Ref, reactive } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import { Step, Client, Service, Deployment } from './typings';

function toUtcDate(date: Date): Date {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000);
}

function createStep(message: Step): Step {
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

export function createService(message: Service): Service {
  const service: Service = {
    id: message.id,
    name: message.name,
    collect: message.collect,
    deploy: message.deploy,
    deleted: message.deleted,
  };
  return service;
}

function createDeployment(message: Deployment): Deployment {
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

function getApiBase(): string {
  if (import.meta.env.MODE == 'production') {
    return String(import.meta.env.VITE_API_BASE_PROD);
  } else if (import.meta.env.MODE == 'development') {
    return String(import.meta.env.VITE_API_BASE_DEV);
  } else {
    return 'http://localhost:8000';
  }
}

export function createClient(): Client {
  const client: Client = {
    uuid: uuidv4(),
    apiBase: getApiBase(),
    errorMessage: ref(false),
    connection: null,
    accessToken: null,
    isAuthenticated: ref(false),
    install(app: App, options: any) {
      app.provide('client', this);
    },
    steps: reactive(new Map<number, Step>()),
    services: reactive(new Map<number | undefined, Service>()),
    deployments: reactive(new Map<number, Deployment>()),
    getUrl(path: string): string {
      return new URL(this.apiBase) + path;
    },
    initWebsocketConnection() {
      let websocketUrl = 'ws://localhost:8000/deployments/ws'
      if (import.meta.env.VITE_WEBSOCKET_URL_PROD) {
        websocketUrl = String(import.meta.env.VITE_WEBSOCKET_URL_PROD);
      } else if (import.meta.env.VITE_WEBSOCKET_URL_DEV) {
        websocketUrl = String(import.meta.env.VITE_WEBSOCKET_URL_DEV);
      }
      this.connection = new WebSocket(`${websocketUrl}/${this.uuid}`);
      this.connection.onopen = (event: MessageEvent) => {
        console.log(event);
        console.log('Successfully connected to the echo websocket server...');
        this.authenticateWebsocketConnection();
      };
      this.connection.onmessage = (event: MessageEvent) => {
        const message = JSON.parse(event.data);
        console.log('in client.ts: ', message);
        if (message.type === 'step') {
          const step = createStep(message) as Step;
          console.log('step: ', step);
          if (step.deleted) {
            this.steps.delete(step.id);
          } else {
            this.steps.set(step.id, step);
          }
        } else if (message.type === 'service') {
          const service = createService(message) as Service;
          console.log('service: ', service);
          if (service.deleted) {
            this.services.delete(service.id);
          } else {
            this.services.set(service.id, service);
          }
        } else if (message.type === 'deployment') {
          const deployment = createDeployment(message) as Deployment;
          console.log('deployment: ', deployment);
          if (deployment.deleted) {
            this.deployments.delete(deployment.id);
          } else {
            this.deployments.set(deployment.id, deployment);
          }
        }
      };
    },
    authenticateWebsocketConnection() {
      const credentials = JSON.stringify({ access_token: this.accessToken });
      this.connection.send(credentials);
    },
    async fetchServiceToken(serviceName: string, accessToken: string, origin: string) {
      const headers = {
        authorization: `Bearer ${accessToken}`,
        'content-type': 'application/json',
      };
      const body = JSON.stringify({
        service: serviceName,
        origin,
      });
      console.log('service token body: ', body);
      const response = await fetch(this.getUrl('service-token'), {
        method: 'POST',
        headers: headers,
        body: body,
      });
      const json = await response.json();
      console.log('service token response: ', json);
      return String(json.service_token);
    },
    async startDeployment(serviceName: string) {
      if (!this.accessToken) {
        throw (new Error('No access token'));
      }
      const serviceToken = await this.fetchServiceToken(serviceName, this.accessToken, 'frontend');
      const headers = {
        authorization: `Bearer ${serviceToken}`,
        'content-type': 'application/json',
      };
      const response = await fetch(this.getUrl('deployments'), {
        method: 'POST',
        headers: headers,
      })
      const deployment = createDeployment(await response.json());
      console.log('start deployment response: ', deployment);
      this.deployments.set(deployment.id, deployment);
      return deployment;
    },
    async login(username: string, password: string) {
      console.log('env: ', import.meta.env)
      console.log('running in mode: ', import.meta.env.MODE)
      console.log('api base: ', this.apiBase)
      let formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      const response = await fetch(this.getUrl('token'), {
        method: 'POST',
        body: formData,
      });
      const result = await response.json();
      if (!response.ok) {
        // error
        console.log('login error: ', result);
        client.isAuthenticated.value = false;
        client.errorMessage.value = result.detail;
      } else {
        console.log('login success: ', result);
        client.errorMessage.value = false;
        client.isAuthenticated.value = true;
        client.accessToken = result.access_token;
        client.initWebsocketConnection();
      }
    },
    async fetchServices() {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        'content-type': 'application/json',
      };
      const response = await fetch(this.getUrl('services'), {
        headers: headers,
      });
      const services = await response.json();
      console.log('fetchServices: ', services);
      for (const item of services) {
        const service = createService(item) as Service;
        client.services.set(service.id, service);
      }
      return services;
    },
    async addService(service) {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        'content-type': 'application/json',
      };
      const response = await fetch(this.getUrl('services'), {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(service),
      });
      const newService = createService(await response.json()) as Service;
      client.services.set(newService.id, newService);
      console.log('add service: ', newService);
      return newService;
    },
    async deleteService(serviceId: number) {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        'content-type': 'application/json',
      };
      const response = await fetch(
        this.getUrl(`services/${serviceId}`),
        {
          method: 'DELETE',
          headers: headers,
        }
      );
      console.log('delete service: ', await response.json());
    },
    async fetchDeployments() {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        'content-type': 'application/json',
      };
      const response = await fetch(this.getUrl('deployments'), {
        headers: headers,
      });
      const deployments = (await response.json()).map(createDeployment);
      for (const deployment of deployments) {
        client.deployments.set(deployment.id, deployment);
      }
      console.log('fetchDeployments: ', deployments);
      for (const deployment of deployments) {
        client.deployments.set(deployment.id, deployment);
      }
      return deployments;
    },
    async fetchStepsFromDeployment(deploymentId: number) {
      const headers = {
        authorization: `Bearer ${this.accessToken}`,
        'content-type': 'application/json',
      };
      console.log('fetchStepsFromDeployment: ', deploymentId);
      const params = {
        deployment_id: deploymentId.toString(),
      }
      const response = await fetch(
        this.getUrl('steps/?' + new URLSearchParams(params)),
        {
          headers: headers,
        }
      );
      const steps = (await response.json()).map(createStep);
      console.log('fetchSteps by deployment id: ', steps);
      for (const step of steps) {
        client.steps.set(step.id, step);
      }
      return steps;
    },
  };
  return client;
}
