import { vi } from 'vitest';
import { initPinia } from './conftest';
import { useSteps } from '../src/stores/step';
import { useServices } from '../src/stores/service';

const step = (id: number) => ({ id, deployment_id: 1, name: `step-${id}`, state: 'running', message: '', started: null, finished: null });
const service = (id: number) => ({ id, name: `service-${id}`, data: {} });
beforeEach(() => initPinia());

it.each([
  null, {}, [step(4), null], [step(4), { ...step(5), state: 'unknown' }],
  [step(4), step(4)], [step(4), { ...step(5), deployment_id: 2 }],
  [step(4), { ...step(5), id: '__proto__' }], [step(4), { ...step(5), id: Number.MAX_SAFE_INTEGER + 1 }],
  [step(4), { ...step(5), started: 'not-a-date' }], [step(4), { ...step(5), finished: 42 }],
  [step(4), { ...step(5), message: null }], [step(4), { ...step(5), name: null }],
  [step(4), { id: 5, deployment_id: 1 }], [step(4), { ...step(5), deleted: 'yes' }],
  [step(4), { ...step(5), deleted: null }],
])('rejects an entire malformed step snapshot without changing any index: %j', async response => {
  const store = useSteps();
  store.addStep({ id: 1, deploymentId: 1, name: 'old', state: 'running', message: '', started: null, finished: null });
  store.addStep({ id: 9, deploymentId: 2, name: 'other', state: 'running', message: '', started: null, finished: null });
  const maps = [store.steps, store.stepsByDeployment, store.stepsInProgressByDeployment];
  const before = JSON.stringify(maps);
  store.client = { get: vi.fn().mockResolvedValue(response) } as any;
  await expect(store.fetchStepsFromDeployment(1)).rejects.toThrow();
  expect(JSON.stringify([store.steps, store.stepsByDeployment, store.stepsInProgressByDeployment])).toBe(before);
  expect(store.steps).toBe(maps[0]);
  expect(store.pendingFetches).toEqual([]);
});

it('normalizes only declared step fields, including hostile object-method keys', async () => {
  const store = useSteps();
  const wire = JSON.parse(JSON.stringify({ ...step(4), started: '2026-11-01T00:00:00Z', hasOwnProperty: 'hostile', constructor: 'hostile', deploymentId: 999, __proto__: null }));
  Object.defineProperty(wire, '__proto__', { value: { polluted: true }, enumerable: true });
  store.client = { get: vi.fn().mockResolvedValue([wire]) } as any;
  await store.fetchStepsFromDeployment(1);
  expect(store.steps[4].deploymentId).toBe(1);
  expect(store.steps[4].started).toEqual(new Date(wire.started));
  expect(Object.hasOwn(store.steps[4], 'hasOwnProperty')).toBe(false);
  expect(Object.hasOwn(store.steps[4], '__proto__')).toBe(false);
  expect(store.stepsInProgressByDeployment[1]).toEqual([store.steps[4]]);
});

it.each([
  null, {}, [service(2), null], [service(2), service(2)],
  [service(2), { ...service(3), id: '__proto__' }], [service(2), { ...service(3), id: 0 }],
  [service(2), { ...service(3), id: 1.5 }], [service(2), { ...service(3), id: Number.MAX_SAFE_INTEGER + 1 }],
  [service(2), { ...service(3), name: 7 }], [service(2), { ...service(3), data: [] }],
  [service(2), { ...service(3), data: null }], [service(2), { id: 3, name: 'missing-data' }],
  [service(2), { ...service(3), deleted: 1 }],
])('retains services and deletion feedback after invalid REST response: %j', async response => {
  const store = useServices(); store.services = { 1: service(1) }; store.deleteErrors[1] = 'keep';
  const before = store.services;
  store.client = { get: vi.fn().mockResolvedValue(response) } as any;
  await store.fetchServices();
  expect(store.services).toBe(before);
  expect(store.deleteErrors).toEqual({ 1: 'keep' });
  expect(store.servicesError).toContain('Could not load');
  expect(store.servicesError.length).toBeLessThan(150);
  expect(store.servicesLoading).toBe(false);
  expect(store.pendingFetches).toEqual([]);
});

it.each([null, {}, [null], ['valid', 7], ['valid', {}], ['duplicate', 'duplicate']])('retains available names after invalid response: %j', async response => {
  const store = useServices(); store.serviceNames = ['old'];
  store.client = { get: vi.fn().mockResolvedValue(response) } as any;
  await store.fetchServiceNames();
  expect(store.serviceNames).toEqual(['old']);
  expect(store.serviceNamesError).toContain('Could not load service names');
  expect(store.serviceNamesLoading).toBe(false);
});

it('refuses a step id already cached under another deployment before pruning', async () => {
  const store = useSteps();
  store.addStep({ id: 1, deploymentId: 1, name: 'old', state: 'running', message: '', started: null, finished: null });
  store.addStep({ id: 9, deploymentId: 2, name: 'other', state: 'running', message: '', started: null, finished: null });
  const before = JSON.stringify([store.steps, store.stepsByDeployment, store.stepsInProgressByDeployment]);
  store.client = { get: vi.fn().mockResolvedValue([step(4), step(9)]) } as any;
  await expect(store.fetchStepsFromDeployment(1)).rejects.toThrow('Invalid REST snapshot');
  expect(JSON.stringify([store.steps, store.stepsByDeployment, store.stepsInProgressByDeployment])).toBe(before);
});

it('admits an empty step snapshot and removes only the requested deployment', async () => {
  const store = useSteps();
  store.addStep({ id: 1, deploymentId: 1, name: 'old', state: 'running', message: '', started: null, finished: null });
  store.addStep({ id: 9, deploymentId: 2, name: 'other', state: 'running', message: '', started: null, finished: null });
  store.client = { get: vi.fn().mockResolvedValue([]) } as any;
  await store.fetchStepsFromDeployment(1);
  expect(Object.keys(store.steps)).toEqual(['9']);
  expect(store.stepsByDeployment[1]).toEqual({});
  expect(store.stepsInProgressByDeployment[1]).toEqual([]);
  expect(store.stepsInProgressByDeployment[2].map(row => row.id)).toEqual([9]);
});

it('admits boolean deletion flags in REST snapshots like websocket messages', async () => {
  const steps = useSteps();
  steps.client = { get: vi.fn().mockResolvedValue([{ ...step(4), deleted: false }]) } as any;
  await steps.fetchStepsFromDeployment(1);
  expect(steps.steps[4].deleted).toBe(false);
  const services = useServices();
  services.client = { get: vi.fn().mockResolvedValue([{ ...service(2), deleted: false }]) } as any;
  await services.fetchServices();
  expect(services.services[2].deleted).toBe(false);
  expect(services.servicesError).toBe('');
});
