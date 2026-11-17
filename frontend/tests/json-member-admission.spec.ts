import { vi } from 'vitest';
import { initPinia } from './conftest';
import { useAuth } from '../src/stores/auth';
import { useServices } from '../src/stores/service';
import { useDeployments } from '../src/stores/deployment';
import { useSteps } from '../src/stores/step';
import { useWebsocketStore } from '../src/stores/websocket';
import { createWebsocketClient } from '../src/websocket';

const service = { type: 'service', id: 2, name: 'synthetic', data: {} };
const deployment = { type: 'deployment', id: 2, service_id: 1, origin: 'fixture', user: 'synthetic', started: '2026-11-01T00:00:00Z', finished: null };
const step = { type: 'step', id: 2, deployment_id: 1, name: 'synthetic', state: 'running', message: '', started: null, finished: null };
// Keep the raw spelling: JSON.stringify alone cannot represent duplicate members.
const cases = [
  ...[false, true].flatMap(reverse => [
    { kind: 'service', raw: `{"type":"service","id":${reverse ? 3 : 2},"\\u0069d":${reverse ? 2 : 3},"name":"synthetic","data":{}}` },
    { kind: 'service', raw: `{"type":"service","id":2,"name":"synthetic","data":{},"deleted":${reverse},"deleted":${!reverse}}` },
    { kind: 'deployment', raw: JSON.stringify(deployment).replace('"service_id":1', `"service_id":${reverse ? 2 : 1},"service_id":${reverse ? 1 : 2}`) },
    { kind: 'step', raw: JSON.stringify(step).replace('"state":"running"', `"state":"${reverse ? 'success' : 'running'}","st\\u0061te":"${reverse ? 'running' : 'success'}"`) },
    { kind: 'service', raw: JSON.stringify(service).replace('"data":{}', `"data":{"items":[{"key":${reverse ? 2 : 1},"k\\u0065y":${reverse ? 1 : 2}}]}`) },
  ]),
];

beforeEach(() => {
  initPinia();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function businessState() {
  return JSON.stringify([useServices().services, useDeployments().deployments, useSteps().steps,
    useSteps().stepsByDeployment, useSteps().stepsInProgressByDeployment]);
}
function seed() {
  useServices().services = { 1: { id: 1, name: 'kept', data: {} } };
  useDeployments().deployments = { 1: { id: 1, serviceId: 1 } } as any;
  useSteps().addStep({ id: 1, deploymentId: 1, name: 'kept', state: 'running', message: '', started: null, finished: null });
}

it.each(cases)('retains REST business state for duplicate members: $raw', async ({ kind, raw }) => {
  seed();
  const before = businessState();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(`[${raw}]`)));
  if (kind === 'service') {
    await useServices().fetchServices();
    expect(useServices().servicesError).not.toBe('');
  } else if (kind === 'deployment') {
    await useDeployments().fetchDeployments();
    expect(useDeployments().historyError).not.toBe('');
  } else {
    await expect(useSteps().fetchStepsFromDeployment(1)).rejects.toThrow();
  }
  expect(businessState()).toBe(before);
});

it.each(cases)('retires websocket on duplicate members without publishing: $raw', ({ raw }) => {
  seed();
  const before = businessState();
  const client = createWebsocketClient();
  for (const store of [useServices(), useDeployments(), useSteps()]) client.registerStore(store);
  const connection = { close: vi.fn(), onopen: vi.fn(), onclose: vi.fn(), onmessage: vi.fn() };
  client.connection = connection as any;
  const logout = vi.spyOn(useAuth(), 'logout');
  client.onMessage({ data: raw } as MessageEvent);
  expect(businessState()).toBe(before);
  expect(connection.close).toHaveBeenCalledOnce();
  expect(connection.onmessage).toBeNull();
  expect(useWebsocketStore().protocolError).toContain('Invalid websocket message');
  expect(logout).not.toHaveBeenCalled();
});

it.each([['first', 'second'], ['second', 'first']])('cannot log in with duplicate token members: %s, %s', async (first, second) => {
  const auth = useAuth();
  auth.username = 'synthetic'; auth.password = 'synthetic';
  const success = vi.spyOn(auth, 'onLoginSuccess').mockResolvedValue();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(`{"access_token":"${first}","access_\\u0074oken":"${second}"}`)));
  await auth.login();
  expect(auth.isAuthenticated).toBe(false);
  expect(success).not.toHaveBeenCalled();
});

it.each([['failure', 'success'], ['success', 'failure']])('cannot authenticate or log out with duplicate websocket status: %s, %s', (first, second) => {
  const logout = vi.spyOn(useAuth(), 'logout').mockImplementation(() => {});
  createWebsocketClient().onMessage({ data: `{"type":"authentication","status":"${first}","st\\u0061tus":"${second}"}` } as MessageEvent);
  expect(useWebsocketStore().authentication).toBe('not authenticated');
  expect(useWebsocketStore().protocolError).toContain('Invalid websocket message');
  expect(logout).not.toHaveBeenCalled();
});
