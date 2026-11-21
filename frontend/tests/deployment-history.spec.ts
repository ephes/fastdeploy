import { vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, watch } from "vue";
import { initPinia } from "./conftest";
import { useDeployments } from "../src/stores/deployment";
import { useAuth } from "../src/stores/auth";
import { useServices } from "../src/stores/service";
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
