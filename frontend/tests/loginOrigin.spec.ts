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

it.each([true, false])('rejects a late login completion after API changes (success %s)', async success => {
  const auth = useAuth();
  let settle!: (value: any) => void;
  auth.client.post = vi.fn().mockReturnValue(new Promise((resolve, reject) => { settle = success ? resolve : reject; }));
  auth.username = 'synthetic'; auth.password = 'invented-password';
  auth.onLoginSuccess = vi.fn();
  const pending = auth.login();
  useSettings().developmentApi = B;
  useSettings().developmentApi = A;
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
