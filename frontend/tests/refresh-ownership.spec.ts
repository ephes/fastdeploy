import { vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import { getActivePinia } from 'pinia';
import { initPinia } from './conftest';
import { useServices } from '../src/stores/service';
import { useSteps } from '../src/stores/step';
import { useDeployments } from '../src/stores/deployment';
import { useAuth } from '../src/stores/auth';
import ServiceList from '../src/components/ServiceList.vue';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const service = (id: number, name = `service-${id}`) => ({ id, name, data: {}, type: 'service' as const });
const apiStep = (id: number) => ({ id, deployment_id: 1, name: `step-${id}`, state: 'running', type: 'step', message: '', started: null, finished: null });
beforeEach(() => initPinia());
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('reconciles the service snapshot while preserving intervening add/update/delete events', async () => {
  const store = useServices(); store.services = { 1: service(1), 2: service(2), 3: service(3) };
  const response = deferred<any[]>(); store.client = { get: vi.fn().mockReturnValue(response.promise) } as any;
  const fetch = store.fetchServices();
  store.onMessage({ ...service(2), deleted: true } as any); store.onMessage(service(3, 'updated')); store.onMessage(service(4));
  response.resolve([service(2), service(3), service(5)]); await fetch;
  expect(Object.keys(store.services)).toEqual(['3', '4', '5']); expect(store.services[3].name).toBe('updated');
  await store.fetchServices();
  expect(Object.keys(store.services)).toEqual(['2', '3', '5']);
});
it.each(['success', 'error'])('ignores obsolete service fetch %s and retains latest loading/error ownership', async outcome => {
  const store = useServices(); const old = deferred<any[]>(); const current = deferred<any[]>();
  store.client = { get: vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise) } as any;
  const first = store.fetchServices(); const second = store.fetchServices();
  if (outcome === 'success') old.resolve([service(1)]); else old.reject(new Error('old'));
  await first; expect(store.servicesLoading).toBe(true); expect(store.servicesError).toBe('');
  current.resolve([service(2)]); await second;
  expect(Object.keys(store.services)).toEqual(['2']); expect(store.servicesLoading).toBe(false);
});
it('does not resurrect a confirmed local deletion during refresh', async () => {
  const store = useServices(); store.services[1] = service(1); const response = deferred<any[]>();
  store.client = { get: vi.fn().mockReturnValue(response.promise), delete: vi.fn().mockResolvedValue({}) } as any;
  const fetch = store.fetchServices(); await store.deleteService(1); response.resolve([service(1)]); await fetch;
  expect(store.services[1]).toBeUndefined();
});
it('retains service rows on failed refresh and ignores a former session', async () => {
  const store = useServices(); store.services[1] = service(1);
  store.client = { get: vi.fn().mockRejectedValueOnce(new Error('fixture')) } as any;
  await store.fetchServices(); expect(store.services[1]).toBeDefined(); expect(store.servicesError).toContain('Could not load');
  const response = deferred<any[]>(); store.client.get = vi.fn().mockReturnValue(response.promise);
  const fetch = store.fetchServices(); useAuth().endSession(); response.resolve([service(2)]); await fetch;
  expect(store.services).toEqual({});
});
it.each(['success', 'failure', 'deleted'])('step hydration preserves intervening %s and permits subsequent refresh', async outcome => {
  const store = useSteps(); const response = deferred<any[]>();
  store.client = { get: vi.fn().mockReturnValueOnce(response.promise).mockResolvedValueOnce([apiStep(1)]) } as any;
  const fetch = store.fetchStepsFromDeployment(1);
  store.onMessage({ id: 1, deploymentId: 1, name: 'newer', type: 'step', state: outcome, deleted: outcome === 'deleted' } as any);
  response.resolve([apiStep(1), apiStep(2)]); await fetch;
  if (outcome === 'deleted') expect(store.steps[1]).toBeUndefined(); else expect(store.steps[1].state).toBe(outcome);
  expect(store.steps[2]).toBeDefined(); await store.fetchStepsFromDeployment(1); expect(store.steps[1].state).toBe('running');
});
it('deduplicates running-scroll history and removes deleted entries', async () => {
  const store = useSteps(); store.client = { get: vi.fn().mockResolvedValue([apiStep(1)]) } as any;
  await store.fetchStepsFromDeployment(1); await store.fetchStepsFromDeployment(1);
  store.onMessage({ id: 1, deploymentId: 1, type: 'step', state: 'running' } as any);
  expect(store.stepsInProgressByDeployment[1].map(step => step.id)).toEqual([1]);
  store.onMessage({ id: 1, deploymentId: 1, type: 'step', deleted: true } as any);
  expect(store.stepsInProgressByDeployment[1]).toEqual([]);
});
it('retires failed step hydration fences', async () => {
  const store = useSteps(); const response = deferred<any[]>();
  store.client = { get: vi.fn().mockReturnValueOnce(response.promise).mockResolvedValueOnce([apiStep(1)]) } as any;
  const fetch = store.fetchStepsFromDeployment(1); store.onMessage({ id: 1, deploymentId: 1, type: 'step', deleted: true } as any);
  response.reject(new Error('fixture')); await expect(fetch).rejects.toThrow('fixture');
  await store.fetchStepsFromDeployment(1); expect(store.steps[1]).toBeDefined();
});
it.each(['token', 'start', 'query', 'return'])('late launch preserves newer navigation during %s', async phase => {
  const store = useServices(); store.services[1] = service(1);
  const token = deferred<string>(); const start = deferred<Response>();
  const issue = vi.spyOn(store, 'fetchServiceToken').mockReturnValue(token.promise);
  const fetch = vi.fn().mockReturnValue(start.promise); vi.stubGlobal('fetch', fetch);
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: ServiceList }, { path: '/other', component: { template: '<p>Other</p>' } },
    { path: '/deployments/:id', name: 'deployment-detail', component: { template: '<p>Deployment</p>' } },
  ] });
  await router.push('/'); await router.isReady();
  const wrapper = mount(RouterView, { global: { plugins: [getActivePinia()!, router], stubs: { ProgressCount: true, RouterLink: true } } });
  await flushPromises(); await wrapper.get('button[aria-label="Deploy service-1"]').trigger('click');
  if (phase !== 'token') { token.resolve('synthetic-credential'); await flushPromises(); }
  await router.push(phase === 'query' ? '/?changed=1' : '/other'); if (phase === 'return') await router.push('/');
  const destination = router.currentRoute.value.fullPath;
  token.resolve('synthetic-credential'); await flushPromises();
  start.resolve(new Response(JSON.stringify({ id: 7, service_id: 1, origin: 'fixture' }), { headers: { 'Content-Type': 'application/json' } }));
  await flushPromises(); expect(router.currentRoute.value.fullPath).toBe(destination);
  expect(useDeployments().deployments[7].serviceId).toBe(1);
  expect(issue).toHaveBeenCalledTimes(1); expect(fetch).toHaveBeenCalledTimes(1); wrapper.unmount();
});

