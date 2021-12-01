import { ServiceWithId, Service } from "../src/typings";
import { createWebsocketClient } from "../src/websocket";
import { useServices } from "../src/stores/service";
import { createEvent, initPinia } from "./conftest";

const service: ServiceWithId = {
  id: 1,
  name: "fastdeploy",
  data: {},
  type: "service",
};

describe("Services via Store Websocket", () => {
  beforeEach(() => {
    initPinia();
  });

  it("has no service store registered", () => {
    const servicesStore = useServices();
    const websocketClient = createWebsocketClient();
    websocketClient.onMessage(createEvent(service));
    expect(servicesStore.services).toStrictEqual({});
  });

  it("received create or update service", () => {
    const servicesStore = useServices();
    const websocketClient = createWebsocketClient();
    websocketClient.registerStore(servicesStore);
    websocketClient.onMessage(createEvent(service));
    expect(servicesStore.services[service.id]).toStrictEqual(service);
  });

  it("received delete service", () => {
    const servicesStore = useServices();
    const websocketClient = createWebsocketClient();
    websocketClient.registerStore(servicesStore);
    servicesStore.services[service.id] = service;
    websocketClient.onMessage(createEvent({ ...service, deleted: true }));
    expect(servicesStore.services).toStrictEqual({});
  });
});

describe("Services Store Actions", () => {
  beforeEach(() => {
    initPinia();
  });

  it("adds a service to the store", async () => {
    const servicesStore = useServices();
    const newService: Service = {
      name: "fastdeploy",
      data: {},
    };
    servicesStore.new = newService;
    servicesStore.client = {
      async post<T = unknown>(): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve({ ...newService, id: 1});
        });
      },
      options: {headers: {}},
    } as any;
    await servicesStore.addService();
    expect(servicesStore.services[1]).toStrictEqual({ ...newService, id: 1 });
  });

  it("deletes a service from the store", async () => {
    const servicesStore = useServices();
    servicesStore.services[service.id] = service;
    servicesStore.client = {
      async delete<T = unknown>(url: string | number): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve(service.id);
        });
      },
      options: {headers: {}},
    } as any;
    await servicesStore.deleteService(service.id);
    expect(servicesStore.services).toStrictEqual({});
  });

  it("fetches the list of services", async () => {
    const servicesStore = useServices();
    servicesStore.client = {
      async  get<T = unknown>(url: string | number): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve([service]);
        });
      },
      options: {headers: {}},
    } as any;
    await servicesStore.fetchServices();
    expect(servicesStore.services[service.id]).toStrictEqual(service);
  });
});
