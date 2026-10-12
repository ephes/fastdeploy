import { vi } from "vitest";
import { mount } from "@vue/test-utils";
import { initPinia } from "./conftest";
import ServiceList from "../src/components/ServiceList.vue";
import { useAuth } from "../src/stores/auth";
import { useServices } from "../src/stores/service";
import { useDeployments } from "../src/stores/deployment";
import { useSteps } from "../src/stores/step";
import { useWebsocketStore } from "../src/stores/websocket";
import { getClient } from "../src/stores/httpClient";

const routerPush = vi.fn();
vi.mock("vue-router", () => ({
  useRouter: () => ({ push: routerPush }),
}));

/**
 * A websocket whose events are fired by the test.
 */
class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  closeCalls = 0;
  onopen: ((event: any) => void) | null = null;
  onclose: ((event: any) => void) | null = null;
  onmessage: ((event: any) => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closeCalls++;
    this.readyState = FakeWebSocket.CLOSED;
  }
  /** the server accepted the connection */
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.({ target: this });
  }
  /** the server (or the network) dropped the connection */
  drop() {
    this.readyState = FakeWebSocket.CLOSED;
    return this.onclose?.({ target: this });
  }
  receive(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

/**
 * A promise the test resolves or rejects when it wants the "response" to arrive.
 */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: any) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/**
 * An http client that records the Authorization header of every request
 * and answers from the given table.
 */
function recordingClient(authorization: string | undefined, answers: { [url: string]: any }, log: string[]) {
  const answer = (method: string) => async (url: string) => {
    log.push(`${method} ${url} ${client.options.headers.Authorization}`);
    return answers[url];
  };
  const client: any = {
    options: { headers: authorization ? { Authorization: authorization } : {} },
    get: answer("GET"),
    post: answer("POST"),
    delete: answer("DELETE"),
  };
  return client;
}

const apiService = { id: 1, name: "fastdeploy", data: {}, type: "service" };
const apiDeployment = {
  id: 7,
  service_id: 1,
  origin: "frontend",
  user: "alice",
  started: "2021-11-23T10:03:01.000000",
  finished: null,
  type: "deployment",
};
const apiStep = {
  id: 3,
  name: "step",
  state: "running",
  deployment_id: 7,
  message: "private output",
  started: "2021-11-23T10:03:02.000000",
  finished: null,
  type: "step",
};

function loginAs(username: string, token: string) {
  const authStore = useAuth();
  authStore.username = username;
  authStore.password = `${username}-password`;
  authStore.client = {
    async post() {
      return { access_token: token };
    },
    options: { headers: {} },
  } as any;
  return authStore.login();
}

