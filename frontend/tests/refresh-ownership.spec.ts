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
const apiStep = (id: number) => ({ id, deployment_id: 1, name: `step-${id}`, state: 'running', type: 'step' });
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
