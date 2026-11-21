import { Step } from "../src/typings";
import { pythonToJavascript } from "../src/converters";
import { createWebsocketClient } from "../src/websocket";
import { useDeployments } from "../src/stores/deployment";
import { useSteps } from "../src/stores/step";
import { getClientWithoutAuth } from "../src/stores/httpClient";
import { createEvent, initPinia } from "./conftest";

const apiStep: object = {
  id: 1,
  name: "Create unix user deploy",
  state: "pending",
  message: "",
  deployment_id: 1,
  started: "2021-11-23T10:04:01.276123",
  finished: null,
  deleted: false,
  type: "step",
};

const step: Step = pythonToJavascript(apiStep) as Step;

describe("Steps Store Websocket", () => {
  beforeEach(() => {
    initPinia();
  });

  it("has no steps store registered", () => {
    const stepsStore = useSteps();
    const websocketClient = createWebsocketClient();
    websocketClient.onMessage(createEvent(apiStep));
    expect(stepsStore.steps).toStrictEqual({});
  });

  it("has a steps store registered", () => {
    const stepsStore = useSteps();
    const websocketClient = createWebsocketClient();
    websocketClient.registerStore(stepsStore);
    websocketClient.onAuthenticationMessage({ type: "authentication", status: "success" });
    websocketClient.onMessage(createEvent(apiStep));
    expect(stepsStore.steps[step.id]).toStrictEqual(step);
  });
});

describe("Steps Store Actions", () => {
  beforeEach(() => {
    initPinia();
  });

  it("fetches the list of steps for a deployment", async () => {
    const stepsStore = useSteps();
    stepsStore.client = {
      async get<T = unknown>(url: string | number): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve([apiStep]);
        });
      },
      options: { headers: {} },
    } as any;
    await stepsStore.fetchStepsFromDeployment(step.deploymentId);
    expect(stepsStore.steps[step.id]).toStrictEqual(step);
  });
});

describe("Steps Store Getters", () => {
  beforeEach(() => {
    initPinia();
  });

  it("Steps by deployment returns a list of steps", () => {
    const stepsStore = useSteps();
    stepsStore.addStep(step);
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual([
      step,
    ]);
  });

  it("Steps by deployment sorts finished above not finished", async () => {
    const stepsStore = useSteps();
    const withoutFinished = step;
    stepsStore.addStep(withoutFinished);
    const withFinished = {
      ...withoutFinished,
      id: 2,
      finished: withoutFinished.started,
    };
    stepsStore.addStep(withFinished);
    const expected = [withFinished, withoutFinished];
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual(
      expected
    );
  });

  it("Steps by deployment sorts earlier finished above later", async () => {
    const stepsStore = useSteps();
    const earlier = {...step, finished: step.started};
    const laterDate = new Date((earlier.finished as Date).getTime() + 1000);
    const later = {...earlier, id: 2, finished: laterDate};
    stepsStore.addStep(later);
    stepsStore.addStep(earlier);
    const expected = [earlier, later];
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual(
      expected
    );
  });

  it("Steps by deployment sorts started above not started", async () => {
    const stepsStore = useSteps();
    const withStarted = step;
    const withoutStarted = {...withStarted, id: 2, started: null};
    stepsStore.addStep(withoutStarted);
    stepsStore.addStep(withStarted);
    const expected = [withStarted, withoutStarted];
    expect(stepsStore.getStepsByDeployment(step.deploymentId)).toStrictEqual(
      expected
    );
  });
});


