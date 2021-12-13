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
      pythonToJavascript({...deployment, created: new Date("2021-11-23T09:03:01.000000Z")})
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
    servicesStore.fetchServiceToken = jest.fn();
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
