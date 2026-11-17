import { vi } from 'vitest';
import { initPinia, createEvent } from './conftest';
import { isWireDate } from '../src/wireValues';
import { useDeployments } from '../src/stores/deployment';
import { useWebsocketStore } from '../src/stores/websocket';
import { createWebsocketClient } from '../src/websocket';

const invalid = [
  '2026-02-30T12:00:00Z', '2026-04-31T12:00:00Z', '2026-02-29T12:00:00Z',
  '1900-02-29T12:00:00Z', '2024-02-30T12:00:00+02:00',
  '2026-01-00T12:00:00Z', '2026-13-01T12:00:00Z',
  '2026-11-01T24:00:00Z', '2026-11-01T12:60:00Z', '2026-11-01T12:00:60Z',
  '2026-11-01T12:00:00+24:00', '2026-11-01T12:00:00+01:60',
  '2026-02-30T12:00:00', '2026-04-31T12:00:00.123456-0530',
];
const valid = [
  '2024-02-29T12:00:00Z', '2000-02-29T12:00:00Z', '2026-04-30T23:59:59Z',
  '2026-11-01T12:00:00.123456Z', '2026-11-01T12:00:00+05:30',
  '2026-11-01T12:00:00.123456-0530', '2026-11-01T12:00:00',
  '2026-11-01T12:00:00.123456', '2026-11-01T12:00', '2026-11-01T12:00Z',
  '2026-01-01T00:15:00+01:00', '2026-12-31T23:45:00-01:00',
];
const row = (id: number) => ({ id, service_id: 1, origin: 'fixture', user: 'synthetic', started: valid[0], finished: null });

beforeEach(() => {
  initPinia();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it.each(invalid)('refuses impossible calendar/time components: %s', value => {
  expect(isWireDate(value)).toBe(false);
});

it.each(invalid.flatMap(value => ['started', 'finished'].map(field => ({ value, field }))))(
  'retains the complete REST snapshot and retires websocket for $field=$value', async ({ value, field }) => {
    const store = useDeployments();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify([row(9)])))
      .mockResolvedValueOnce(new Response(JSON.stringify([row(8), { ...row(7), [field]: value }]))));
    await store.fetchDeployments();
    const before = JSON.stringify([store.deployments, store.historyIds, store.historyBeforeId, store.historyHasMore]);
    await store.fetchDeployments();
    expect(JSON.stringify([store.deployments, store.historyIds, store.historyBeforeId, store.historyHasMore])).toBe(before);
    expect(store.historyError).not.toBe('');
    const client = createWebsocketClient(); client.registerStore(store);
    const close = vi.fn(); client.connection = { close } as any;
    client.onMessage(createEvent({ ...row(8), type: 'deployment', [field]: value }));
    expect(JSON.stringify([store.deployments, store.historyIds, store.historyBeforeId, store.historyHasMore])).toBe(before);
    expect(close).toHaveBeenCalledOnce();
    expect(useWebsocketStore().protocolError).toContain('Invalid websocket message');
  },
);

it.each(valid)('preserves REST/websocket conversion of supported timestamps: %s', async value => {
  expect(isWireDate(value)).toBe(true);
  const store = useDeployments();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([{ ...row(9), started: value, finished: value }]))));
  await store.fetchDeployments();
  expect(store.historyError).toBe('');
  expect(store.deployments[9].started).toEqual(new Date(value));
  expect(store.deployments[9].finished).toEqual(new Date(value));
  const client = createWebsocketClient(); client.registerStore(store);
  client.onMessage(createEvent({ ...row(8), type: 'deployment', started: value, finished: value }));
  expect(store.deployments[8].started).toEqual(new Date(value));
  expect(store.deployments[8].finished).toEqual(new Date(value));
  expect(useWebsocketStore().protocolError).toBe('');
});