describe("Step lifecycle and scroll bounds", () => {
  beforeEach(() => initPinia());

  it("keeps only the five recent scroll candidates for 10,000 sequential steps", () => {
    useDeployments().onMessage({ id: 1, type: "deployment", serviceId: 1, finished: null } as any);
    const store = useSteps();
    for (let id = 1; id <= 10000; id++) {
      const running = { ...step, id, state: "running" };
      store.onMessage(running);
      store.onMessage({ ...running, state: "success", finished: new Date() } as Step);
    }
    expect(store.stepsInProgressByDeployment[1].map(row => row.id)).toEqual([10000, 9999, 9998, 9997, 9996]);
    expect(store.shouldScrollToStep(store.steps[9996])).toBe(true);
    expect(Object.keys(store.steps)).toHaveLength(10000);
    store.onMessage({ ...store.steps[9996], deleted: true } as Step);
    expect(store.stepsInProgressByDeployment[1]).toHaveLength(4);
    store.onMessage({ id: 1, type: "deployment", finished: new Date() } as any);
    store.onMessage({ ...step, id: 10001, state: "running" } as Step);
    expect(store.stepsInProgressByDeployment[1]).toBeUndefined();
  });

  it("retires the scroll target when REST reports deployment completion", async () => {
    const deployments = useDeployments();
    const store = useSteps();
    const deploymentRow = {
      id: step.deploymentId,
      service_id: 1,
      origin: "test",
      user: "test",
      started: "2021-11-23T10:03:00Z",
      finished: "2021-11-23T10:05:00Z",
    };
    deployments.client = {
      get: vi.fn().mockResolvedValueOnce([{ ...deploymentRow, finished: null }])
        .mockResolvedValueOnce([deploymentRow]),
    } as any;
    await deployments.fetchDeployments();
    for (let id = 1; id <= 5; id++) {
      const running: Step = { ...step, id, state: "running" };
      store.onMessage(running);
    }
    expect(store.shouldScrollToStep(store.steps[1])).toBe(true);

    await deployments.fetchDeployments();

    expect(deployments.deployments[step.deploymentId].finished).toBeInstanceOf(Date);
    expect(store.shouldScrollToStep(store.steps[1])).toBe(false);
    const lateStep: Step = { ...step, id: 6, state: "running" };
    store.onMessage(lateStep);
    expect(store.stepsInProgressByDeployment[step.deploymentId]).toBeUndefined();
    expect(store.steps[6].state).toBe("running");
  });

  it("does not reinsert an evicted duplicate running event", () => {
    const store = useSteps();
    for (let id = 1; id <= 6; id++) store.onMessage({ ...step, id, state: "running" } as Step);
    store.onMessage({ ...step, id: 1, state: "running" } as Step);
    expect(store.stepsInProgressByDeployment[1].map(row => row.id)).toEqual([6, 5, 4, 3, 2]);
  });

  it.each([false, true])("rejects terminal regressions and resurrection (REST pending: %s)", async pending => {
    const store = useSteps();
    let respond!: (rows: unknown) => void;
    store.client = { get: () => new Promise(resolve => { respond = resolve; }) } as any;
    const fetch = pending ? store.fetchStepsFromDeployment(1) : Promise.resolve();
    const terminal = { ...step, state: "success", finished: new Date() };
    store.onMessage(terminal);
    store.onMessage({ ...step, state: "running" } as Step);
    expect(store.steps[1]).toEqual(terminal);
    store.onMessage({ ...terminal, deleted: true } as Step);
    store.onMessage({ ...step, state: "running" } as Step);
    // A rerun has a fresh step id, even when the name is identical.
    store.onMessage({ ...step, id: 2, state: "running" } as Step);
    if (pending) respond([apiStep]);
    await fetch;
    expect(store.steps[1]).toBeUndefined();
    expect(store.steps[2].state).toBe("running");
  });
});