it('removes absent steps from all indexes while retaining live changes and other deployments', async () => {
  const store = useSteps();
  for (const id of [1, 2, 3]) store.addStep({ id, deploymentId: 1, name: 'old', state: 'running' } as any);
  store.addStep({ id: 9, deploymentId: 2, name: 'other', state: 'running' } as any);
  const response = deferred<any[]>(); store.client = { get: vi.fn().mockReturnValue(response.promise) } as any;
  const fetch = store.fetchStepsFromDeployment(1);
  store.onMessage({ id: 2, deploymentId: 1, type: 'step', deleted: true } as any);
  store.onMessage({ id: 4, deploymentId: 1, type: 'step', state: 'running', name: 'live' } as any);
  store.onMessage({ id: 3, deploymentId: 1, type: 'step', state: 'success', name: 'updated' } as any);
  response.resolve([apiStep(2), apiStep(5)]); await fetch;
  expect(Object.keys(store.steps)).toEqual(['3', '4', '5', '9']);
  expect(Object.keys(store.stepsByDeployment[1])).toEqual(['3', '4', '5']);
  expect(store.stepsInProgressByDeployment[1].map(step => step.id).sort()).toEqual([3, 4, 5]);
  expect(store.stepsInProgressByDeployment[2].map(step => step.id)).toEqual([9]);
});

