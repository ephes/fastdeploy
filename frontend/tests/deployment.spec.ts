import { vi } from "vitest";
import { mount } from "@vue/test-utils";
import ServiceList from "../src/components/ServiceList.vue";
import { initPinia, createEvent } from "./conftest";
import { createWebsocketClient } from "../src/websocket";
import { pythonToJavascript } from "../src/converters";
import { useServices } from "../src/stores/service";
import { useDeployments } from "../src/stores/deployment";

const apiDeployment = {
  id: 1,
  service_id: 1,
  origin: "GitHub",
  user: "deploy",
  created: "2021-11-23T10:03:01.000000",
  type: "deployment",
};

const deployment = pythonToJavascript(apiDeployment);

describe("Deployment Store Websocket", () => {
  beforeEach(() => {
    initPinia();
  });

  it("has no deployments store registered", () => {
    const deploymentsStore = useDeployments();
    const websocketClient = createWebsocketClient();
    websocketClient.onMessage(
      createEvent({ ...apiDeployment, type: "deployment" })
    );
    expect(deploymentsStore.deployments).toStrictEqual({});
  });

  it("has a deployments store registered", () => {
    const deploymentsStore = useDeployments();
    const websocketClient = createWebsocketClient();
    websocketClient.registerStore(deploymentsStore);
    websocketClient.onMessage(
      createEvent({ ...apiDeployment, type: "deployment" })
    );
    expect(deploymentsStore.deployments[deployment.id]).toStrictEqual(
      pythonToJavascript(apiDeployment)
    );
  });
});

describe("Deployment Store Actions", () => {
  beforeEach(() => {
    initPinia();
  });

  it("starts a deployment", async () => {
    const servicesStore = useServices();
    const deploymentsStore = useDeployments();
    servicesStore.fetchServiceToken = vi.fn().mockResolvedValue("service-token");
    const client = {
      async post<T = unknown>(): Promise<T> {
        return new Promise<any>((resolve, reject) => {
          resolve(deployment);
        });
      },
      options: { headers: {} },
    } as any;
    await deploymentsStore.startDeployment("fastdeploy", client);
    expect(deploymentsStore.deployments[deployment.id]).toStrictEqual(
      deployment
    );
  });

  it("shows a started deployment under its service right away", async () => {
    const servicesStore = useServices();
    const deploymentsStore = useDeployments();
    servicesStore.fetchServiceToken = vi.fn().mockResolvedValue("service-token");
    // what the backend answers: snake case keys, dates as strings
    const startResponse = {
      id: 2,
      service_id: 1,
      origin: "frontend",
      user: "deploy",
      started: "2021-11-23T10:03:01.000000",
      finished: null,
    };
    const client = {
      async post<T = unknown>(): Promise<T> {
        return startResponse as any;
      },
      options: { headers: {} },
    } as any;

    const started = (await deploymentsStore.startDeployment("fastdeploy", client))!;

    expect(started).toStrictEqual(pythonToJavascript(startResponse));
    expect(started.serviceId).toBe(1);
    expect(started.started).toBeInstanceOf(Date);
    expect("service_id" in started).toBe(false);
    expect(Object.keys(deploymentsStore.getDeploymentsByService(1))).toStrictEqual(["2"]);
    expect(Object.keys(deploymentsStore.getActiveDeploymentsByService(1))).toStrictEqual(["2"]);
    expect(deploymentsStore.getDeploymentsByService(2)).toStrictEqual({});
  });

  it("keeps a newer websocket state when the start response arrives late", async () => {
    const servicesStore = useServices();
    const deploymentsStore = useDeployments();
    const websocketClient = createWebsocketClient();
    websocketClient.registerStore(deploymentsStore);
    servicesStore.fetchServiceToken = vi.fn().mockResolvedValue("service-token");
    let respond!: (value: any) => void;
    const client = {
      post: () => new Promise<any>((resolve) => (respond = resolve)),
      options: { headers: {} },
    } as any;
    const starting = deploymentsStore.startDeployment("fastdeploy", client);
    await Promise.resolve();
    await Promise.resolve();

    // the deployment finishes (seen over the websocket) before the
    // response of the request that started it has arrived
    const finishedMessage = {
      id: 2,
      service_id: 1,
      origin: "frontend",
      user: "deploy",
      started: "2021-11-23T10:03:01.000000",
      finished: "2021-11-23T10:03:05.000000",
      type: "deployment",
    };
    websocketClient.onMessage(createEvent(finishedMessage));
    respond({ ...finishedMessage, finished: null, type: undefined });
    const started = (await starting)!;

    expect(deploymentsStore.deployments[2].finished).toBeInstanceOf(Date);
    expect(started.finished).toBeInstanceOf(Date);
    expect(deploymentsStore.getActiveDeploymentsByService(1)).toStrictEqual({});
    expect(Object.keys(deploymentsStore.getDeploymentsByService(1))).toStrictEqual(["2"]);
  });

  it("uses the service token only on the client of the start request", async () => {
    const servicesStore = useServices();
    const deploymentsStore = useDeployments();
    servicesStore.fetchServiceToken = vi.fn(async () => "service-token");
    const seen: string[] = [];
    const client = {
      async post() {
        seen.push(client.options.headers.Authorization);
        return { id: 3, service_id: 1 };
      },
      options: { headers: {} as any },
    } as any;

    await deploymentsStore.startDeployment("fastdeploy", client);

    expect(seen).toStrictEqual(["Bearer service-token"]);
    expect(deploymentsStore.client).not.toBe(client);
    expect(JSON.stringify(deploymentsStore.client.options)).not.toContain("service-token");
    expect(JSON.stringify(servicesStore.client.options)).not.toContain("service-token");
  });

  it("shows the issuance refusal and never starts a run with a missing token", async () => {
    const servicesStore = useServices();
    const deploymentsStore = useDeployments();
    servicesStore.client = {
      post: vi.fn().mockRejectedValue({
        message: "Forbidden",
        body: { detail: "Service token issuance requires an administrator" },
      }),
      options: { headers: {} },
    } as any;
    const client = { post: vi.fn(), options: { headers: {} } } as any;
    const started = await deploymentsStore.startDeployment("fastdeploy", client);
    expect(started).toBeNull();
    expect(client.post).not.toHaveBeenCalled();
    expect(client.options.headers.Authorization).toBeUndefined();
    expect(deploymentsStore.deployments).toStrictEqual({});
    const wrapper = mount(ServiceList, {
      global: { stubs: { "router-link": true, "progress-count": true } },
    });
    expect(wrapper.find('[role="alert"]').text()).toContain(
      "Service token issuance requires an administrator"
    );
    wrapper.unmount();
  });

  it("fetches the list of deployments", async () => {
    const deploymentsStore = useDeployments();
    deploymentsStore.client = {
      async get<T = unknown>(url: string | number): Promise<T> {
        return new Promise<any>((resolve) => {
          resolve([apiDeployment]);
        });
      },
      options: { headers: {} },
    } as any;
    await deploymentsStore.fetchDeployments();
    expect(deploymentsStore.deployments[deployment.id]).toStrictEqual(
      deployment
    );
  });
});
