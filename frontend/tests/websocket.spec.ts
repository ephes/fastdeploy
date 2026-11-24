import { vi, beforeEach, afterEach, it, expect } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import WebsocketStatus from "../src/components/WebsocketStatus.vue";
import { initPinia } from "./conftest";
import { createWebsocketClient } from "../src/websocket";
import { useWebsocketStore } from "../src/stores/websocket";
import { useAuth } from "../src/stores/auth";
import { useSettings } from "../src/stores/config";

import { useServices } from "../src/stores/service";
import { useDeployments } from "../src/stores/deployment";
import { useSteps } from "../src/stores/step";

class Socket {
  static CLOSED = 3;
  static instances: Socket[] = [];
  readyState = 0;
  onopen: any = null;
  onclose: any = null;
  onmessage: any = null;
  send = vi.fn();
  close = vi.fn(() => { this.readyState = 3; });
  constructor(public url: string) { Socket.instances.push(this); }
  receive(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }); }
}
beforeEach(() => {
  initPinia();
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
  vi.useFakeTimers();
  vi.spyOn(console, "log").mockImplementation(() => {});
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("recovers when sending websocket credentials throws", async () => {
  const client = createWebsocketClient();
  const status = useWebsocketStore();
  const logout = vi.spyOn(useAuth(), "logout");
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  client.initWebsocketConnection("ws://synthetic", "synthetic-secret");
  const socket = Socket.instances[0];
  const lateMessage = socket.onmessage;
  const lateClose = socket.onclose;
  socket.readyState = 1;
  socket.send.mockImplementation(() => { throw new Error("synthetic-secret"); });
  // An unresponsive peer may leave the retired transport closing.
  socket.close.mockImplementation(() => { socket.readyState = 2; });

  expect(() => socket.onopen({ target: socket })).not.toThrow();
  expect(socket.close).toHaveBeenCalledOnce();
  expect(status.connection).toBe("CLOSED");
  expect(status.authentication).toBe("not authenticated");
  expect(status.connectionError).toBe("Unable to send websocket credentials.");
  expect(warn).toHaveBeenCalledExactlyOnceWith(status.connectionError);

  lateMessage({ data: JSON.stringify({ type: "authentication", status: "failure" }) });
  lateClose({ target: socket });
  expect(logout).not.toHaveBeenCalled();
  expect(client.retryCount).toBe(1);
  await vi.advanceTimersByTimeAsync(1000);
  expect(Socket.instances).toHaveLength(2);
});

it("times out a silent websocket peer and uses only the bounded retries", async () => {
  const client = createWebsocketClient();
  const status = useWebsocketStore();
  const logout = vi.spyOn(useAuth(), "logout");
  vi.spyOn(console, "warn").mockImplementation(() => {});
  client.initWebsocketConnection("ws://synthetic", "token");

  for (let attempt = 0; attempt < 4; attempt++) {
    const socket = Socket.instances[attempt];
    const lateMessage = socket.onmessage;
    socket.readyState = 1;
    socket.onopen({ target: socket });
    await vi.advanceTimersByTimeAsync(14999);
    expect(status.authentication).toBe("authenticating...");
    expect(socket.close).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(socket.close).toHaveBeenCalledOnce();
    expect(status.connection).toBe("CLOSED");
    expect(status.authentication).toBe("not authenticated");
    expect(status.connectionError).toBe("Websocket authentication timed out.");
    lateMessage({ data: JSON.stringify({ type: "authentication", status: "failure" }) });
    expect(logout).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1000);
  }

  expect(Socket.instances).toHaveLength(4);
  expect(client.retryCount).toBe(3);
  expect(vi.getTimerCount()).toBe(0);
});

it.each(["success", "failure", "logout", "replacement", "close", "invalid frame"])(
  "cancels the websocket authentication deadline on %s",
  async (outcome) => {
    const auth = useAuth();
    auth.authenticatedApi = useSettings().api;
    auth.accessToken = "token";
    await auth.initWebsocketClient();
    const client = auth.websocketClient!;
    const socket = Socket.instances[0];
    const status = useWebsocketStore();
    vi.spyOn(console, "warn").mockImplementation(() => {});
    socket.readyState = 1;
    socket.onopen({ target: socket });
    await vi.advanceTimersByTimeAsync(5000);
    expect(vi.getTimerCount()).toBe(1);

    switch (outcome) {
      case "success":
      case "failure":
        socket.receive({ type: "authentication", status: outcome });
        break;
      case "logout":
        auth.logout();
        break;
      case "replacement":
        client.initWebsocketConnection("ws://synthetic", "new-token");
        break;
      case "close":
        socket.readyState = 3;
        void socket.onclose({ target: socket });
        break;
      case "invalid frame":
        socket.onmessage({ data: "malformed" });
        break;
    }

    // Success leaves the activity indicator timer, and close leaves the retry wait.
    expect(vi.getTimerCount()).toBe(outcome === "success" || outcome === "close" ? 1 : 0);
    await vi.advanceTimersByTimeAsync(16000);
    expect(status.connectionError).toBe("");
    expect(Socket.instances).toHaveLength(outcome === "replacement" || outcome === "close" ? 2 : 1);
    if (outcome === "success") {
      expect(status.authentication).toBe("authenticated");
      expect(socket.close).not.toHaveBeenCalled();
    }
  }
);

it("ignores all queued callbacks from a replaced socket", async () => {
  const client = createWebsocketClient();
  const store = { onMessage: vi.fn() };
  client.registerStore(store);
  client.initWebsocketConnection("ws://synthetic", "token-a");
  const a = Socket.instances[0];
  const old = { open: a.onopen, close: a.onclose, message: a.onmessage };
  client.initWebsocketConnection("ws://synthetic", "token-b");
  const b = Socket.instances[1];
  b.readyState = 1;
  b.onopen({ target: b });
  b.receive({ type: "authentication", status: "success" });
  const logout = vi.spyOn(useAuth(), "logout").mockImplementation(() => {});
  const before = { ...useWebsocketStore().$state };
  client.retryCount = 2;
  old.open({ target: a });
  old.message({ data: JSON.stringify({ type: "authentication", status: "failure" }) });
  old.message({ data: JSON.stringify({ type: "service", id: 1, name: "old", data: {} }) });
  await old.close({ target: a });
  await vi.advanceTimersByTimeAsync(500);
  expect(a.onopen).toBeNull();
  expect(a.onclose).toBeNull();
  expect(a.onmessage).toBeNull();
  expect(a.close).toHaveBeenCalledOnce();
  expect(a.send).not.toHaveBeenCalled();
  expect(b.send).toHaveBeenCalledOnce();
  expect(logout).not.toHaveBeenCalled();
  expect(store.onMessage).not.toHaveBeenCalled();
  expect(useWebsocketStore().$state).toEqual(before);
  expect(client.retryCount).toBe(2);
});

it("retires a reconnect continuation when its socket is replaced", async () => {
  const client = createWebsocketClient();
  client.initWebsocketConnection("ws://synthetic", "token");
  const a = Socket.instances[0];
  a.readyState = 3;
  const waiting = a.onclose({ target: a });
  client.initWebsocketConnection("ws://synthetic", "new-token");
  Socket.instances[1].readyState = 3;
  await vi.advanceTimersByTimeAsync(5000);
  await waiting;
  expect(Socket.instances).toHaveLength(2);
  expect(client.retryCount).toBe(1);
});

const step = { type: "step", id: 1, deployment_id: 2, name: "synthetic", state: "running", message: "ok", started: null, finished: null };
it.each([
  "invalid sentinel-secret", "null", "[]", '{}', '{"type":"unknown"}',
  '{"type":"authentication","status":true}', '{"type":"authentication","status":"failure","detail":42}',
  JSON.stringify({ ...step, id: "1" }), JSON.stringify({ ...step, state: "other" }),
  JSON.stringify({ ...step, started: "1" }), JSON.stringify({ ...step, started: "nonsense" }), JSON.stringify({ ...step, message: null }),
  JSON.stringify({ type: "service", id: 1, name: "x", data: [] }),
])("refuses malformed frame %s without dispatch or logout", (data) => {
  const client = createWebsocketClient();
  client.initWebsocketConnection("ws://synthetic", "token");
  const store = { onMessage: vi.fn() };
  client.registerStore(store);
  const logout = vi.spyOn(useAuth(), "logout").mockImplementation(() => {});
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  const received = useWebsocketStore().lastMessageReceived;
  expect(() => Socket.instances[0].onmessage({ data })).not.toThrow();
  expect(store.onMessage).not.toHaveBeenCalled();
  expect(logout).not.toHaveBeenCalled();
  expect(useWebsocketStore().lastMessageReceived).toBe(received);
  expect(useWebsocketStore().handling).toBe("Invalid websocket message; refresh to resynchronize.");
  const status = mount(WebsocketStatus);
  expect(status.text()).toContain("Invalid websocket message; refresh to resynchronize.");
  status.unmount();
  expect(Socket.instances[0].close).toHaveBeenCalledOnce();
  expect(JSON.stringify(warn.mock.calls)).not.toContain("sentinel-secret");
  // Already queued frames on the failed connection must also be ignored.
  Socket.instances[0].receive(step);
  expect(store.onMessage).not.toHaveBeenCalled();
});

it("admits domain messages only after each socket authenticates", async () => {
  const client = createWebsocketClient();
  const store = { onMessage: vi.fn() };
  client.registerStore(store);
  for (const store of [useServices(), useDeployments()]) {
    store.client = { get: vi.fn().mockResolvedValue([]) } as any;
  }
  const domainMessages = [step,
    { type: "service", id: 1, name: "s", data: {}, deleted: true },
    { type: "deployment", id: 2, service_id: 1, origin: "test", user: "u", started: "2026-11-01T00:00:00Z", finished: null },
    { type: "user", id: 1, name: "u" }];

  for (let i = 0; i < 2; i++) {
    client.initWebsocketConnection("ws://synthetic", "token");
    const socket = Socket.instances[i];
    expect(useWebsocketStore().authentication).toBe("not authenticated");
    store.onMessage.mockClear();
    socket.receive({ type: "warning", detail: "synthetic warning" });
    socket.receive({ message: "Client left" });
    for (const message of domainMessages) socket.receive(message);
    expect(store.onMessage).not.toHaveBeenCalled();

    socket.receive({ type: "authentication", status: "success", detail: null });
    expect(useWebsocketStore().authentication).toBe("authenticated");
    for (const message of domainMessages) socket.receive(message);
    expect(store.onMessage).toHaveBeenCalledTimes(4);
  }
  await flushPromises();
});

it.each(["hasOwnProperty", "has_own_property", "started"])("ignores undeclared %s fields before conversion", (key) => {
  const client = createWebsocketClient();
  client.initWebsocketConnection("ws://synthetic", "token");
  const store = { onMessage: vi.fn() };
  client.registerStore(store);
  const message: Record<string, unknown> = { type: "service", id: 1, name: "synthetic", data: {}, [key]: { toString: null } };
  Socket.instances[0].receive({ type: "authentication", status: "success" });
  expect(() => Socket.instances[0].receive(message)).not.toThrow();
  expect(store.onMessage).toHaveBeenCalledOnce();
  expect(store.onMessage).toHaveBeenCalledWith({ type: "service", id: 1, name: "synthetic", data: {} });
});


it("resnapshots mounted stores on authenticated reconnect, coalescing repeated auth", async () => {
  const client = createWebsocketClient();
  const services = useServices(), deployments = useDeployments(), steps = useSteps();
  for (const store of [services, deployments, steps]) client.registerStore(store);
  services.services = { 1: { id: 1, name: "kept", data: {} }, 2: { id: 2, name: "deleted offline", data: {} } };
  deployments.deployments[7] = { id: 7, serviceId: 1, finished: null } as any;
  deployments.deployments[8] = { id: 8, serviceId: 2, finished: null } as any;
  deployments.historyIds = [8, 7];
  steps.addStep({ id: 1, deploymentId: 7, state: "running" } as any);
  steps.addStep({ id: 2, deploymentId: 8, state: "running" } as any);
  const finished = "2026-11-13T12:00:00Z";
  const get = vi.fn(async (url: string) => {
    if (url === "services/") return [{ id: 1, name: "kept", data: {} }];
    if (url === "services/names/") return ["kept"];
    if (url.startsWith("deployments/")) return [{ id: 7, service_id: 1, started: '2026-11-01T00:00:00Z', origin: 'fixture', user: 'synthetic', finished }];
    return [];
  });
  for (const store of [services, deployments, steps]) store.client = { get } as any;
  client.initWebsocketConnection("ws://synthetic", "token");
  Socket.instances[0].receive({ type: "authentication", status: "success" });
  expect(get).not.toHaveBeenCalled();
  Socket.instances[0].readyState = 3;
  const closing = Socket.instances[0].onclose({});
  await vi.advanceTimersByTimeAsync(1000); await closing;
  const replacement = Socket.instances[1];
  replacement.receive({ type: "authentication", status: "success" });
  replacement.receive({ type: "authentication", status: "success" });
  await flushPromises();
  expect(Object.keys(services.services)).toEqual(["1"]);
  expect(deployments.historyIds).toEqual([7]);
  expect(deployments.deployments[7].finished).toEqual(new Date(finished));
  expect(deployments.deployments[8]).toBeUndefined();
  expect(steps.steps).toEqual({});
  expect(steps.stepsInProgressByDeployment[7]).toBeUndefined();
  expect(get.mock.calls.filter(([url]) => url === "services/")).toHaveLength(1);
});

it.each(["logout", "replacement"])("fences a reconnect refresh after %s", async outcome => {
  const client = createWebsocketClient();
  const services = useServices();
  let resolve!: (value: any[]) => void;
  const response = new Promise<any[]>(yes => { resolve = yes; });
  services.client = { get: vi.fn().mockReturnValue(response) } as any;
  useDeployments().client = { get: vi.fn().mockResolvedValue([]) } as any;
  client.initWebsocketConnection("ws://synthetic", "token");
  Socket.instances[0].receive({ type: "authentication", status: "success" });
  client.initWebsocketConnection("ws://synthetic", "token");
  Socket.instances[1].receive({ type: "authentication", status: "success" });
  await flushPromises(); expect(services.client.get).toHaveBeenCalled();
  if (outcome === "logout") { client.dispose(); useAuth().endSession(); }
  else client.initWebsocketConnection("ws://synthetic", "replacement");
  resolve([{ id: 99, name: "obsolete", data: {} }]); await flushPromises();
  expect(services.services).toEqual({}); expect(services.serviceNames).toEqual([]);
  expect(services.servicesLoading).toBe(false); expect(services.serviceNamesLoading).toBe(false);
});

it.each(["complete", "logout", "replacement"])("bounds queued step inventories on reconnect (%s)", async outcome => {
  const client = createWebsocketClient();
  const services = useServices(), deployments = useDeployments(), steps = useSteps();
  const ids = Array.from({ length: 20 }, (_, i) => i + 1);
  for (const id of ids) steps.addStep({ id, deploymentId: id, state: "running" } as any);
  const getServices = vi.fn().mockResolvedValue([]);
  const getHistory = vi.fn().mockResolvedValue([]);
  services.client = { get: getServices } as any;
  deployments.client = { get: getHistory } as any;
  const started: number[] = [];
  let peak = 0;
  const pending: ((fail?: boolean) => void)[] = [];
  steps.client = {
    get: (url: string) => new Promise((resolve, reject) => {
      started.push(Number(new URLSearchParams(url.split("?")[1]).get("deployment_id")));
      pending.push(fail => fail ? reject(new Error("synthetic request failure")) : resolve([]));
      peak = Math.max(peak, pending.length);
    }),
  } as any;

  client.initWebsocketConnection("ws://synthetic", "token");
  Socket.instances[0].receive({ type: "authentication", status: "success" });
  client.initWebsocketConnection("ws://synthetic", "token");
  Socket.instances[1].receive({ type: "authentication", status: "success" });
  expect(started).toEqual(ids.slice(0, 4));
  expect(getServices).toHaveBeenCalledTimes(2);
  expect(getHistory).toHaveBeenCalledOnce();

  if (outcome === "logout") {
    useAuth().logout();
  } else if (outcome === "replacement") {
    client.initWebsocketConnection("ws://synthetic", "token");
    Socket.instances[2].receive({ type: "authentication", status: "success" });
    expect(started).toHaveLength(4);
  }

  let first = true;
  while (pending.length) {
    pending.shift()!(outcome === "complete" && first);
    first = false;
    await flushPromises();
  }

  expect(peak).toBe(4);
  if (outcome === "logout") {
    expect(started).toEqual(ids.slice(0, 4));
    expect(steps.inventoryComplete).toEqual({});
  } else {
    expect(started).toEqual(outcome === "replacement" ? [...ids.slice(0, 4), ...ids] : ids);
    const refreshed = ids.filter(id => steps.inventoryComplete[id]);
    expect(refreshed).toEqual(outcome === "complete" ? ids.slice(1) : ids);
  }
});