describe("Logout", () => {
  const realWebSocket = globalThis.WebSocket;

  /** "METHOD url authorization" of every request that reached fetch */
  let requests: string[] = [];

  beforeEach(() => {
    FakeWebSocket.instances = [];
    (globalThis as any).WebSocket = FakeWebSocket;
    routerPush.mockReset();
    requests = [];
    // the stores' own clients end here instead of on the network
    vi.stubGlobal("fetch", async (url: any, init: any = {}) => {
      const headers = new Headers(init.headers);
      requests.push(`${init.method} ${url} ${headers.get("Authorization")}`);
      return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.useFakeTimers();
    vi.spyOn(console, "log").mockImplementation(() => {});
    initPinia();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    (globalThis as any).WebSocket = realWebSocket;
  });

  /**
   * Log in as alice with an authenticated websocket and one service,
   * deployment and step in the stores.
   */
  async function aliceSession() {
    const authStore = useAuth();
    // the services fetched right after login come from the dummy client
    await loginAs("alice", "alice-token");
    await vi.advanceTimersByTimeAsync(0);
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.receive({ type: "authentication", status: "success" });
    socket.receive(apiService);
    socket.receive(apiDeployment);
    socket.receive(apiStep);
    return { authStore, socket };
  }

  it("logs in with an authenticated websocket and private data", async () => {
    const { authStore, socket } = await aliceSession();
    expect(authStore.isAuthenticated).toBe(true);
    expect(FakeWebSocket.instances.length).toBe(1);
    expect(socket.sent).toStrictEqual([JSON.stringify({ access_token: "alice-token" })]);
    expect(useWebsocketStore().isOnline).toBe(true);
    expect(Object.keys(useServices().services)).toStrictEqual(["1"]);
    expect(Object.keys(useDeployments().deployments)).toStrictEqual(["7"]);
    expect(Object.keys(useSteps().steps)).toStrictEqual(["3"]);
    expect(useServices().client.options.headers.Authorization).toBe("Bearer alice-token");
    expect(requests).toStrictEqual([
      "GET http://localhost:8000/services/ Bearer alice-token",
      "GET http://localhost:8000/services/names/ Bearer alice-token",
    ]);
  });

  it("sends no request with the old token after logout", async () => {
    const { authStore } = await aliceSession();
    requests.length = 0;

    authStore.logout();
    await useServices().fetchServices();
    await useDeployments().fetchDeployments();
    await useSteps().fetchStepsFromDeployment(7);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(requests.length).toBe(3);
    for (const request of requests) {
      expect(request.endsWith(" null")).toBe(true);
    }
  });

  it("forgets the password after login and does not keep it in the client", async () => {
    const authStore = useAuth();
    await loginAs("alice", "alice-token");
    expect(authStore.password).toBe("");
    expect(JSON.stringify(authStore.client.options)).not.toContain("alice-password");
  });

  it("does not keep the password in the client after a failed login", async () => {
    const authStore = useAuth();
    authStore.username = "alice";
    authStore.password = "alice-password";
    const options: any = { headers: {} };
    authStore.client = {
      async post() {
        expect(options.body).toContain("alice-password");
        const error: any = Error("Unauthorized");
        error.response = { status: 401 };
        throw error;
      },
      options,
    } as any;
    await authStore.login();
    expect(authStore.errorMessage).toBe("Invalid username or password");
    expect("body" in options).toBe(false);
  });

  it("clears token, password and all private store state on logout", async () => {
    const { authStore } = await aliceSession();
    useServices().serviceNames = ["fastdeploy", "other"];
    useServices().serviceTokenErrorMessage = "private error";
    useServices().syncRefusal = { message: "refused", wouldDelete: ["fastdeploy"], total: 1 };
    useServices().syncErrorMessage = "private sync error";
    authStore.password = "typed-again";

    authStore.logout();

    expect(authStore.isAuthenticated).toBe(false);
    expect(authStore.accessToken).toBe(null);
    expect(authStore.password).toBe("");
    expect(authStore.websocketClient).toBe(null);
    expect(useServices().services).toStrictEqual({});
    expect(useServices().serviceNames).toStrictEqual([]);
    expect(useServices().serviceTokenErrorMessage).toBe("");
    expect(useServices().syncRefusal).toBe(null);
    expect(useServices().syncErrorMessage).toBe("");
    expect(useDeployments().deployments).toStrictEqual({});
    expect(useSteps().steps).toStrictEqual({});
    expect(useSteps().stepsByDeployment).toStrictEqual({});
    expect(useSteps().stepsInProgressByDeployment).toStrictEqual({});
    expect(useWebsocketStore().connection).toBe("not connected");
    expect(useWebsocketStore().authentication).toBe("not authenticated");
  });

  it("replaces the authenticated http clients on logout", async () => {
    const { authStore } = await aliceSession();
    const stores = [useServices(), useDeployments(), useSteps()];
    const before = stores.map((store) => store.client);
    for (const client of before) {
      expect(client.options.headers.Authorization).toBe("Bearer alice-token");
    }

    authStore.logout();

    stores.forEach((store, index) => {
      expect(store.client).not.toBe(before[index]);
      expect("Authorization" in store.client.options.headers).toBe(false);
    });
    expect("Authorization" in authStore.client.options.headers).toBe(false);
    // a client created while logged out is unauthenticated, not "Bearer null"
    expect("Authorization" in getClient().options.headers).toBe(false);
  });

  it("closes the websocket on logout and never reconnects", async () => {
    const { authStore, socket } = await aliceSession();

    authStore.logout();

    expect(socket.closeCalls).toBe(1);
    expect(socket.onclose).toBe(null);
    expect(socket.onopen).toBe(null);
    expect(socket.onmessage).toBe(null);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(FakeWebSocket.instances.length).toBe(1);
    expect(socket.sent.length).toBe(1);
  });

  it("does not reconnect with the old token when the socket dropped just before logout", async () => {
    const { authStore, socket } = await aliceSession();
    // the reconnect loop of the old client is now waiting on its timer
    const reconnecting = socket.drop();
    await vi.advanceTimersByTimeAsync(500);

    authStore.logout();
    await vi.advanceTimersByTimeAsync(10_000);
    await reconnecting;

    expect(FakeWebSocket.instances.length).toBe(1);
  });

  it("reconnects while logged in (the loop the logout has to stop)", async () => {
    const { socket } = await aliceSession();
    socket.drop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeWebSocket.instances.length).toBe(2);
    FakeWebSocket.instances[1].open();
    expect(FakeWebSocket.instances[1].sent).toStrictEqual([
      JSON.stringify({ access_token: "alice-token" }),
    ]);
  });

  it("does not send the old token on a connection that opens after logout", async () => {
    const { authStore, socket } = await aliceSession();
    socket.drop();
    await vi.advanceTimersByTimeAsync(1000);
    const reconnect = FakeWebSocket.instances[1];
    // keep the handlers the old client registered, as a browser that
    // already queued the events would
    const { onopen, onmessage } = reconnect;

    authStore.logout();
    reconnect.readyState = FakeWebSocket.OPEN;
    onopen?.({ target: reconnect });
    onmessage?.({ data: JSON.stringify(apiDeployment) });

    expect(reconnect.sent).toStrictEqual([]);
    expect(reconnect.closeCalls).toBeGreaterThanOrEqual(1);
    expect(useDeployments().deployments).toStrictEqual({});
    expect(useWebsocketStore().authentication).toBe("not authenticated");
  });

  it("ignores websocket messages queued before logout", async () => {
    const { authStore, socket } = await aliceSession();
    const { onmessage, onclose } = socket;

    authStore.logout();
    onmessage?.({ data: JSON.stringify({ ...apiDeployment, id: 8 }) });
    onmessage?.({ data: JSON.stringify({ ...apiService, id: 2 }) });
    onmessage?.({ data: JSON.stringify({ ...apiStep, id: 4 }) });
    const closing = onclose?.({ target: socket });
    await vi.advanceTimersByTimeAsync(10_000);
    await closing;

    expect(useDeployments().deployments).toStrictEqual({});
    expect(useServices().services).toStrictEqual({});
    expect(useSteps().steps).toStrictEqual({});
    expect(FakeWebSocket.instances.length).toBe(1);
  });

  it("logs out when the websocket authentication fails and stays logged out", async () => {
    const authStore = useAuth();
    await loginAs("alice", "alice-token");
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.receive(apiDeployment);
    const push = vi.fn();
    authStore.router = { push };

    socket.receive({ type: "authentication", status: "failure" });
    await vi.advanceTimersByTimeAsync(10_000);

    expect(authStore.isAuthenticated).toBe(false);
    expect(push).toHaveBeenCalledWith("/login");
    expect(useDeployments().deployments).toStrictEqual({});
    expect(socket.closeCalls).toBe(1);
    expect(FakeWebSocket.instances.length).toBe(1);
  });

  it("drops http responses that arrive after logout", async () => {
    const { authStore } = await aliceSession();
    const services = deferred<any[]>();
    const names = deferred<string[]>();
    const deployments = deferred<any[]>();
    const steps = deferred<any[]>();
    const deleted = deferred<number>();
    const sync = deferred<any>();
    const token = deferred<{ service_token: string }>();
    const serviceStore = useServices();
    serviceStore.client = {
      get: (url: string) => (url === "services/" ? services.promise : names.promise),
      delete: () => deleted.promise,
      post: (url: string) => (url === "service-token" ? token.promise : sync.promise),
      options: { headers: {} },
    } as any;
    useDeployments().client = { get: () => deployments.promise, options: { headers: {} } } as any;
    useSteps().client = { get: () => steps.promise, options: { headers: {} } } as any;

    const pending = [
      serviceStore.fetchServices(),
      serviceStore.fetchServiceNames(),
      serviceStore.deleteService(1),
      useDeployments().fetchDeployments(),
      useSteps().fetchStepsFromDeployment(7),
    ];
    const syncing = serviceStore.syncServices();
    const fetchingToken = serviceStore.fetchServiceToken("fastdeploy", "frontend");

    authStore.logout();
    services.resolve([{ ...apiService, id: 5 }]);
    names.resolve(["fastdeploy"]);
    deleted.resolve(1);
    deployments.resolve([{ ...apiDeployment, id: 9 }]);
    steps.resolve([{ ...apiStep, id: 6 }]);
    const refusal: any = Error("Conflict");
    refusal.response = { status: 409 };
    refusal.body = { detail: { message: "would delete", would_delete: ["fastdeploy"], total: 1 } };
    sync.reject(refusal);
    token.resolve({ service_token: "late-service-token" });
    await Promise.all(pending);
    await vi.advanceTimersByTimeAsync(0);

    expect(await syncing).toBe(false);
    expect(await fetchingToken).toBe(null);
    expect(useServices().services).toStrictEqual({});
    expect(useServices().serviceNames).toStrictEqual([]);
    expect(useServices().syncRefusal).toBe(null);
    expect(useServices().syncErrorMessage).toBe("");
    expect(useServices().serviceTokenErrorMessage).toBe("");
    expect(useDeployments().deployments).toStrictEqual({});
    expect(useSteps().steps).toStrictEqual({});
    expect(useSteps().stepsByDeployment).toStrictEqual({});
  });

  it("drops error state of a service token request that fails after logout", async () => {
    const { authStore } = await aliceSession();
    const token = deferred<{ service_token: string }>();
    useServices().client = { post: () => token.promise, options: { headers: {} } } as any;
    const fetchingToken = useServices().fetchServiceToken("fastdeploy", "frontend");

    authStore.logout();
    const error: any = Error("Unauthorized");
    error.body = { detail: "private detail" };
    token.reject(error);

    expect(await fetchingToken).toBe(null);
    expect(useServices().serviceTokenErrorMessage).toBe("");
  });

  it("does not start a deployment whose service token arrives after logout", async () => {
    const { authStore } = await aliceSession();
    const token = deferred<{ service_token: string }>();
    useServices().client = { post: () => token.promise, options: { headers: {} } } as any;
    const log: string[] = [];
    const client = recordingClient("Bearer alice-token", { "deployments/": apiDeployment }, log);
    const starting = useDeployments().startDeployment("fastdeploy", client);

    authStore.logout();
    token.resolve({ service_token: "late-service-token" });

    expect(await starting).toBe(null);
    expect(log).toStrictEqual([]);
    expect(useDeployments().deployments).toStrictEqual({});
  });

  it("does not store a deployment whose start response arrives after logout", async () => {
    const { authStore } = await aliceSession();
    useServices().fetchServiceToken = vi.fn(async () => "service-token");
    const response = deferred<any>();
    const client = { post: () => response.promise, options: { headers: {} } } as any;
    const starting = useDeployments().startDeployment("fastdeploy", client);
    await vi.advanceTimersByTimeAsync(0);

    authStore.logout();
    response.resolve({ ...apiDeployment, id: 11 });

    expect(await starting).toBe(null);
    expect(useDeployments().deployments).toStrictEqual({});
  });

  it("does not navigate the next user to a deployment the previous user started", async () => {
    const { authStore } = await aliceSession();
    useServices().services[1] = { id: 1, name: "fastdeploy", data: {} };
    useServices().fetchServiceToken = vi.fn(async () => "service-token");
    const response = deferred<any>();
    // the deploy button uses the store's default client
    vi.stubGlobal("fetch", async (url: any, init: any = {}) => {
      if (init.method === "POST" && String(url).endsWith("/deployments/")) {
        return new Response(JSON.stringify(await response.promise), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const wrapper = mount(ServiceList, {
      global: { stubs: { "router-link": true, ProgressCount: true } },
    });
    const deployButton = wrapper.findAll("button").find((button) => button.text() === "deploy");
    await deployButton!.trigger("click");
    await vi.advanceTimersByTimeAsync(0);

    authStore.logout();
    await loginAs("bob", "bob-token");
    response.resolve({ ...apiDeployment, id: 11 });
    await vi.advanceTimersByTimeAsync(10);

    expect(routerPush).not.toHaveBeenCalled();
    expect(useDeployments().deployments).toStrictEqual({});
    wrapper.unmount();
  });

  it("navigates to a deployment started in the current session", async () => {
    await aliceSession();
    useServices().services[1] = { id: 1, name: "fastdeploy", data: {} };
    useServices().fetchServiceToken = vi.fn(async () => "service-token");
    vi.stubGlobal("fetch", async () =>
      new Response(JSON.stringify({ ...apiDeployment, id: 11 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    const wrapper = mount(ServiceList, {
      global: { stubs: { "router-link": true, ProgressCount: true } },
    });
    const deployButton = wrapper.findAll("button").find((button) => button.text() === "deploy");
    await deployButton!.trigger("click");
    await vi.advanceTimersByTimeAsync(10);

    expect(routerPush).toHaveBeenCalledWith({ name: "deployment-detail", params: { id: 11 } });
    wrapper.unmount();
  });

  it("ignores a login response that arrives after a logout", async () => {
    const authStore = useAuth();
    const response = deferred<{ access_token: string }>();
    authStore.username = "alice";
    authStore.password = "alice-password";
    authStore.client = { post: () => response.promise, options: { headers: {} } } as any;
    const loggingIn = authStore.login();

    authStore.logout();
    response.resolve({ access_token: "alice-token" });
    await loggingIn;

    expect(authStore.isAuthenticated).toBe(false);
    expect(FakeWebSocket.instances.length).toBe(0);
  });

  it("gives the next user fresh state and clients", async () => {
    const { authStore, socket: aliceSocket } = await aliceSession();
    const aliceClients = [useServices().client, useDeployments().client, useSteps().client];
    const lateServices = deferred<any[]>();
    useServices().client = { get: () => lateServices.promise, options: { headers: {} } } as any;
    const aliceFetch = useServices().fetchServices();
    const aliceHandlers = { onmessage: aliceSocket.onmessage, onclose: aliceSocket.onclose };

    authStore.logout();
    await loginAs("bob", "bob-token");
    await vi.advanceTimersByTimeAsync(0);

    // bob has a websocket of his own, authenticated with his token
    expect(FakeWebSocket.instances.length).toBe(2);
    const bobSocket = FakeWebSocket.instances[1];
    expect(bobSocket.url).not.toBe(aliceSocket.url);
    bobSocket.open();
    expect(bobSocket.sent).toStrictEqual([JSON.stringify({ access_token: "bob-token" })]);
    bobSocket.receive({ type: "authentication", status: "success" });

    // bob's stores do not hold what alice saw
    expect(useDeployments().deployments).toStrictEqual({});
    expect(useSteps().steps).toStrictEqual({});
    expect(useServices().services).toStrictEqual({});

    // nothing of alice's session arrives in bob's
    lateServices.resolve([{ ...apiService, id: 5, name: "alice-only" }]);
    await aliceFetch;
    aliceHandlers.onmessage?.({ data: JSON.stringify({ ...apiDeployment, id: 8 }) });
    const closing = aliceHandlers.onclose?.({ target: aliceSocket });
    await vi.advanceTimersByTimeAsync(10_000);
    await closing;
    expect(useServices().services).toStrictEqual({});
    expect(useDeployments().deployments).toStrictEqual({});
    expect(FakeWebSocket.instances.length).toBe(2);
    expect(authStore.isAuthenticated).toBe(true);

    // bob's requests carry bob's token and bob's messages are delivered
    const stores = [useServices(), useDeployments(), useSteps()];
    stores.forEach((store, index) => {
      expect(store.client).not.toBe(aliceClients[index]);
      expect(store.client.options.headers.Authorization).toBe("Bearer bob-token");
    });
    bobSocket.receive({ ...apiDeployment, id: 20, user: "bob" });
    expect(Object.keys(useDeployments().deployments)).toStrictEqual(["20"]);
  });

  it("disposes the previous session when logging in again without logout", async () => {
    const { socket: aliceSocket } = await aliceSession();

    await loginAs("bob", "bob-token");
    await vi.advanceTimersByTimeAsync(10_000);

    expect(aliceSocket.closeCalls).toBe(1);
    expect(FakeWebSocket.instances.length).toBe(2);
    expect(useDeployments().deployments).toStrictEqual({});
    expect(useServices().client.options.headers.Authorization).toBe("Bearer bob-token");
  });
});
