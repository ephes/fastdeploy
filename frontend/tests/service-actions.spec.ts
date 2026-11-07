import { vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { initPinia } from './conftest';
import ServiceList from '../src/components/ServiceList.vue';
import { useServices } from '../src/stores/service';
import { useDeployments } from '../src/stores/deployment';
import { useAuth } from '../src/stores/auth';

const originalConfirm = window.confirm;
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
}
function action(wrapper: any, kind: 'Deploy' | 'Delete', name: string) {
  const row = wrapper.findAll('tr.list-service').find((candidate: any) => candidate.find('td').text() === name)!;
  return row.findAll('button')[kind === 'Deploy' ? 0 : 1];
}
function setup() {
  const store = useServices();
  store.services = { 1: { id: 1, name: 'first', data: {} }, 2: { id: 2, name: 'second', data: {} } };
  const wrapper = mount(ServiceList, { global: { stubs: { 'router-link': true, ProgressCount: true } } });
  return { store, wrapper };
}

beforeEach(() => { initPinia(); push.mockReset(); });
afterEach(() => { window.confirm = originalConfirm; vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('confirms the named service/history, cancels without a request, and deletes only after success', async () => {
  const { store, wrapper } = setup();
  const response = deferred<any>();
  const remove = vi.fn().mockReturnValue(response.promise);
  store.client = { delete: remove } as any;
  const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValue(true);
  window.confirm = confirm;
  const button = action(wrapper, 'Delete', 'first');
  await button.trigger('click');
  expect(remove).not.toHaveBeenCalled();
  expect(confirm.mock.calls[0][0]).toContain('first');
  expect(confirm.mock.calls[0][0]).toContain('history');
  await button.trigger('click'); await button.trigger('click');
  expect(remove).toHaveBeenCalledTimes(1);
  expect(store.services[1]).toBeDefined();
  expect(button.attributes('disabled')).toBeDefined();
  response.resolve({ detail: 'Service 1 deleted' }); await flushPromises();
  expect(store.services[1]).toBeUndefined();
  expect(store.services[2].name).toBe('second');
  expect(action(wrapper, 'Delete', 'second').attributes('aria-label')).toBe('Delete second');
  wrapper.unmount();
});

it.each([409, 404, 0])('keeps deletion refusal/transport failure visible and retryable (%s)', async status => {
  const { store, wrapper } = setup();
  window.confirm = vi.fn().mockReturnValue(true);
  const remove = vi.fn().mockRejectedValueOnce({ response: { status }, message: 'synthetic-secret', body: { detail: 'synthetic-secret' } }).mockResolvedValueOnce({ detail: 'deleted' });
  store.client = { delete: remove } as any;
  const button = action(wrapper, 'Delete', 'first');
  await button.trigger('click'); await flushPromises();
  expect(store.services[1]).toBeDefined();
  expect(wrapper.get('[role="alert"]').text()).toContain(status === 409 ? 'running' : status === 404 ? 'no longer exists' : 'Could not confirm');
  expect(wrapper.text()).not.toContain('synthetic-secret');
  expect(button.attributes('disabled')).toBeUndefined();
  await button.trigger('click'); await flushPromises();
  expect(store.services[1]).toBeUndefined();
  wrapper.unmount();
});

it('bounds a pending launch per service and navigates only after confirmed success', async () => {
  const { store, wrapper } = setup();
  vi.spyOn(store, 'fetchServiceToken').mockResolvedValue('synthetic-credential');
  const response = deferred<Response>();
  const fetch = vi.fn().mockReturnValue(response.promise);
  vi.stubGlobal('fetch', fetch);
  const button = action(wrapper, 'Deploy', 'first');
  await button.trigger('click'); await button.trigger('click'); await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(button.attributes('disabled')).toBeDefined();
  expect(action(wrapper, 'Deploy', 'second').attributes('disabled')).toBeUndefined();
  expect(push).not.toHaveBeenCalled();
  response.resolve(new Response(JSON.stringify({ id: 7, service_id: 1, origin: 'fixture', user: 'fixture' }), { headers: { 'Content-Type': 'application/json' } }));
  await flushPromises();
  expect(push).toHaveBeenCalledWith({ name: 'deployment-detail', params: { id: 7 } });
  wrapper.unmount();
});

it.each(['conflict', 'network', 'token'])('shows safe launch feedback and permits a deliberate retry after %s', async failure => {
  const { store, wrapper } = setup();
  vi.spyOn(store, 'fetchServiceToken').mockResolvedValue(failure === 'token' ? null : 'synthetic-credential');
  const fetch = vi.fn().mockImplementation(async () => {
    if (failure === 'network') throw new Error('synthetic-secret');
    return new Response(JSON.stringify({ detail: { message: 'synthetic-secret' } }), { status: 409, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetch);
  const button = action(wrapper, 'Deploy', 'first');
  await button.trigger('click'); await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain('first');
  expect(wrapper.text()).not.toContain('synthetic-secret');
  expect(button.attributes('disabled')).toBeUndefined();
  expect(push).not.toHaveBeenCalled();
  expect(fetch).toHaveBeenCalledTimes(failure === 'token' ? 0 : 1);
  wrapper.unmount();
});

it('ignores a late launch success after logout even when supplied by a store mock', async () => {
  const { wrapper } = setup();
  const response = deferred<any>();
  vi.spyOn(useDeployments(), 'startDeployment').mockReturnValue(response.promise);
  await action(wrapper, 'Deploy', 'first').trigger('click');
  useAuth().endSession();
  response.resolve({ id: 7 }); await flushPromises();
  expect(push).not.toHaveBeenCalled();
  wrapper.unmount();
});


it('puts real token-issuance details in one contextual row alert', async () => {
  const { store, wrapper } = setup();
  store.client = { post: vi.fn().mockRejectedValue({ response: { status: 403 }, body: { detail: 'Service token issuance requires an administrator' } }) } as any;
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  await action(wrapper, 'Deploy', 'first').trigger('click'); await flushPromises();
  expect(store.client.post).toHaveBeenCalledTimes(1);
  expect(fetch).not.toHaveBeenCalled();
  expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
  expect(wrapper.get('[role="alert"]').text()).toContain('first');
  expect(wrapper.get('[role="alert"]').text()).toContain('requires an administrator');
  expect(store.serviceTokenErrorMessage).toBe('');
  wrapper.unmount();
});

it('clears a deletion error when a deletion event confirms removal', () => {
  const { store, wrapper } = setup();
  store.deleteErrors[1] = 'synthetic-error';
  store.onMessage({ type: 'service', id: 1, deleted: true } as any);
  expect(store.services[1]).toBeUndefined();
  expect(store.deleteErrors[1]).toBeUndefined();
  wrapper.unmount();
});
