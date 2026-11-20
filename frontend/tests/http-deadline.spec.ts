import { vi } from 'vitest';
import { initPinia } from './conftest';
import { getClient, getClientWithoutAuth, type BoundedOptions } from '../src/stores/httpClient';
import { useAuth } from '../src/stores/auth';
import { useServices } from '../src/stores/service';
import { useSteps } from '../src/stores/step';

const deadline = 30_000;
const never = () => new Promise<Response>(() => {});
beforeEach(() => { vi.useFakeTimers(); initPinia(); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('settles service loading and step fences even if fetch ignores abort', async () => {
  const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', vi.fn((_url, options) => { signals.push(options.signal); return never(); }));
  const services = useServices(), steps = useSteps();
  const list = services.fetchServices();
  const stepResult = steps.fetchStepsFromDeployment(1).catch(error => error);
  await vi.advanceTimersByTimeAsync(deadline);
  await list;
  expect((await stepResult).name).toBe('TimeoutError');
  expect(services.servicesLoading).toBe(false);
  expect(services.servicesError).toContain('Could not load');
  expect(services.pendingFetches).toEqual([]);
  expect(steps.pendingFetches).toEqual({});
  expect(signals.every(signal => signal.aborted)).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});

it('includes response body reading in the deadline and never retries a mutation', async () => {
  let signal!: AbortSignal;
  const fetch = vi.fn((_url, options) => {
    signal = options.signal;
    return Promise.resolve(new Response(new ReadableStream({ pull: () => new Promise(() => {}) })));
  });
  vi.stubGlobal('fetch', fetch);
  const result = getClientWithoutAuth().post('/deployments/', { service: 'synthetic' }).catch(error => error);
  await vi.advanceTimersByTimeAsync(deadline);
  expect(await result).toMatchObject({ name: 'TimeoutError' });
  expect(signal.aborted).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it('composes caller abort without changing shared request options', async () => {
  let signal!: AbortSignal;
  vi.stubGlobal('fetch', vi.fn((_url, options) => { signal = options.signal; return never(); }));
  const caller = new AbortController();
  const remove = vi.spyOn(caller.signal, 'removeEventListener');
  const options = { signal: caller.signal };
  const result = getClientWithoutAuth().get('services/', options).catch(error => error);
  caller.abort();
  await vi.advanceTimersByTimeAsync(0);
  expect(await result).toMatchObject({ name: 'AbortError' });
  expect(signal.aborted).toBe(true);
  expect(options.signal).toBe(caller.signal);
  expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
  expect(vi.getTimerCount()).toBe(0);
});

it('does not start a request whose caller already cancelled', async () => {
  const fetch = vi.fn(never); vi.stubGlobal('fetch', fetch);
  const caller = new AbortController(); caller.abort();
  await expect(getClientWithoutAuth().get({ signal: caller.signal })).rejects.toMatchObject({ name: 'AbortError' });
  expect(fetch).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});

it.each(['get', 'delete', 'post', 'put', 'patch'] as const)('cleans deadline/listener on successful %s with base-url options', async method => {
  const fetch = vi.fn().mockResolvedValue(new Response('{}')); vi.stubGlobal('fetch', fetch);
  const caller = new AbortController(), options = { signal: caller.signal };
  const remove = vi.spyOn(caller.signal, 'removeEventListener');
  const client = getClientWithoutAuth();
  if (method === 'get' || method === 'delete') await client[method](options);
  else await client[method]({ name: 'synthetic' }, options);
  expect(fetch.mock.calls[0][1].signal).not.toBe(caller.signal);
  expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
  expect(vi.getTimerCount()).toBe(0);
  caller.abort();
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(false);
});

it('cleans resources on transport rejection', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('transport')));
  const caller = new AbortController(); const remove = vi.spyOn(caller.signal, 'removeEventListener');
  await expect(getClientWithoutAuth().get('services/', { signal: caller.signal })).rejects.toThrow('transport');
  expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
  expect(vi.getTimerCount()).toBe(0);
});

it.each([200, 409])('cancels a response arriving after logout before reading its body (%i)', async status => {
  let respond!: (response: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { respond = resolve; })));
  const cancel = vi.fn();
  const onBodyBytes = vi.fn();
  const options: BoundedOptions<"json"> = { onBodyBytes };
  const pending = getClient().get('services/', options).catch(error => error);
  useAuth().logout();
  respond(new Response(new ReadableStream({
    start(controller) { controller.enqueue(new Uint8Array([123])); },
    cancel,
  }), { status }));

  await vi.advanceTimersByTimeAsync(deadline);
  expect(await pending).toMatchObject({ message: 'API destination or login session changed. Log in again.' });
  expect(cancel).toHaveBeenCalledOnce();
  expect(onBodyBytes).not.toHaveBeenCalled();
});
