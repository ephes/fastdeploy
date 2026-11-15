import { vi } from 'vitest';
import { initPinia, createEvent } from './conftest';
import { createWebsocketClient } from '../src/websocket';
import { useDeployments } from '../src/stores/deployment';
import { useServices } from '../src/stores/service';
const row = (id: number) => ({ id, service_id: 1, origin: 'frontend', user: 'synthetic', started: '2026-11-01T00:00:00Z', finished: null });
beforeEach(() => initPinia());
it.each([
  [row(4), null], [row(4), row(4)], [row(4), { ...row(3), service_id: 2 }],
  [row(3), row(4)], [row(4), { ...row(3), finished: 'bad-date' }],
  Array.from({ length: 51 }, (_, i) => row(100 - i)),
].map(response => ({ response })))('retains last-good history on an invalid refresh: %j', async ({ response }) => {
  const store = useDeployments();
  store.client = { get: vi.fn().mockResolvedValue([row(8)]) } as any;
  await store.fetchDeployments(1);
  const before = JSON.stringify([store.deployments, store.historyIds, store.historyBeforeId, store.historyHasMore]);
  store.client = { get: vi.fn().mockResolvedValue(response) } as any;
  await store.fetchDeployments(1);
  expect(JSON.stringify([store.deployments, store.historyIds, store.historyBeforeId, store.historyHasMore])).toBe(before);
  expect(store.historyError).toContain('Try again');
});
it('rejects load-more rows at or above the requested cursor', async () => {
  const store = useDeployments();
  store.historyBeforeId = 5; store.historyServiceId = 1;
  store.client = { get: vi.fn().mockResolvedValue([row(5)]) } as any;
  await store.fetchDeployments(1, true);
  expect(store.deployments).toEqual({});
  expect(store.historyBeforeId).toBe(5);
  expect(store.historyError).toContain('Try again');
});
it.each([{ service_id: 2 }, { id: 0 }, { started: 'bad-date' }, { finished: false }])('refuses ambiguous launch result: %j', async invalid => {
  const services = useServices(), store = useDeployments();
  services.services = { 1: { id: 1, name: 'synthetic', data: {} } };
  services.fetchServiceToken = vi.fn().mockResolvedValue('synthetic-token');
  const client = { options: { headers: {} }, post: vi.fn().mockResolvedValue({ ...row(9), ...invalid }) } as any;
  await expect(store.startDeployment('synthetic', client)).rejects.toThrow(/Refresh.*retry/i);
  expect(store.deployments).toEqual({});
});
it('keeps completion when a delayed start event arrives, then agrees with REST', async () => {
  const store = useDeployments();
  const finished = { ...row(9), type: 'deployment', serviceId: 1, started: new Date(row(9).started), finished: new Date('2026-11-01T00:00:05Z') };
  const client = createWebsocketClient(); client.registerStore(store);
  client.onMessage(createEvent({ ...row(9), type: 'deployment', finished: finished.finished.toISOString() }));
  client.onMessage(createEvent({ ...row(9), type: 'deployment' }));
  expect(store.deployments[9].finished).toEqual(finished.finished);
  store.client = { get: vi.fn().mockResolvedValue([{ ...row(9), finished: finished.finished.toISOString() }]) } as any;
  await store.fetchDeployments(1);
  expect(store.deployments[9].finished).toEqual(finished.finished);
  store.onMessage({ ...finished, deleted: true } as any);
  expect(store.deployments[9]).toBeUndefined();
});
