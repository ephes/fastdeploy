import { getActivePinia } from 'pinia';
import { vi } from 'vitest';
import { initPinia } from './conftest';
import { useAuth } from '../src/stores/auth';
import { useSettings } from '../src/stores/config';
import { useServices } from '../src/stores/service';
import { getClient } from '../src/stores/httpClient';

const A = 'https://api-a.example';
const B = 'https://api-b.example';

beforeEach(() => { initPinia(); useSettings().developmentApi = A; });
afterEach(() => { vi.unstubAllGlobals(); });

async function login() {
  const auth = useAuth();
  auth.username = 'synthetic';
  auth.password = 'invented-password';
  auth.onLoginSuccess = vi.fn();
  auth.client.post = vi.fn().mockResolvedValue({ access_token: 'token-for-a' });
  await auth.login();
  return auth;
}

it('retires credentials, cached clients, sockets and stores on an API change', async () => {
  const auth = await login();
  const cached = getClient();
  const dispose = vi.fn();
  auth.websocketClient = { dispose } as any;
  const fetch = vi.fn().mockResolvedValue(new Response('{}'));
  vi.stubGlobal('fetch', fetch);
  useSettings().developmentApi = B;
  expect(auth.accessToken).toBeNull();
  expect(dispose).toHaveBeenCalledOnce();
  expect(getClient().options.headers.Authorization).toBeUndefined();
  await expect(cached.get('/services/')).rejects.toThrow();
  expect(fetch).not.toHaveBeenCalled();
});

it.each([
  ['developmentApi', B, true],
  ['developmentApi', B, false],
  ['developmentWebsocket', 'wss://other.example/deployments/ws', true],
  ['developmentWebsocket', 'wss://other.example/deployments/ws', false],
] as const)('rejects a late login completion after %s changes to %s (success %s)', async (setting, destination, success) => {
  const auth = useAuth();
  let settle!: (value: any) => void;
  auth.client.post = vi.fn().mockReturnValue(new Promise((resolve, reject) => { settle = success ? resolve : reject; }));
  auth.username = 'synthetic'; auth.password = 'invented-password';
  auth.onLoginSuccess = vi.fn();
  const pending = auth.login();
  const settings = useSettings();
  const original = settings[setting];
  settings[setting] = destination;
  settings[setting] = original;
  settle(success ? { access_token: 'stale-a' } : { response: { status: 401 } });
  await pending;
  expect(auth.accessToken).toBeNull();
  expect(auth.errorMessage).toBeNull();
  expect(auth.onLoginSuccess).not.toHaveBeenCalled();
});

it('does not install a late A service snapshot into B stores', async () => {
  await login();
  const services = useServices();
  let resolve!: (value: any) => void;
  services.client.get = vi.fn().mockReturnValue(new Promise(yes => { resolve = yes; }));
  const pending = services.fetchServices();
  useSettings().developmentApi = B;
  resolve([{ id: 1, name: 'from-a', data: {} }]);
  await pending;
  expect(services.services).toEqual({});
});

it('uses the new API for the next login form after settings change', async () => {
  const auth = useAuth();
  useSettings().developmentApi = B;
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: 'token-for-b' })));
  vi.stubGlobal('fetch', fetch);
  auth.onLoginSuccess = vi.fn();
  auth.username = 'synthetic'; auth.password = 'invented-password';
  await auth.login();
  expect(fetch.mock.calls[0][0]).toBe(`${B}/token`);
  expect(auth.accessToken).toBe('token-for-b');
});

it.each([0, 2])('retires only the recreated auth store after %i resets', (resets) => {
  const pinia = getActivePinia()!;
  const settings = useSettings(pinia);
  const original = useAuth(pinia);
  const beforeDisposal = original.sessionId;
  original.$dispose();
  settings.developmentApi = B;
  expect(original.sessionId).toBe(beforeDisposal);

  // Pinia keeps the state entry on disposal.
  const current = useAuth(pinia);
  for (let count = 0; count < resets; count++) current.$reset();
  current.accessToken = 'current-token';
  const beforeChange = current.sessionId;
  initPinia();
  const unrelated = useAuth();
  settings.developmentApi = A;
  expect(current.sessionId).toBe(beforeChange + 1);
  expect(current.accessToken).toBeNull();
  expect(unrelated.sessionId).toBe(0);
});
