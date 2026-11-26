import { vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, watch } from "vue";
import { initPinia } from "./conftest";
import { useDeployments } from "../src/stores/deployment";
import { useAuth } from "../src/stores/auth";
import { useServices } from "../src/stores/service";
import { useSteps } from "../src/stores/step";
import DeploymentList from "../src/components/DeploymentList.vue";

const { route } = vi.hoisted(() => ({ route: { query: {} as Record<string, string> } }));
vi.mock("vue-router", () => ({ useRoute: () => route }));
const row = (id: number, service_id = 1) => ({ id, service_id, started: '2026-11-01T00:00:00Z', finished: null, origin: "fixture", user: "fixture-user", type: "deployment" });
const page = Array.from({ length: 50 }, (_, i) => row(100 - i));

beforeEach(() => {
  initPinia();
  route.query = reactive({ serviceId: "1" });
});

it("loads bounded pages explicitly and keeps events during load more", async () => {
  const store = useDeployments();
  let respond!: (rows: any[]) => void;
  const get = vi.fn().mockResolvedValueOnce(page).mockImplementationOnce(() => new Promise((resolve) => (respond = resolve)));
  store.client = { get } as any;
  await store.fetchDeployments(1);
  expect(get).toHaveBeenLastCalledWith("deployments/?limit=50&service_id=1");
  expect(store.historyHasMore).toBe(true);
  const pending = store.fetchDeployments(1, true);
  expect(get).toHaveBeenLastCalledWith("deployments/?limit=50&service_id=1&before_id=51");
  const finished = { ...row(50), serviceId: 1, finished: new Date() };
  store.onMessage(finished as any);
  store.onMessage({ ...row(49), deleted: true } as any);
  respond([row(50), row(49), row(48)]);
  await pending;
  expect(store.deployments[50].finished).toEqual(finished.finished);
  expect(store.deployments[49]).toBeUndefined();
  expect(store.historyDeployments.map((d) => d.id)).toEqual([...page.map((d) => d.id), 50, 48]);
  expect(store.historyHasMore).toBe(false);
  expect(store.pendingFetches).toEqual([]);
});

it("reopens an evicted deployment from REST despite a refused late event", async () => {
  const store = useDeployments();
  const finished = new Date("2026-11-01T00:00:01Z");
  const finishedEvent = (id: number) => ({ ...row(id), type: "deployment" as const, serviceId: 1, finished });
  // Finished events outside the current service filter are eligible for eviction.
  store.client.get = vi.fn().mockResolvedValue([]);
  await store.fetchDeployments(2);
  for (let id = 1; id <= 101; id++) {
    store.onMessage(finishedEvent(id));
  }
  expect(store.deployments[1]).toBeUndefined();

  let respond!: (rows: unknown) => void;
  store.client.get = vi.fn(() => new Promise(resolve => { respond = resolve; })) as typeof store.client.get;
  const refresh = store.fetchDeployments(1);
  store.onMessage(finishedEvent(1));
  expect(store.deployments[1]).toBeUndefined();
  respond([{ ...row(1), finished: finished.toISOString() }]);
  await refresh;

  expect(store.historyDeployments.map(({ id }) => id)).toEqual([1]);
  expect(store.deployments[1].finished).toEqual(finished);
});

it("applies a refused finish to the stale REST row of an uncached older run", async () => {
  const store = useDeployments();
  const finished = new Date("2026-11-01T00:00:01Z");
  store.client.get = vi.fn().mockResolvedValue([]);
  await store.fetchDeployments(1);
  // Deleting a newer run advances the retirement fence past the never-cached run 1.
  store.onMessage({ ...row(2), serviceId: 1, deleted: true } as any);

  let respond!: (rows: unknown) => void;
  store.client.get = vi.fn(() => new Promise(resolve => { respond = resolve; })) as typeof store.client.get;
  const refresh = store.fetchDeployments(1);
  const finishEvent = { ...row(1), type: "deployment" as const, serviceId: 1, finished };
  store.onMessage(finishEvent);
  expect(store.deployments[1]).toBeUndefined();
  respond([row(1)]);
  await refresh;

  expect(store.historyDeployments.map(({ id }) => id)).toEqual([1]);
  expect(store.deployments[1].finished).toEqual(finished);
  expect(store.retiredFinishes.size).toBe(0);
});

