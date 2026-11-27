import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import DeploymentDetail from '../src/components/DeploymentDetail.vue';
import { useDeployments } from '../src/stores/deployment';
import { useSteps } from '../src/stores/step';
import type { Step } from '../src/typings';

async function open(get: (...args: any[]) => Promise<unknown>, finished: Date | null = new Date(60_000)) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/deployments/:id', component: DeploymentDetail },
    { path: '/deployments', component: { template: '<p>History</p>' } },
  ] });
  await router.push('/deployments/1');
  await router.isReady();
  useDeployments().deployments[1] = {
    id: 1, serviceId: 1, origin: 'fixture', user: 'synthetic', started: new Date(0), finished,
  };
  const steps = useSteps();
  steps.client = { get } as any;
  const wrapper = mount(RouterView, { global: { plugins: [pinia, router] } });
  return { wrapper, steps };
}
const row = (id: number, state: string) => ({
  id, deployment_id: 1, name: `step-${id}`, state, message: '', started: null, finished: null,
});

it('does not report success from a partial step cache when the inventory fails', async () => {
  const { wrapper, steps } = await open(vi.fn().mockRejectedValue(new Error('fixture failure')));
  const cached: Step = { type: 'step', id: 1, deploymentId: 1, name: 'cached', state: 'success',
    message: '', started: null, finished: null };
  steps.onMessage(cached);
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain('Try again.');
  expect(wrapper.get('.state').text()).toBe('Finished');
});

it.each([
  [[row(2, 'success'), row(1, 'success')], new Date(60_000), 'Succeeded'],
  [[row(2, 'failure'), row(1, 'success')], new Date(60_000), 'Failed'],
  [[row(2, 'running'), row(1, 'success')], null, 'Running'],
  [[], new Date(60_000), 'Finished'],
])('derives the state badge from a complete inventory', async (rows, finished, label) => {
  const { wrapper } = await open(vi.fn().mockResolvedValue(rows), finished);
  await flushPromises();
  expect(wrapper.get('.state').text()).toBe(label);
});

it('does not report success for a deployment that finished after its steps were loaded', async () => {
  const { wrapper } = await open(vi.fn().mockResolvedValue([row(2, 'success'), row(1, 'success')]), null);
  await flushPromises();
  expect(wrapper.get('.state').text()).toBe('Running');
  useDeployments().deployments[1].finished = new Date(60_000);
  await flushPromises();
  expect(wrapper.get('.state').text()).toBe('Finished');
});
