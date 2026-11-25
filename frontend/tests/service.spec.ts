import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, vi } from "vitest";
import { ServiceWithId } from "../src/typings";
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

const emptyReceipt = { detail: "Services synced", updated: [], deleted: [], skipped: [] };
const originalConfirmation = "a".repeat(64);
const refusalBody = {
  detail: {
    message: "Refusing to delete 2 of 3 services (more than half)",
    would_delete: ["a", "b"],
    total: 3,
    confirmation: originalConfirmation,
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
        store.client = { post, get: vi.fn().mockResolvedValue([]), options: { headers: {} } } as any;
        const ordinary = store.syncServices();
        const forced = store.syncServices(originalConfirmation);
        const settleOlder = async () => {
          if (olderOutcome === "success") older.resolve(emptyReceipt);
          else older.reject(syncError(olderOutcome === "refusal" ? 409 : 500, refusalBody));
          expect(await ordinary).toBe(false);
          expect(store.syncRefusal).toBeNull();
          expect(store.syncErrorMessage).toBe("");
        };
        if (olderFirst) await settleOlder();
        latest.resolve(emptyReceipt);
        expect(await forced).toBe(true);
        if (!olderFirst) await settleOlder();
        expect(post).toHaveBeenLastCalledWith("/services/sync", undefined, { query: { force: "true", confirmation: originalConfirmation } });
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
    expect(await store.syncServices(originalConfirmation)).toBe(false);
    const refusal = store.syncRefusal;
    const error = store.syncErrorMessage;
    expect(status === 409 ? refusal : error).toBeTruthy();
    older.resolve(emptyReceipt);
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
    const get = vi.fn().mockResolvedValue([]);
    const currentReceipt = { ...emptyReceipt, updated: ["current session"] };
    store.client = { post: vi.fn().mockResolvedValue(currentReceipt), get, options: { headers: {} } } as any;
    expect(await store.syncServices(originalConfirmation)).toBe(true);
    if (outcome === "success") old.resolve({ ...emptyReceipt, updated: ["former session"] });
    else old.reject(syncError(outcome === "refusal" ? 409 : 500, refusalBody));
    expect(await pending).toBe(false);
    expect(get).toHaveBeenCalledTimes(1);
    expect(store.syncReceipt).toEqual({ updated: ["current session"], deleted: [], skipped: [] });
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
      confirmation: originalConfirmation,
    });
    expect(servicesStore.syncErrorMessage).toBe("");
  });

  it("sends force and clears the refusal on a forced sync", async () => {
    const servicesStore = useServices();
    const post = vi.fn().mockResolvedValue(emptyReceipt);
    servicesStore.client = { post, get: vi.fn().mockResolvedValue([]), options: { headers: {} } } as any;
    servicesStore.syncRefusal = { message: "refused", wouldDelete: ["a"], total: 1, confirmation: originalConfirmation };
    const synced = await servicesStore.syncServices(originalConfirmation);
    expect(synced).toBe(true);
    expect(post).toHaveBeenCalledWith("/services/sync", undefined, { query: { force: "true", confirmation: originalConfirmation } });
    expect(servicesStore.syncRefusal).toBeNull();
  });

  it("does not send force on a normal sync", async () => {
    const servicesStore = useServices();
    const post = vi.fn().mockResolvedValue(emptyReceipt);
    servicesStore.client = { post, get: vi.fn().mockResolvedValue([]), options: { headers: {} } } as any;
    await servicesStore.syncServices();
    expect(post).toHaveBeenCalledWith("/services/sync", undefined, {});
  });

  it.each([
    { detail: "Services synced" },
    { ...emptyReceipt, deleted: [1] },
    { ...emptyReceipt, updated: ["duplicate"], deleted: ["duplicate"] },
    { ...emptyReceipt, skipped: [{ name: "busy", reason: 42 }] },
  ])("does not admit an invalid sync receipt: %j", async response => {
    const store = useServices();
    const get = vi.fn();
    store.client = { post: vi.fn().mockResolvedValue(response), get } as any;
    expect(await store.syncServices()).toBe(false);
    expect(store.syncReceipt).toBeNull();
    expect(store.syncErrorMessage).toContain("Could not verify");
    expect(get).not.toHaveBeenCalled();
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

describe("ServiceList sync receipt", () => {
  beforeEach(() => initPinia());

  it.each([false, true])("shows a settled sync without socket delivery (refresh fails: %s)", async refreshFails => {
    const store = useServices();
    const busy = { id: 2, name: "busy", data: {} };
    const added = { id: 3, name: "added", data: {} };
    const receipt = {
      detail: "Services synced",
      updated: [added.name],
      deleted: [service.name],
      skipped: [{ name: busy.name, reason: "deployment 42 is still running" }],
    };
    const get = vi.fn().mockResolvedValue([busy, added]);
    if (refreshFails) get.mockRejectedValueOnce(new Error("offline"));
    const post = vi.fn().mockResolvedValue(receipt);
    store.client = { post, get } as any;
    store.services = { [service.id]: service, [busy.id]: busy };
    store.serviceNames = [added.name];
    const wrapper = mount(ServiceList, {
      global: { stubs: { "router-link": true, "progress-count": true } },
    });

    await wrapper.findAll("button").find(button => button.text() === "sync")!.trigger("click");
    await flushPromises();

    expect(wrapper.get(".sync-receipt").text()).toContain("Updated added");
    expect(wrapper.get(".sync-receipt").text()).toContain("Deleted fastdeploy");
    expect(wrapper.get(".sync-receipt").text()).toContain("deployment 42 is still running");
    expect(get).toHaveBeenCalledExactlyOnceWith("services/");
    expect(store.syncErrorMessage).toBe("");
    if (refreshFails) {
      expect(wrapper.text()).toContain("Could not load services");
      expect(store.getServices.map(row => row.name)).toEqual(["busy", "fastdeploy"]);
      await wrapper.findAll("button").find(button => button.text() === "Retry services")!.trigger("click");
      await flushPromises();
    }
    expect(wrapper.text()).not.toContain("Could not load services");
    expect(store.getServices.map(row => row.name)).toEqual(["added", "busy"]);
    expect(post).toHaveBeenCalledTimes(1);
    wrapper.unmount();
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
    servicesStore.client = { post, get: vi.fn().mockResolvedValue([]), options: { headers: {} } } as any;
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
    { ...refusalBody.detail, confirmation: undefined },
    { ...refusalBody.detail, confirmation: "invalid" },
    { ...refusalBody.detail, total: "3" },
    { ...refusalBody.detail, total: 2.5 },
    { ...refusalBody.detail, total: 1 },
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
    { message: "No services found in the services directory, refusing to delete all 1 services", would_delete: ["a"], total: 1, confirmation: originalConfirmation },
  ])("shows a valid refusal and retries with force after confirmation: %j", async detail => {
    const post = vi
      .fn()
      .mockRejectedValueOnce(syncError(409, { detail }))
      .mockResolvedValueOnce(emptyReceipt);
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
    expect(post).toHaveBeenLastCalledWith("/services/sync", undefined, { query: { force: "true", confirmation: originalConfirmation } });
    expect(servicesStore.syncRefusal).toBeNull();
    expect(wrapper.find(".sync-refusal").exists()).toBe(false);
  });

  it("sends the displayed confirmation and asks again when the deletion set changes", async () => {
    const confirmation = originalConfirmation;
    const replacement = "b".repeat(64);
    const post = vi.fn()
      .mockRejectedValueOnce(syncError(409, { detail: { ...refusalBody.detail, confirmation } }))
      .mockRejectedValueOnce(syncError(409, {
        detail: { message: "The deletion set changed", would_delete: ["a", "b", "c"], total: 3, confirmation: replacement },
      }));
    window.confirm = vi.fn().mockReturnValue(true);
    const { servicesStore, wrapper } = await mountWithRefusal(post);
    await wrapper.findAll(".sync-refusal button").find(button => button.text() === "force sync")!.trigger("click");
    await flushPromises();

    expect(post).toHaveBeenLastCalledWith("/services/sync", undefined, { query: { force: "true", confirmation } });
    expect(wrapper.get(".sync-refusal").text()).toContain("a, b, c");
    expect(servicesStore.syncRefusal).toMatchObject({ confirmation: replacement });
    expect(post).toHaveBeenCalledTimes(2);
    wrapper.unmount();
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