it('awaits service names, fences older results, contains errors, retries and resets session state', async () => {
  const store = useServices(); const old = deferred<string[]>(); const latest = deferred<string[]>();
  store.client = { get: vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise) } as any;
  const first = store.fetchServiceNames(); const second = store.fetchServiceNames();
  latest.resolve(['new']); await second; old.resolve(['old']); await first; await flushPromises();
  expect(store.serviceNames).toEqual(['new']);
  store.client.get = vi.fn().mockRejectedValue(new Error('private diagnostic'));
  await store.fetchServiceNames(); expect(store.serviceNamesError).toContain('Could not load');
  expect(store.serviceNames).toEqual(['new']); expect(store.serviceNamesLoading).toBe(false);
  store.client.get = vi.fn().mockResolvedValue(['retry']); await store.fetchServiceNames();
  expect(store.serviceNames).toEqual(['retry']); expect(store.serviceNamesError).toBe('');
  const late = deferred<string[]>(); store.client.get = vi.fn().mockReturnValue(late.promise);
  const pending = store.fetchServiceNames(); useAuth().endSession(); late.resolve(['secret']); await pending;
  expect(store.serviceNames).toEqual([]); expect(store.serviceNamesLoading).toBe(false); expect(store.serviceNamesError).toBe('');
});


it('an obsolete service-name failure cannot clear loading or set feedback for a newer request', async () => {
  const store = useServices(), old = deferred<string[]>(), latest = deferred<string[]>();
  store.client = { get: vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise) } as any;
  const first = store.fetchServiceNames(), second = store.fetchServiceNames();
  old.reject(new Error('obsolete')); await first;
  expect(store.serviceNamesLoading).toBe(true); expect(store.serviceNamesError).toBe('');
  latest.resolve(['current']); await second;
  expect(store.serviceNamesLoading).toBe(false); expect(store.serviceNames).toEqual(['current']);
});

it('shows bounded service-name failure feedback and allows retry from the mounted Services view', async () => {
  const store = useServices();
  store.client = { get: vi.fn().mockRejectedValueOnce(new Error('private')).mockResolvedValueOnce(['new']) } as any;
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: ServiceList }] });
  await router.push('/'); await router.isReady();
  const wrapper = mount(ServiceList, { global: { plugins: [getActivePinia()!, router] } });
  await store.fetchServiceNames(); await flushPromises();
  expect(wrapper.text()).toContain('Could not load service names'); expect(wrapper.text()).not.toContain('private');
  await wrapper.findAll('button').find(button => button.text() === 'Retry service names')!.trigger('click');
  await flushPromises(); expect(store.serviceNames).toEqual(['new']); expect(wrapper.text()).not.toContain('Could not load');
  wrapper.unmount();
});

it.each(['success', 'error'])('a history refresh that loses ownership after %s leaves a retry message', async outcome => {
  const store = useDeployments(); store.deployments[3] = { id: 3, serviceId: 1 } as any; store.historyIds = [3];
  const response = deferred<any[]>(); store.client = { get: vi.fn().mockReturnValue(response.promise) } as any;
  let owned = true;
  const fetch = store.fetchDeployments(undefined, false, () => owned);
  owned = false;
  if (outcome === 'success') response.resolve([{ id: 3, service_id: 1 }]); else response.reject(new Error('fixture'));
  await fetch;
  expect(store.historyLoading).toBe(false);
  expect(store.historyError).toContain('Could not load deployment history');
});

it('a started deployment survives an older in-flight history page that predates it', async () => {
  const store = useDeployments(); const page = deferred<any[]>();
  store.client = { get: vi.fn().mockReturnValue(page.promise) } as any;
  vi.spyOn(useServices(), 'fetchServiceToken').mockResolvedValue('synthetic-credential');
  const history = store.fetchDeployments();
  const client = { options: { headers: {} as Record<string, string> }, post: vi.fn().mockResolvedValue({ id: 9, service_id: 1 }) };
  await store.startDeployment('service-1', client as any);
  page.resolve([{ id: 8, service_id: 1 }]); await history;
  expect(store.deployments[9]).toBeDefined();
  expect(store.historyIds).toContain(8);
});

it('a history page served after a start still updates the started row', async () => {
  const store = useDeployments(); const page = deferred<any[]>();
  store.client = { get: vi.fn().mockReturnValue(page.promise) } as any;
  vi.spyOn(useServices(), 'fetchServiceToken').mockResolvedValue('synthetic-credential');
  const history = store.fetchDeployments();
  const client = { options: { headers: {} as Record<string, string> }, post: vi.fn().mockResolvedValue({ id: 9, service_id: 1, finished: null }) };
  await store.startDeployment('service-1', client as any);
  const finished = '2026-11-01T00:00:00Z';
  page.resolve([{ id: 9, service_id: 1, finished }]); await history;
  expect(store.deployments[9].finished).toEqual(new Date(finished));
});
