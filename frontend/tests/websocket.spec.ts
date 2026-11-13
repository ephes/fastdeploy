import { vi, beforeEach, afterEach, it, expect } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import WebsocketStatus from "../src/components/WebsocketStatus.vue";
import { initPinia } from "./conftest";
import { createWebsocketClient } from "../src/websocket";
import { useWebsocketStore } from "../src/stores/websocket";
import { useAuth } from "../src/stores/auth";

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

it("dispatches existing valid domain and control variants", () => {
  const client = createWebsocketClient();
  client.initWebsocketConnection("ws://synthetic", "token");
  const store = { onMessage: vi.fn() };
  client.registerStore(store);
  const socket = Socket.instances[0];
  for (const message of [step, { type: "service", id: 1, name: "s", data: {}, deleted: true },
    { type: "deployment", id: 2, service_id: 1, origin: "test", user: "u", started: "2026-11-01T00:00:00Z", finished: null },
    { type: "user", id: 1, name: "u" }]) socket.receive(message);
  expect(store.onMessage).toHaveBeenCalledTimes(4);
  socket.receive({ type: "authentication", status: "success", detail: null });
  expect(useWebsocketStore().authentication).toBe("authenticated");
  socket.receive({ type: "warning", detail: "expired" });
  socket.receive({ message: "Client left" });
  expect(store.onMessage).toHaveBeenCalledTimes(4);
});

it.each(["hasOwnProperty", "has_own_property", "started"])("ignores undeclared %s fields before conversion", (key) => {
  const client = createWebsocketClient();
  client.initWebsocketConnection("ws://synthetic", "token");
  const store = { onMessage: vi.fn() };
  client.registerStore(store);
  const message: Record<string, unknown> = { type: "service", id: 1, name: "synthetic", data: {}, [key]: { toString: null } };
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
    if (url.startsWith("deployments/")) return [{ id: 7, service_id: 1, finished }];
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
  expect(steps.stepsInProgressByDeployment[7]).toEqual([]);
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
