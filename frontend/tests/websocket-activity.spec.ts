import { vi } from 'vitest';
import { initPinia } from './conftest';
import { useWebsocketStore } from '../src/stores/websocket';
import { useAuth } from '../src/stores/auth';

beforeEach(() => { vi.useFakeTimers(); initPinia(); });
afterEach(() => { useWebsocketStore().$reset(); vi.useRealTimers(); });

it('keeps activity for a full second after the latest message', async () => {
  const store = useWebsocketStore();
  void store.receivedMessage();
  await vi.advanceTimersByTimeAsync(900);
  void store.receivedMessage();
  await vi.advanceTimersByTimeAsync(100);
  expect(store.recentlyReceivedMessage).toBe(true);
  await vi.advanceTimersByTimeAsync(899);
  expect(store.recentlyReceivedMessage).toBe(true);
  await vi.advanceTimersByTimeAsync(1);
  expect(store.recentlyReceivedMessage).toBe(false);
});

it('owns one timer for a burst and retires it on reset and logout', async () => {
  const store = useWebsocketStore();
  for (let i = 0; i < 1000; i++) void store.receivedMessage();
  expect(vi.getTimerCount()).toBe(1);
  store.$reset();
  const resetTimestamp = store.lastMessageReceived;
  expect(vi.getTimerCount()).toBe(0);
  await vi.advanceTimersByTimeAsync(1000);
  expect(store.lastMessageReceived).toBe(resetTimestamp);
  void store.receivedMessage();
  useAuth().endSession();
  expect(vi.getTimerCount()).toBe(0);
  expect(store.recentlyReceivedMessage).toBe(false);
});
