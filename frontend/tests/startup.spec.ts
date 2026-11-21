const { createApp } = vi.hoisted(() => ({ createApp: vi.fn() }));
vi.mock('vue', async importOriginal => {
  const vue = await importOriginal<typeof import('vue')>();
  return { ...vue, createApp: createApp.mockImplementation(vue.createApp) };
});
vi.mock('../src/App.vue', () => ({ default: { render: () => 'Mounted' } }));
vi.mock('../src/routes', () => ({
  routes: [{ path: '/', name: 'login', component: { render: () => null } }],
}));
const api = 'https://staging.example.test/platform/api';
const websocket = 'wss://staging.example.test/deployments/ws';

beforeEach(() => {
  vi.resetModules();
  createApp.mockClear();
  document.body.innerHTML = '<div id="app"></div>';
  vi.stubEnv('MODE', 'production');
  vi.stubEnv('PROD', true);
  vi.stubEnv('VITE_API_BASE_PROD', api);
  vi.stubEnv('VITE_WEBSOCKET_URL_PROD', websocket);
});

afterEach(() => vi.unstubAllEnvs());

it.each(['VITE_API_BASE_PROD', 'VITE_WEBSOCKET_URL_PROD'])(
  'stops startup before app creation when %s is missing',
  async key => {
    vi.stubEnv(key, undefined);
    await expect(import('../src/main')).rejects.toThrow(
      `Missing frontend production configuration: ${key}`,
    );
    expect(createApp).not.toHaveBeenCalled();
  },
);

it.each([
  ['VITE_API_BASE_PROD', 'wss://example.test/api'],
  ['VITE_WEBSOCKET_URL_PROD', 'https://example.test/ws'],
  ['VITE_API_BASE_PROD', '/api'],
  ['VITE_WEBSOCKET_URL_PROD', 'wss://[broken'],
  ['VITE_API_BASE_PROD', 'https:example.test/api'],
  ['VITE_API_BASE_PROD', 'https://user@example.test/api'],
  ['VITE_API_BASE_PROD', 'https://example.test/api?query=1'],
  ['VITE_WEBSOCKET_URL_PROD', 'wss://example.test/ws#fragment'],
])('stops startup before app creation for invalid %s (%s)', async (key, invalid) => {
  vi.stubEnv(key, invalid);
  await expect(import('../src/main')).rejects.toThrow(
    `Invalid frontend production configuration: ${key}`,
  );
  expect(createApp).not.toHaveBeenCalled();
});

it.each([
  ['production', true, api, websocket],
  ['staging', true, api, websocket],
  ['development', false, 'http://localhost:8000', 'ws://localhost:8000/deployments/ws'],
])('starts in %s mode with the expected endpoints', async (mode, prod, expectedApi, expectedWebsocket) => {
  vi.stubEnv('MODE', mode);
  vi.stubEnv('PROD', prod);
  vi.stubEnv('VITE_API_BASE_DEV', undefined);
  vi.stubEnv('VITE_WEBSOCKET_URL_DEV', undefined);
  await import('../src/main');
  const { useSettings } = await import('../src/stores/config');
  expect(useSettings().api).toBe(expectedApi);
  expect(useSettings().websocket).toBe(expectedWebsocket);
  expect(document.querySelector('#app')?.textContent).toBe('Mounted');
});