describe("Step inventory pages", () => {
  beforeEach(() => initPinia());
  const row = (id: number) => ({ ...apiStep, id });

  it("rejects a deletion for a step owned by another deployment before changing either inventory", async () => {
    const store = useSteps();
    store.addStep({ ...step, state: "running" });
    const original = store.steps[step.id];
    let respond!: (rows: unknown) => void;
    store.client = { get: () => new Promise(resolve => { respond = resolve; }) } as any;
    const unrelated = store.fetchStepsFromDeployment(2);
    const [changes] = store.pendingFetches[2]!;

    const conflictingDelete: Step = { ...step, deploymentId: 2, deleted: true };
    store.onMessage(conflictingDelete);
    respond([]);
    await unrelated;

    expect(store.steps[step.id]).toBe(original);
    expect(store.stepsByDeployment[1][step.id]).toBe(original);
    expect(store.stepCounts).toEqual({ 1: 1 });
    expect(store.stepsInProgressByDeployment[1]).toEqual([original]);
    expect(store.deletedSteps).toEqual({});
    expect(store.deletedByDeployment).toEqual({});
    expect(changes.has(step.id)).toBe(false);
  });

  it("repairs a running step from REST after refusing a delayed pending event", async () => {
    const store = useSteps();
    store.addStep({ ...step, state: "running" });
    let respond!: (rows: unknown) => void;
    store.client = { get: () => new Promise(resolve => { respond = resolve; }) } as any;
    const fetch = store.fetchStepsFromDeployment(step.deploymentId);

    store.onMessage(step);
    expect(store.steps[step.id].state).toBe("running");
    respond([{ ...apiStep, state: "success", finished: "2021-11-23T10:05:00Z" }]);
    await fetch;

    expect(store.steps[step.id].state).toBe("success");
    expect(store.stepsByDeployment[step.deploymentId][step.id]).toBe(store.steps[step.id]);
  });

  it("stages pages until completion and preserves events across boundaries", async () => {
    const store = useSteps();
    store.addStep({ ...step, id: 99 });
    let respond!: (rows: unknown) => void;
    const get = vi.fn().mockResolvedValueOnce(Array.from({ length: 25 }, (_, i) => row(50 - i)))
      .mockImplementationOnce(() => new Promise(resolve => { respond = resolve; }));
    store.client = { get } as any;
    const fetch = store.fetchStepsFromDeployment(1);
    // Let the first page finish; it must not remove absent cached rows yet.
    await Promise.resolve(); await Promise.resolve();
    expect(get).toHaveBeenCalledTimes(2);
    expect(store.steps[99]).toBeDefined();
    store.onMessage({ ...step, id: 26, deleted: true } as Step);
    store.onMessage({ ...step, id: 25, state: "success", finished: new Date() } as Step);
    store.onMessage({ ...step, id: 51, state: "running" } as Step);
    respond([row(25), row(24)]);
    await fetch;
    expect(get.mock.calls[1][0]).toContain("before_id=26");
    expect(store.steps[99]).toBeUndefined();
    expect(store.steps[26]).toBeUndefined();
    expect(store.steps[25].state).toBe("success");
    expect(store.steps[51]).toBeDefined();
    expect(store.inventoryComplete[1]).toBe(true);
  });

  it("records step events only in active snapshot fences for their deployment", async () => {
    const store = useSteps();
    const respond: ((rows: unknown) => void)[] = [];
    store.client = { get: () => new Promise(resolve => respond.push(resolve)) } as any;
    const older = store.fetchStepsFromDeployment(1);
    const unrelated = store.fetchStepsFromDeployment(2);
    const current = store.fetchStepsFromDeployment(1);

    const add = vi.spyOn(Set.prototype, "add");
    const update = { ...step, message: "newer websocket update" };
    store.onMessage(update);
    const writes = add.mock.calls.filter(([id]) => id === step.id).length;
    add.mockRestore();

    respond[0]([apiStep]);
    await older;
    respond[1]([]);
    respond[2]([apiStep]);
    await Promise.all([unrelated, current]);

    expect(writes).toBe(2);
    expect(store.steps[step.id].message).toBe("newer websocket update");
  });

  it("requests an empty final page when the last page was full", async () => {
    const store = useSteps();
    const get = vi.fn().mockResolvedValueOnce(Array.from({ length: 25 }, (_, i) => row(25 - i)))
      .mockResolvedValueOnce([]);
    store.client = { get } as any;
    await store.fetchStepsFromDeployment(1);
    expect(get).toHaveBeenCalledTimes(2);
    expect(get.mock.calls[1][0]).toContain("before_id=1");
    expect(store.inventoryComplete[1]).toBe(true);
    expect(Object.keys(store.steps)).toHaveLength(25);
  });

  it.each(["failure", "ownership loss"])("keeps a published inventory complete through refresh %s", async outcome => {
    const store = useSteps();
    store.client = { get: async () => [apiStep] } as any;
    await store.fetchStepsFromDeployment(1);
    expect(store.inventoryComplete[1]).toBe(true);
    const original = store.steps[step.id];

    let settled!: () => void;
    const transportError = new Error("fixture transport failure");
    store.client = { get: () => new Promise((resolve, reject) => {
      settled = () => outcome === "failure" ? reject(transportError) : resolve([row(2)]);
    }) } as any;
    let ownsRefresh = true;
    const refreshing = store.fetchStepsFromDeployment(1, () => ownsRefresh);
    const completeWhileFetching = store.inventoryComplete[1];
    expect(store.fetching[1]).toBe(1);
    ownsRefresh = outcome === "failure";
    settled();
    if (outcome === "failure") await expect(refreshing).rejects.toBe(transportError);
    else await refreshing;

    expect(store.inventoryComplete[1]).toBe(true);
    expect(completeWhileFetching).toBe(true);
    expect(store.steps).toEqual({ [step.id]: original });
    expect(store.stepsByDeployment[1][step.id]).toBe(original);
    expect(store.fetching[1]).toBeUndefined();
  });

  it.each(["error", "invalid", "logout"])("does not publish partial inventories after %s", async outcome => {
    const store = useSteps();
    store.addStep(step);
    const get = vi.fn().mockResolvedValueOnce(Array.from({ length: 25 }, (_, i) => row(50 - i)));
    if (outcome === "error") get.mockRejectedValueOnce(new Error("fixture"));
    else get.mockImplementationOnce(async () => {
      if (outcome === "logout") { const { useAuth } = await import("../src/stores/auth"); useAuth().endSession(); }
      return [row(50)]; // Cursor did not advance.
    });
    store.client = { get } as any;
    const fetch = store.fetchStepsFromDeployment(1);
    if (outcome === "logout") { await fetch; expect(store.steps).toEqual({}); }
    else { await expect(fetch).rejects.toThrow(); expect(Object.keys(store.steps)).toEqual(["1"]); }
    expect(store.inventoryComplete[1]).not.toBe(true);
    expect(store.pendingFetches).toEqual({});
  });
});