it("keeps a buffered finish across a later start acknowledgement and delayed start event", async () => {
  const store = useDeployments();
  const services = useServices();
  services.services[1] = { id: 1, name: "fastdeploy", data: {} } as any;
  services.fetchServiceToken = vi.fn().mockResolvedValue("service-token");
  const finished = new Date("2026-11-01T00:00:01Z");
  store.client.get = vi.fn().mockResolvedValue([]);
  await store.fetchDeployments(1);
  store.onMessage({ ...row(2), serviceId: 1, deleted: true } as any);

  let respond!: (rows: unknown) => void;
  store.client.get = vi.fn(() => new Promise(resolve => { respond = resolve; })) as typeof store.client.get;
  const refresh = store.fetchDeployments(1);
  const finishEvent = { ...row(1), type: "deployment" as const, serviceId: 1, finished };
  store.onMessage(finishEvent);
  const client = { post: vi.fn().mockResolvedValue(row(1)), options: { headers: {} } } as any;
  await store.startDeployment("fastdeploy", client);
  const lateStart = { ...row(1), type: "deployment" as const, serviceId: 1, started: new Date(row(1).started) };
  store.onMessage(lateStart);
  expect(store.deployments[1].finished).toEqual(finished);
  respond([row(1)]);
  await refresh;

  expect(store.deployments[1].finished).toEqual(finished);
});

it("keeps a refused finish for a start acknowledged after the history page settled", async () => {
  const store = useDeployments();
  const services = useServices();
  services.services[1] = { id: 1, name: "fastdeploy", data: {} } as any;
  services.fetchServiceToken = vi.fn().mockResolvedValue("service-token");
  const finished = new Date("2026-11-01T00:00:01Z");
  store.client.get = vi.fn().mockResolvedValue([]);
  await store.fetchDeployments(1);
  store.onMessage({ ...row(2), serviceId: 1, deleted: true } as any);

  let acknowledge!: (value: unknown) => void;
  const client = { post: vi.fn(() => new Promise(resolve => { acknowledge = resolve; })), options: { headers: {} } } as any;
  const starting = store.startDeployment("fastdeploy", client);
  await flushPromises();
  const finishEvent = { ...row(1), type: "deployment" as const, serviceId: 1, finished };
  store.onMessage(finishEvent);
  store.client.get = vi.fn().mockResolvedValue([]);
  await store.fetchDeployments(1);
  acknowledge(row(1));
  expect((await starting)!.finished).toEqual(finished);
  const lateStart = { ...row(1), type: "deployment" as const, serviceId: 1, started: new Date(row(1).started) };
  store.onMessage(lateStart);

  expect(store.deployments[1].finished).toEqual(finished);
});

it("bounds refused finishes kept for later admission", async () => {
  const store = useDeployments();
  store.onMessage({ ...row(500), serviceId: 1, deleted: true } as any);
  const finished = new Date("2026-11-01T00:00:01Z");
  for (let id = 1; id <= 150; id++) {
    const finishEvent = { ...row(id), type: "deployment" as const, serviceId: 1, finished };
    store.onMessage(finishEvent);
  }
  expect(store.retiredFinishes.size).toBe(100);
  expect(store.retiredFinishes.has(50)).toBe(false);
  expect(store.retiredFinishes.has(150)).toBe(true);
});

it("keeps a cached finish when a REST page returns the deployment unfinished", async () => {
  const store = useDeployments();
  const finished = "2026-11-01T00:00:01Z";
  store.client.get = vi.fn().mockResolvedValue([{ ...row(1), finished }]);
  await store.fetchDeployments(1);
  store.client.get = vi.fn().mockResolvedValue([row(1)]);
  await store.fetchDeployments(1);

  expect(store.deployments[1].finished).toEqual(new Date(finished));
});

it("reconciles REST history despite a refused late start for a finished deployment", async () => {
  const store = useDeployments();
  const started = row(1);
  const finished = "2026-11-01T00:00:01Z";
  store.client.get = vi.fn().mockResolvedValue([{ ...started, finished }]);
  await store.fetchDeployments(1);

  let respond!: (rows: unknown) => void;
  store.client.get = vi.fn(() => new Promise(resolve => { respond = resolve; })) as typeof store.client.get;
  const refresh = store.fetchDeployments(1);
  const lateStart = { ...store.deployments[1], finished: null };
  store.onMessage(lateStart);
  expect(store.deployments[1].finished).toEqual(new Date(finished));
  respond([]);
  await refresh;

  expect(store.historyIds).toEqual([]);
  expect(store.deployments[1]).toBeUndefined();
});

