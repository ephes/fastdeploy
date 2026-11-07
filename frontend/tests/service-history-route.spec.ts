import { vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';
import { routes } from '../src/routes';
import ServiceList from '../src/components/ServiceList.vue';
import DeploymentList from '../src/components/DeploymentList.vue';
import { useServices } from '../src/stores/service';
import { useDeployments } from '../src/stores/deployment';

it('roundtrips a real service-history link through a fresh router and resets paging on back/forward', async () => {
  const pinia = createPinia(); setActivePinia(pinia);
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push('/'); await router.isReady();
  useServices().services[7] = { id: 7, name: 'fixture-seven', data: {} };
  const services = mount(ServiceList, { global: { plugins: [pinia, router], stubs: { ProgressCount: true } } });
  const href = services.get('a[href="/deployments?serviceId=7"]').attributes('href')!;
  services.unmount();
  const fresh = createRouter({ history: createMemoryHistory(), routes });
  expect(fresh.resolve(href).name).toBe('deployment-list');
  expect(fresh.resolve(href).query.serviceId).toBe('7');
  await fresh.push(href); await fresh.isReady();
  const store = useDeployments();
  let resolveOld!: (rows: any[]) => void;
  const get = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValue([{ id: 202, service_id: 8, origin: 'fixture-eight' }]);
  store.client = { get } as any;
  const list = mount(DeploymentList, { global: { plugins: [pinia, fresh] } });
  expect(get).toHaveBeenLastCalledWith('deployments/?limit=50&service_id=7');
  store.historyBeforeId = 50; // a prior paging cursor must not survive a filter change
  await fresh.push('/deployments?serviceId=8'); await flushPromises();
  expect(get).toHaveBeenLastCalledWith('deployments/?limit=50&service_id=8');
  resolveOld([{ id: 101, service_id: 7, origin: 'obsolete-seven' }]); await flushPromises();
  expect(list.text()).toContain('fixture-eight');
  expect(list.text()).not.toContain('obsolete-seven');
  get.mockResolvedValueOnce([{ id: 103, service_id: 7, origin: 'fixture-seven' }]);
  fresh.back();
  await vi.waitFor(() => expect(get).toHaveBeenLastCalledWith('deployments/?limit=50&service_id=7'));
  await flushPromises();
  expect(list.text()).toContain('fixture-seven');
  expect(list.text()).not.toContain('fixture-eight');
  fresh.forward();
  await vi.waitFor(() => expect(get).toHaveBeenLastCalledWith('deployments/?limit=50&service_id=8'));
  await flushPromises();
  expect(list.text()).toContain('fixture-eight');
  expect(list.text()).not.toContain('fixture-seven');
  list.unmount();
});
