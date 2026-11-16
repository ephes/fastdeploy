import { initPinia } from './conftest';
import { useDeployments } from '../src/stores/deployment';
import { useSteps } from '../src/stores/step';

const deployment = (id: number, finished: Date | null = new Date()) => ({
  id, type: 'deployment', serviceId: id, origin: 'fixture', user: 'fixture', started: new Date(), finished,
} as any);
const step = (id: number, deploymentId = id) => ({
  id, deploymentId, type: 'step', name: 'fixture', message: '', state: 'success', started: new Date(), finished: new Date(),
} as any);
const wire = (id: number) => ({ id, service_id: id, type: 'deployment', origin: 'fixture', user: 'fixture', started: '2026-11-01T00:00:00Z', finished: '2026-11-01T00:01:00Z' });

beforeEach(() => initPinia());

it('bounds visited inactive histories and their step indexes and tombstones', async () => {
  const deployments = useDeployments();
  const steps = useSteps();
  for (let id = 1; id <= 500; id++) {
    deployments.client = { get: async () => [wire(id)] } as any;
    await deployments.fetchDeployments(id);
    steps.onMessage(step(id));
    steps.onMessage({ ...step(id), deleted: true });
    steps.onMessage(deployment(id));
  }
  expect(Object.keys(deployments.deployments).length).toBeLessThanOrEqual(101);
  expect(Object.keys(steps.finishedDeployments).length).toBeLessThanOrEqual(101);
  expect(Object.keys(steps.deletedSteps).length).toBeLessThanOrEqual(101);
  expect(Object.keys(steps.stepsByDeployment).length).toBeLessThanOrEqual(101);
  steps.onMessage(step(1));
  deployments.onMessage(deployment(1));
  expect(steps.steps[1]).toBeUndefined();
  expect(deployments.deployments[1]).toBeUndefined();
  steps.client = { get: async () => [] } as any;
  await steps.fetchStepsFromDeployment(1);
  expect(steps.inventoryComplete[1]).toBe(true);
});

it('bounds standalone finished/delete event histories', () => {
  const steps = useSteps();
  for (let id = 1; id <= 500; id++) {
    steps.onMessage({ ...step(id), deleted: true });
    steps.onMessage(deployment(id));
  }
  expect(Object.keys(steps.deletedSteps).length).toBeLessThanOrEqual(100);
  expect(Object.keys(steps.finishedDeployments).length).toBeLessThanOrEqual(100);
  steps.onMessage(step(1));
  expect(steps.steps[1]).toBeUndefined();
});

it('pins active and displayed detail state while evicting inactive histories', () => {
  const deployments = useDeployments();
  const steps = useSteps();
  deployments.onMessage(deployment(1, null));
  deployments.displayedDeploymentId = 2;
  deployments.onMessage(deployment(2));
  steps.onMessage(step(1));
  steps.onMessage({ ...step(2), deleted: true });
  for (let id = 3; id <= 500; id++) {
    deployments.onMessage(deployment(id));
    steps.onMessage(step(id));
    steps.onMessage(deployment(id));
  }
  expect(deployments.deployments[1]).toBeDefined();
  expect(deployments.deployments[2]).toBeDefined();
  expect(steps.steps[1]).toBeDefined();
  steps.onMessage(step(2));
  expect(steps.steps[2]).toBeUndefined();
});

it('refuses further history pages at the display budget before HTTP work', async () => {
  const store = useDeployments();
  let next = 500;
  const get = vi.fn(async () => Array.from({ length: 50 }, () => wire(next--)));
  store.client = { get } as any;
  await store.fetchDeployments();
  for (let n = 0; n < 5; n++) await store.fetchDeployments(undefined, true);
  expect(store.historyIds).toHaveLength(200);
  expect(get).toHaveBeenCalledTimes(4);
  expect(store.historyError).toContain('limit');
});

it('counts progress without invoking detail sorting or allocating entry arrays', () => {
  const deployments = useDeployments();
  const steps = useSteps();
  deployments.onMessage(deployment(1, null));
  for (let id = 1; id <= 2000; id++) steps.addStep({ ...step(id, 1), finished: id % 2 ? null : new Date() });
  const sorted = vi.spyOn(Array.prototype, 'sort');
  const values = vi.spyOn(Object, 'values');
  const entries = vi.spyOn(Object, 'entries');
  try {
    for (let n = 0; n < 10; n++) expect(deployments.getFinishedVsAllSteps(1)).toEqual([1000, 2000]);
    expect(sorted).not.toHaveBeenCalled();
    expect(values).not.toHaveBeenCalled();
    expect(entries).not.toHaveBeenCalled();
  } finally { vi.restoreAllMocks(); }
});

it('bounds tombstones within an inactive history and fences late events after reopening', async () => {
  const store = useSteps();
  for (let id = 1; id <= 1100; id++) store.onMessage({ ...step(id, 1), deleted: true });
  expect(Object.keys(store.deletedSteps).length).toBeLessThanOrEqual(1000);
  store.client = { get: async () => [] } as any;
  await store.fetchStepsFromDeployment(1);
  store.onMessage(step(1, 1));
  expect(store.steps[1]).toBeUndefined();
});

it('bounds unpinned step rows even without a deployment finish event', () => {
  const store = useSteps();
  for (let id = 1; id <= 1100; id++) store.onMessage(step(id, 1));
  expect(Object.keys(store.steps).length).toBeLessThanOrEqual(1000);
  expect(store.inventoryComplete[1]).not.toBe(true);
  store.onMessage(step(1, 1));
  expect(store.steps[1]).toBeUndefined();
});

it('keeps admitting previously unseen steps for a pinned live deployment', () => {
  const deployments = useDeployments();
  const steps = useSteps();
  deployments.onMessage(deployment(1, null));
  steps.onMessage(step(10, 1));
  steps.onMessage(step(2000, 2));
  steps.evictDeployment(2);
  steps.onMessage(step(11, 1));
  expect(steps.steps[11]).toBeDefined();
});
