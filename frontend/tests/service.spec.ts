import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, vi } from "vitest";
import { ServiceWithId, Service } from "../src/typings";
import { createWebsocketClient } from "../src/websocket";
import { useServices } from "../src/stores/service";
import { useAuth } from "../src/stores/auth";
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
    websocketClient.onAuthenticationMessage({ type: "authentication", status: "success" });
    websocketClient.onMessage(createEvent(service));
    expect(servicesStore.services[service.id]).toStrictEqual(service);
  });

  it("received delete service", () => {
    const servicesStore = useServices();
    const websocketClient = createWebsocketClient();
    websocketClient.registerStore(servicesStore);
    websocketClient.onAuthenticationMessage({ type: "authentication", status: "success" });
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

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<unknown>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

describe("Services sync", () => {
  beforeEach(() => {
    initPinia();
  });

  for (const olderOutcome of ["success", "refusal", "error"]) {
    for (const olderFirst of [true, false]) {
      it(`retires older ${olderOutcome} when forced sync starts (older settles first: ${olderFirst})`, async () => {
        const store = useServices();
        const older = deferred();
        const latest = deferred();
        const post = vi.fn().mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise);
        store.client = { post, options: { headers: {} } } as any;
        const ordinary = store.syncServices();
        const forced = store.syncServices(true);
        const settleOlder = async () => {
          if (olderOutcome === "success") older.resolve({ detail: "Services synced" });
          else older.reject(syncError(olderOutcome === "refusal" ? 409 : 500, refusalBody));
          expect(await ordinary).toBe(false);
          expect(store.syncRefusal).toBeNull();
          expect(store.syncErrorMessage).toBe("");
        };
        if (olderFirst) await settleOlder();
        latest.resolve({ detail: "Services synced" });
        expect(await forced).toBe(true);
        if (!olderFirst) await settleOlder();
        expect(post).toHaveBeenLastCalledWith("/services/sync", undefined, { query: { force: "true" } });
      });
    }
  }

  it.each([409, 500])("keeps the latest failure (%s) after an older success", async status => {
    const store = useServices();
    const older = deferred();
    store.client = {
      post: vi.fn().mockReturnValueOnce(older.promise).mockRejectedValueOnce(syncError(status, refusalBody)),
      options: { headers: {} },
    } as any;
    const ordinary = store.syncServices();
    expect(await store.syncServices(true)).toBe(false);
    const refusal = store.syncRefusal;
    const error = store.syncErrorMessage;
    expect(status === 409 ? refusal : error).toBeTruthy();
    older.resolve({ detail: "Services synced" });
    expect(await ordinary).toBe(false);
    expect(store.syncRefusal).toEqual(refusal);
    expect(store.syncErrorMessage).toBe(error);
  });

  it.each(["success", "refusal", "error"])("retires old-session %s even when reset reuses a generation", async outcome => {
    const store = useServices();
    const old = deferred();
    store.client = { post: () => old.promise, options: { headers: {} } } as any;
    const pending = store.syncServices();
    useAuth().logout();
    // A later login starts with a reset services store and fresh clients.
    useAuth().sessionId++;
    store.client = { post: vi.fn().mockResolvedValue({}), options: { headers: {} } } as any;
    expect(await store.syncServices(true)).toBe(true);
    if (outcome === "success") old.resolve({});
    else old.reject(syncError(outcome === "refusal" ? 409 : 500, refusalBody));
    expect(await pending).toBe(false);
    expect(store.syncRefusal).toBeNull();
    expect(store.syncErrorMessage).toBe("");
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

  it.each([
    { message: "Unrelated conflict" },
    "Unrelated conflict",
    { ...refusalBody.detail, message: 42 },
    { ...refusalBody.detail, message: " " },
    { ...refusalBody.detail, would_delete: ["a", 2] },
    { ...refusalBody.detail, would_delete: ["a", ""] },
    { ...refusalBody.detail, would_delete: ["a", "a"] },
    { ...refusalBody.detail, would_delete: [] },
    { ...refusalBody.detail, total: "3" },
    { ...refusalBody.detail, total: 2.5 },
    { ...refusalBody.detail, total: 1 },
    { ...refusalBody.detail, total: 4 },
  ])("does not offer force after an invalid conflict: %j", async detail => {
    const post = vi.fn().mockRejectedValue(syncError(409, { detail }));
    const { servicesStore, wrapper } = await mountWithRefusal(post);

    expect(servicesStore.syncRefusal).toBeNull();
    expect(wrapper.findAll("button").some(button => button.text() === "force sync")).toBe(false);
    expect(wrapper.get(".sync-error").text()).toBe("Services sync failed");
    expect(post).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it.each([
    refusalBody.detail,
    { message: "No services found in the services directory, refusing to delete all 1 services", would_delete: ["a"], total: 1 },
  ])("shows a valid refusal and retries with force after confirmation: %j", async detail => {
    const post = vi
      .fn()
      .mockRejectedValueOnce(syncError(409, { detail }))
      .mockResolvedValueOnce({ detail: "Services synced" });
    const confirm = vi.fn().mockReturnValue(true);
    window.confirm = confirm;
    const { servicesStore, wrapper } = await mountWithRefusal(post);

    const refusal = wrapper.find(".sync-refusal");
    expect(refusal.text()).toContain(detail.message);
    expect(refusal.text()).toContain(detail.would_delete.join(", "));

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