it("ignores old filter pages and logout responses including paging metadata", async () => {
  const store = useDeployments();
  let respond!: (rows: any[]) => void;
  store.client = { get: vi.fn().mockImplementationOnce(() => new Promise((resolve) => (respond = resolve))).mockResolvedValueOnce([row(3, 2)]) } as any;
  const old = store.fetchDeployments(1);
  await store.fetchDeployments(2);
  respond(page);
  await old;
  expect(store.historyDeployments.map((d) => d.id)).toEqual([3]);
  store.client = { get: () => new Promise((resolve) => (respond = resolve)) } as any;
  const pending = store.fetchDeployments(2);
  useAuth().logout();
  respond(page);
  await pending;
  expect(store.deployments).toEqual({});
  expect(store.historyIds).toEqual([]);
  expect(store.historyBeforeId).toBeNull();
  expect(store.historyLoading).toBe(false);
});

it("keeps the history window and load-more capacity scoped to the new service", async () => {
  const store = useDeployments();
  const previous = Array.from({ length: 50 }, (_, i) => row(350 - i));
  const next = Array.from({ length: 50 }, (_, i) => row(100 - i, 2));
  let respond!: (rows: unknown) => void;
  const get = vi.fn().mockResolvedValueOnce(previous)
    .mockImplementationOnce(() => new Promise(resolve => { respond = resolve; }))
    .mockResolvedValueOnce([row(50, 2)]);
  store.client = { get } as any;
  await store.fetchDeployments(1);
  const live = (id: number, serviceId: number) => ({ id, serviceId, type: "deployment", finished: new Date() } as const);
  for (let id = 351; id <= 501; id++) store.onMessage(live(id, 1) as any);

  const switching = store.fetchDeployments(2);
  for (let id = 351; id <= 501; id++) store.onMessage(live(id, 1) as any);
  store.onMessage(live(502, 2) as any);
  respond(next);
  await switching;

  await store.fetchDeployments(2, true);
  expect(get).toHaveBeenLastCalledWith("deployments/?limit=50&service_id=2&before_id=51");
  expect(store.historyIds).toEqual([502, ...next.map(({ id }) => id), 50]);
  expect(store.historyDeployments.map(({ id }) => id)).toEqual(store.historyIds);
});

it("reconciles a full stale history with bounded collection updates", async () => {
  const store = useDeployments();
  const services = useServices();
  services.services[1] = { id: 1, name: "fixture", data: {} };
  vi.spyOn(services, "fetchServiceToken").mockResolvedValue("synthetic-token");
  const live = (id: number) => ({ ...row(id), type: "deployment" as const, serviceId: 1, finished: new Date() });
  for (let id = 401; id <= 600; id++) store.onMessage(live(id));
  expect(store.historyIds).toHaveLength(200);

  let respond!: (rows: unknown) => void;
  store.client.get = vi.fn(() => new Promise(resolve => { respond = resolve; })) as typeof store.client.get;
  store.client.post = vi.fn().mockResolvedValue(row(602));
  const refresh = store.fetchDeployments(1);
  const updated = live(575);
  store.onMessage(updated);
  const deleted = { ...live(299), deleted: true };
  store.onMessage(deleted);
  await store.startDeployment("fixture", store.client);

  const replacement = Array.from({ length: 50 }, (_, i) => row(300 - i));
  let publications = 0;
  const stop = watch(() => store.historyIds, () => { publications++; }, { flush: "sync" });
  try {
    respond(replacement);
    await refresh;
    expect(store.historyIds).toEqual([575, ...replacement.map(({ id }) => id).filter(id => id !== 299)]);
    expect(store.deployments[575]).toEqual(updated);
    expect(store.deployments[602]).toBeDefined();
    expect(store.deployments[600]).toBeUndefined();
    expect(store.deployments[299]).toBeUndefined();
    expect(store.historyBeforeId).toBe(251);
    expect(store.historyHasMore).toBe(true);
    // Reconciliation, pruning and cursor clipping each publish at most once.
    expect(publications).toBeLessThanOrEqual(3);
  } finally {
    stop();
  }
});