describe("Whole inventory admission", () => {
  beforeEach(() => initPinia());
  it("refuses more than 1000 staged rows without replacing known state, then retries", async () => {
    const store = useSteps();
    store.addStep(step);
    let next = 2000;
    const get = vi.fn(async () => Array.from({ length: 25 }, () => ({ ...apiStep, id: next-- })));
    store.client = { get } as any;
    await expect(store.fetchStepsFromDeployment(1)).rejects.toThrow();
    expect(get.mock.calls.length).toBeLessThanOrEqual(41);
    expect(Object.keys(store.steps)).toEqual(["1"]);
    expect(store.inventoryComplete[1]).toBe(false);
    store.client = { get: async () => [apiStep] } as any;
    await store.fetchStepsFromDeployment(1);
    expect(store.inventoryComplete[1]).toBe(true);
  });

  it("bounds cumulative page bytes", async () => {
    const store = useSteps();
    store.addStep(step);
    let next = 1000;
    const get = vi.fn(async (_url: string, options: any) => {
      const page = Array.from({ length: 25 }, () => ({ ...apiStep, id: next--, message: "x".repeat(32_000) }));
      options.onBodyBytes(new TextEncoder().encode(JSON.stringify(page)).byteLength);
      return page;
    });
    store.client = { get } as any;
    await expect(store.fetchStepsFromDeployment(1)).rejects.toThrow();
    expect(Object.keys(store.steps)).toEqual(["1"]);
    expect(get.mock.calls.length).toBeLessThanOrEqual(11);
  });

  it("counts actual response bytes, including whitespace padding, across pages", async () => {
    const store = useSteps();
    store.addStep(step);
    let next = 1000;
    const padded = () => {
      const json = JSON.stringify(Array.from({ length: 25 }, () => ({ ...apiStep, id: next-- })));
      return json + " ".repeat(1_000_000 - json.length);
    };
    const fetch = vi.fn(async () => new Response(padded()));
    vi.stubGlobal("fetch", fetch);
    try {
      store.client = getClientWithoutAuth();
      await expect(store.fetchStepsFromDeployment(1)).rejects.toThrow(/too large/);
      // 8 MiB of real bytes is exhausted within the ninth 1 MB page, long before 1,000 rows.
      expect(fetch.mock.calls.length).toBe(9);
      expect(Object.keys(store.steps)).toEqual(["1"]);
      expect(store.inventoryComplete[1]).toBe(false);
    } finally { vi.unstubAllGlobals(); }
  });

  it("aborts the pending page at the whole traversal deadline", async () => {
    vi.useFakeTimers();
    try {
      const store = useSteps();
      let signal!: AbortSignal;
      store.client = { get: (_url: string, options: any) => {
        signal = options?.signal;
        return new Promise(() => {});
      } } as any;
      const result = expect(store.fetchStepsFromDeployment(1)).rejects.toThrow();
      await vi.advanceTimersByTimeAsync(30_000);
      await result;
      expect(signal.aborted).toBe(true);
      expect(store.pendingFetches).toEqual({});
    } finally { vi.useRealTimers(); }
  });
});
