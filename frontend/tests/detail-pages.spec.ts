import { vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import Login from '../src/components/Login.vue';
import ServiceDetail from '../src/components/ServiceDetail.vue';
import DeploymentDetail from '../src/components/DeploymentDetail.vue';
import { useAuth } from '../src/stores/auth';
import { useServices } from '../src/stores/service';
import { useDeployments } from '../src/stores/deployment';
import { useSteps } from '../src/stores/step';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function setup(component: any, path: string) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/login', component: Login }, { path: '/', component: { template: '<p>Home</p>' } },
    { path: '/services/:id', component: ServiceDetail },
    { path: '/deployments/:id', component: DeploymentDetail },
  ] });
  await router.push(path);
  await router.isReady();
  return { router, mount: () => mount(component, { global: { plugins: [pinia, router] } }) };
}

it('labels a native credential form, suppresses duplicate submit, announces failure and allows retry', async () => {
  const page = await setup(Login, '/login');
  const auth = useAuth();
  const pending = deferred<void>();
  const login = vi.spyOn(auth, 'login').mockImplementationOnce(async () => {
    await pending.promise; auth.errorMessage = 'Invalid username or password';
  }).mockImplementationOnce(async () => { auth.accessToken = 'synthetic-token'; });
  const wrapper = page.mount();
  expect(wrapper.get('label[for="username"]').text()).toBe('Username');
  expect(wrapper.get('label[for="password"]').text()).toBe('Password');
  expect(wrapper.get('#username').attributes('autocomplete')).toBe('username');
  expect(wrapper.get('#password').attributes('autocomplete')).toBe('current-password');
  await wrapper.get('#username').setValue('fixture-user');
  await wrapper.get('#password').setValue('fixture-password');
  await wrapper.get('form').trigger('submit');
  await wrapper.get('form').trigger('submit');
  expect(login).toHaveBeenCalledTimes(1);
  expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
  pending.resolve(); await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain('Invalid username or password');
  expect(wrapper.get('#username').attributes('aria-describedby')).toBe('login-error');
  expect((wrapper.get('#password').element as HTMLInputElement).value).toBe('fixture-password');
  await wrapper.get('form').trigger('submit'); await flushPromises();
  expect(login).toHaveBeenCalledTimes(2);
  expect(page.router.currentRoute.value.path).toBe('/');
  wrapper.unmount();
});

it('reacts to late services and route changes and fences an old token response', async () => {
  const page = await setup(ServiceDetail, '/services/1');
  const store = useServices();
  store.servicesLoading = true;
  const old = deferred<string>();
  const fetch = vi.spyOn(store, 'fetchServiceToken').mockReturnValueOnce(old.promise).mockResolvedValueOnce('current-token');
  const wrapper = page.mount();
  expect(wrapper.text()).toContain('Loading service');
  store.services = { 1: { id: 1, name: 'first', data: {} }, 2: { id: 2, name: 'second', data: {} } };
  store.servicesLoading = false; await flushPromises();
  expect(wrapper.text()).toContain('first');
  expect(wrapper.get('label[for="token-origin"]').text()).toContain('Origin');
  await wrapper.get('#token-origin').setValue('fixture');
  await wrapper.get('button').trigger('click');
  await page.router.push('/services/2'); await flushPromises();
  expect(wrapper.text()).toContain('second');
  expect(wrapper.text()).not.toContain('first');
  old.resolve('old-token'); await flushPromises();
  expect(wrapper.text()).not.toContain('old-token');
  await wrapper.get('#token-origin').setValue('new-origin');
  await wrapper.get('button').trigger('click'); await flushPromises();
  expect(fetch).toHaveBeenLastCalledWith('second', 'new-origin', 7, expect.any(Function));
  expect(wrapper.text()).toContain('current-token');
  await page.router.push('/services/9'); await flushPromises();
  expect(wrapper.text()).toContain('Service not found');
  expect(wrapper.text()).not.toContain('current-token');
  wrapper.unmount();
});