it("evicts step inventories for omitted rows while keeping the open detail and live updates", async () => {
  const store = useDeployments();
  const steps = useSteps();
  const finished = "2026-11-01T00:00:01Z";
  const step = (id: number, deploymentId = id) => ({
    id, deployment_id: deploymentId, type: "step", name: "fixture",
    state: "success", message: "", started: row(id).started, finished,
  });
  store.client.get = vi.fn().mockResolvedValue([3, 2, 1].map(id => ({ ...row(id), finished })));
  steps.client.get = vi.fn()
    .mockResolvedValueOnce([step(1)])
    .mockResolvedValueOnce([step(2)])
    .mockResolvedValueOnce([step(3)]);
  await store.fetchDeployments(1);
  for (const id of [1, 2, 3]) await steps.fetchStepsFromDeployment(id);
  expect(steps.inventoryComplete).toEqual({ 1: true, 2: true, 3: true });
  store.displayedDeploymentId = 2;

  let resolveHistory!: (rows: unknown) => void;
  let resolveSteps!: (rows: unknown) => void;
  store.client.get = vi.fn(() => new Promise(resolve => { resolveHistory = resolve; })) as typeof store.client.get;
  steps.client.get = vi.fn(() => new Promise(resolve => { resolveSteps = resolve; })) as typeof steps.client.get;
  const historyRefresh = store.fetchDeployments(1);
  const stepRefresh = steps.fetchStepsFromDeployment(1);
  const updated = { ...store.deployments[3], finished: new Date(finished) };
  store.onMessage(updated);
  resolveHistory([]);
  await historyRefresh;
  const cachedAfterHistory = steps.steps[1];
  resolveSteps([step(4, 1)]);
  await stepRefresh;

  expect(store.historyError).toBe("");
  expect(store.historyIds).toEqual([3]);
  expect(store.deployments[1]).toBeUndefined();
  expect(cachedAfterHistory).toBeUndefined();
  expect(steps.steps[4]).toBeUndefined();
  expect(steps.stepsByDeployment[1]).toBeUndefined();
  expect(steps.inventoryComplete[1]).toBeUndefined();
  expect(store.deployments[2]).toBeDefined();
  expect(store.deployments[3]).toEqual(updated);
  expect(steps.inventoryComplete).toEqual({ 2: true, 3: true });
  expect(Object.keys(steps.steps)).toEqual(["2", "3"]);
});

it("navigates service history and exposes load more and errors", async () => {
  const store = useDeployments();
  const get = vi.fn().mockResolvedValueOnce(page).mockResolvedValueOnce([row(50)]).mockRejectedValueOnce(new Error("fixture failure"));
  store.client = { get } as any;
  const wrapper = mount(DeploymentList, { global: { stubs: { "router-link": true } } });
  await flushPromises();
  expect(wrapper.find("button").text()).toBe("Load more");
  await wrapper.find("button").trigger("click");
  await flushPromises();
  expect(get).toHaveBeenCalledTimes(2);
  expect(wrapper.find("button").exists()).toBe(false);
  route.query.serviceId = "2";
  await flushPromises();
  expect(get).toHaveBeenLastCalledWith("deployments/?limit=50&service_id=2");
  expect(wrapper.find('[role="alert"]').text()).toContain("Could not load deployment history");
  wrapper.unmount();
});

it("keeps updates below the loaded cursor out of the visible history gap", async () => {
  const store = useDeployments();
  store.client = { get: vi.fn().mockResolvedValue(page) } as any;
  await store.fetchDeployments(1);
  store.onMessage({ ...row(2), serviceId: 1, finished: new Date() } as any);
  store.onMessage({ ...row(101), serviceId: 1 } as any);
  expect(store.deployments[2].finished).toBeInstanceOf(Date);
  expect(store.historyDeployments.map((d) => d.id)).toEqual([101, ...page.map((d) => d.id)]);
});

it.each(["initial load", "refresh"])("hides old event-only rows after the first page of %s", async (kind) => {
  const store = useDeployments();
  if (kind === "refresh") {
    store.client = { get: vi.fn().mockResolvedValue(page) } as any;
    await store.fetchDeployments(1);
  }
  let respond!: (rows: any[]) => void;
  store.client = { get: () => new Promise((resolve) => (respond = resolve)) } as any;
  const pending = store.fetchDeployments(1);
  store.onMessage({ ...row(2), serviceId: 1, finished: new Date() } as any);
  store.onMessage({ ...row(101), serviceId: 1 } as any);
  respond(page);
  await pending;
  expect(store.deployments[2].finished).toBeInstanceOf(Date);
  expect(store.historyDeployments.map((d) => d.id)).toEqual([101, ...page.map((d) => d.id)]);
});
