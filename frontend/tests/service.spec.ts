import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, vi } from "vitest";
import { ServiceWithId, Service } from "../src/typings";
import { createWebsocketClient } from "../src/websocket";
import { useServices } from "../src/stores/service";
import { createEvent, initPinia } from "./conftest";
import ServiceList from "../src/components/ServiceList.vue";

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
    servicesStore.client = {
      async post<T = unknown>(): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve({ detail: "Services synced"});
        });
      },
      options: {headers: {}},
    } as any;
    await servicesStore.syncServices();
    const serviceViaWebsocket = {...newService, id: 1}
    servicesStore.services[serviceViaWebsocket.id] = serviceViaWebsocket;
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

function syncError(status: number, body: any) {
  const err: any = new Error(status === 409 ? "Conflict" : "Internal Server Error");
  err.response = { status };
  err.body = body;
  return err;
}

const refusalBody = {
  detail: {
    message: "Refusing to delete 2 of 3 services (more than half)",
    would_delete: ["a", "b"],
    total: 3,
  },
};

describe("Services sync", () => {
  beforeEach(() => {
    initPinia();
  });

  it("stores the refusal when the backend refuses the sync", async () => {
    const servicesStore = useServices();
    servicesStore.client = {
      post: vi.fn().mockRejectedValue(syncError(409, refusalBody)),
      options: { headers: {} },
    } as any;
    const synced = await servicesStore.syncServices();
    expect(synced).toBe(false);
    expect(servicesStore.syncRefusal).toStrictEqual({
      message: "Refusing to delete 2 of 3 services (more than half)",
      wouldDelete: ["a", "b"],
      total: 3,
    });
    expect(servicesStore.syncErrorMessage).toBe("");
  });

  it("sends force and clears the refusal on a forced sync", async () => {
    const servicesStore = useServices();
    const post = vi.fn().mockResolvedValue({ detail: "Services synced" });
    servicesStore.client = { post, options: { headers: {} } } as any;
    servicesStore.syncRefusal = { message: "refused", wouldDelete: ["a"], total: 1 };
    const synced = await servicesStore.syncServices(true);
    expect(synced).toBe(true);
    expect(post).toHaveBeenCalledWith("/services/sync", undefined, { query: { force: "true" } });
    expect(servicesStore.syncRefusal).toBeNull();
  });

  it("does not send force on a normal sync", async () => {
    const servicesStore = useServices();
    const post = vi.fn().mockResolvedValue({ detail: "Services synced" });
    servicesStore.client = { post, options: { headers: {} } } as any;
    await servicesStore.syncServices();
    expect(post).toHaveBeenCalledWith("/services/sync", undefined, {});
  });

  it("stores an error message for other failures", async () => {
    const servicesStore = useServices();
    servicesStore.client = {
      post: vi.fn().mockRejectedValue(syncError(500, null)),
      options: { headers: {} },
    } as any;
    const synced = await servicesStore.syncServices();
    expect(synced).toBe(false);
    expect(servicesStore.syncRefusal).toBeNull();
    expect(servicesStore.syncErrorMessage).toBe("Services sync failed: Internal Server Error");
  });
});

describe("ServiceList sync refusal", () => {
  const originalConfirm = window.confirm;

  beforeEach(() => {
    initPinia();
  });

  afterEach(() => {
    window.confirm = originalConfirm;
  });

  async function mountWithRefusal(post: any) {
    const servicesStore = useServices();
    servicesStore.client = { post, options: { headers: {} } } as any;
    servicesStore.serviceNames = ["a"];
    await servicesStore.syncServices();
    const wrapper = mount(ServiceList, {
      global: { stubs: { "router-link": true, "progress-count": true } },
    });
    return { servicesStore, wrapper };
  }

  it("shows the refusal and retries with force after confirmation", async () => {
    const post = vi
      .fn()
      .mockRejectedValueOnce(syncError(409, refusalBody))
      .mockResolvedValueOnce({ detail: "Services synced" });
    const confirm = vi.fn().mockReturnValue(true);
    window.confirm = confirm;
    const { servicesStore, wrapper } = await mountWithRefusal(post);

    const refusal = wrapper.find(".sync-refusal");
    expect(refusal.text()).toContain("Refusing to delete 2 of 3 services");
    expect(refusal.text()).toContain("a, b");

    const forceButton = refusal.findAll("button").find((b) => b.text() === "force sync")!;
    await forceButton.trigger("click");
    await flushPromises();

    expect(confirm).toHaveBeenCalled();
    expect(post).toHaveBeenLastCalledWith("/services/sync", undefined, { query: { force: "true" } });
    expect(servicesStore.syncRefusal).toBeNull();
    expect(wrapper.find(".sync-refusal").exists()).toBe(false);
  });

  it("does not force the sync when the confirmation is cancelled", async () => {
    const post = vi.fn().mockRejectedValue(syncError(409, refusalBody));
    const confirm = vi.fn().mockReturnValue(false);
    window.confirm = confirm;
    const { servicesStore, wrapper } = await mountWithRefusal(post);

    const forceButton = wrapper.findAll(".sync-refusal button").find((b) => b.text() === "force sync")!;
    await forceButton.trigger("click");
    await flushPromises();

    expect(post).toHaveBeenCalledTimes(1);
    expect(servicesStore.syncRefusal).not.toBeNull();
  });
});