it('keeps deployment metadata, steps, loading, error and retry scoped to the current route', async () => {
  const page = await setup(DeploymentDetail, '/deployments/1');
  const deployments = useDeployments();
  deployments.deployments = { 1: { id: 1, origin: 'first' }, 2: { id: 2, origin: 'second' } } as any;
  const steps = useSteps();
  const one = deferred<void>(); const two = deferred<void>();
  const fetch = vi.spyOn(steps, 'fetchStepsFromDeployment').mockResolvedValue(undefined)
    .mockReturnValueOnce(one.promise).mockReturnValueOnce(two.promise)
    .mockRejectedValueOnce(new Error('synthetic-secret')).mockResolvedValueOnce();
  steps.addStep({ id: 1, deploymentId: 1, name: 'first-step', state: 'pending' } as any);
  steps.addStep({ id: 2, deploymentId: 2, name: 'second-step', state: 'pending' } as any);
  const wrapper = page.mount();
  expect(wrapper.text()).toContain('Loading steps');
  await page.router.push('/deployments/2'); await flushPromises();
  one.resolve(); await flushPromises();
  expect(wrapper.text()).toContain('Deployment ID: 2');
  expect(wrapper.text()).toContain('second');
  expect(wrapper.text()).not.toContain('first-step');
  expect(wrapper.text()).toContain('Loading steps');
  two.resolve(); await flushPromises();
  expect(wrapper.text()).toContain('second-step');
  await page.router.push('/deployments/1'); await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain('Could not load');
  expect(wrapper.text()).not.toContain('synthetic-secret');
  await wrapper.get('button').trigger('click'); await flushPromises();
  expect(fetch.mock.calls.map(([id]) => id)).toEqual([1, 2, 1, 1]);
  expect(wrapper.text()).toContain('first-step');
  await page.router.push('/deployments/9'); await flushPromises();
  expect(wrapper.text()).toContain('Deployment not found');
  wrapper.unmount();
});


it('shows current token failure feedback without stale service details', async () => {
  const page = await setup(ServiceDetail, '/services/1');
  const store = useServices();
  store.services[1] = { id: 1, name: 'fixture-service', data: {} };
  vi.spyOn(store, 'fetchServiceToken').mockResolvedValue(null);
  const wrapper = page.mount();
  await wrapper.get('button').trigger('click'); await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain('Could not issue');
  expect(wrapper.get('button').attributes('disabled')).toBeUndefined();
  wrapper.unmount();
});

it('ignores an older fetch of the same deployment while retaining other deployment results', async () => {
  const page = await setup(DeploymentDetail, '/deployments/1');
  const store = useSteps();
  const first = deferred<any[]>(); const second = deferred<any[]>(); const latest = deferred<any[]>();
  store.client = { get: vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(latest.promise) } as any;
  const wrapper = page.mount();
  await page.router.push('/deployments/2'); await flushPromises();
  await page.router.push('/deployments/1'); await flushPromises();
  latest.resolve([{ id: 3, deployment_id: 1, name: 'latest', state: 'success', message: '', started: null, finished: null }]); await flushPromises();
  second.resolve([{ id: 2, deployment_id: 2, name: 'second-only', state: 'success', message: '', started: null, finished: null }]);
  first.resolve([{ id: 3, deployment_id: 1, name: 'obsolete', state: 'pending', message: '', started: null, finished: null }]); await flushPromises();
  expect(wrapper.text()).toContain('latest');
  expect(wrapper.text()).not.toContain('obsolete');
  expect(wrapper.text()).not.toContain('second-only');
  expect(store.getStepsByDeployment(2)[0].name).toBe('second-only');
  wrapper.unmount();
});


it('shows safe validation details locally and never leaks discarded errors to the list', async () => {
  const page = await setup(ServiceDetail, '/services/1');
  const store = useServices();
  store.serviceTokenErrorMessage = 'prior-list-error';
  store.services = { 1: { id: 1, name: 'first', data: {} }, 2: { id: 2, name: 'second', data: {} } };
  const old = deferred<any>();
  store.client = { post: vi.fn().mockReturnValueOnce(old.promise).mockRejectedValueOnce({ response: { status: 422 }, body: { detail: 'origin must not be empty' } }) } as any;
  const wrapper = page.mount();
  expect(store.serviceTokenErrorMessage).toBe('');
  await wrapper.get('button').trigger('click');
  await page.router.push('/services/2'); await flushPromises();
  await wrapper.get('button').trigger('click'); await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain('origin must not be empty');
  old.reject({ response: { status: 403 }, body: { detail: 'obsolete-first-error' } }); await flushPromises();
  expect(wrapper.text()).not.toContain('obsolete-first-error');
  expect(wrapper.get('[role="alert"]').text()).toContain('origin must not be empty');
  expect(store.serviceTokenErrorMessage).toBe('');
  await page.router.push('/'); await flushPromises();
  expect(store.serviceTokenErrorMessage).toBe('');
  wrapper.unmount();
});
