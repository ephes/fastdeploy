import { vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive } from "vue";
import { initPinia } from "./conftest";
import { useDeployments } from "../src/stores/deployment";
import { useAuth } from "../src/stores/auth";
import DeploymentList from "../src/components/DeploymentList.vue";

const { route } = vi.hoisted(() => ({ route: { params: {} as Record<string, string> } }));
vi.mock("vue-router", () => ({ useRoute: () => route }));
const row = (id: number, service_id = 1) => ({ id, service_id, origin: "fixture", user: "fixture-user", type: "deployment" });
const page = Array.from({ length: 50 }, (_, i) => row(100 - i));

beforeEach(() => {
  initPinia();
  route.params = reactive({ serviceId: "1" });
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
  route.params.serviceId = "2";
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
