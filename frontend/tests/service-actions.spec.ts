import type { ServiceWithId } from '../src/typings';
import { vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createEvent, initPinia } from './conftest';
import ServiceList from '../src/components/ServiceList.vue';
import { useServices } from '../src/stores/service';
import { useDeployments } from '../src/stores/deployment';
import { useAuth } from '../src/stores/auth';
import { createWebsocketClient } from '../src/websocket';

const originalConfirm = window.confirm;
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push, currentRoute: { value: null } }) }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
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

it('shares the pending deletion with remounted lists and direct callers', async () => {
  const { store, wrapper } = setup();
  const response = deferred<unknown>();
  const remove = vi.fn().mockReturnValue(response.promise);
  store.client = { delete: remove } as any;
  window.confirm = vi.fn().mockReturnValue(true);

  await action(wrapper, 'Delete', 'first').trigger('click');
  wrapper.unmount();
  const remounted = mount(ServiceList, { global: { stubs: { 'router-link': true, ProgressCount: true } } });
  const button = action(remounted, 'Delete', 'first');
  await button.trigger('click');
  const duplicate = store.deleteService(1);
  expect(remove).toHaveBeenCalledTimes(1);
  await expect(duplicate).resolves.toBe(false);
  expect(button.attributes('disabled')).toBeDefined();

  response.reject({ response: { status: 409 } });
  await flushPromises();
  expect(store.pendingDeletes.has(1)).toBe(false);
  expect(button.attributes('disabled')).toBeUndefined();
  expect(remounted.get('[role="alert"]').text()).toContain('running');
  remounted.unmount();
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
  response.resolve(new Response(JSON.stringify({ id: 7, service_id: 1, started: '2026-11-01T00:00:00Z', finished: null, origin: 'fixture', user: 'fixture' }), { headers: { 'Content-Type': 'application/json' } }));
  await flushPromises();
  expect(push).toHaveBeenCalledWith({ name: 'deployment-detail', params: { id: 7 } });
  wrapper.unmount();
});

it('asks for a new selection when a service is replaced during token issuance', async () => {
  const { store, wrapper } = setup();
  const credential = { token_type: 'bearer', service_token: 'synthetic-token' };
  const token = deferred<typeof credential>();
  store.client.post = vi.fn().mockReturnValueOnce(token.promise).mockResolvedValueOnce(credential);
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({
    id: 7, service_id: 3, origin: 'frontend', user: 'synthetic',
    started: '2026-11-01T00:00:00Z', finished: null,
  })));
  vi.stubGlobal('fetch', fetch);
  const websocket = createWebsocketClient();
  websocket.registerStore(store);
  websocket.onAuthenticationMessage({ type: 'authentication', status: 'success' });

  await action(wrapper, 'Deploy', 'first').trigger('click');
  expect(store.client.post).toHaveBeenCalledTimes(1);
  websocket.onMessage(createEvent({ ...store.services[1], type: 'service', deleted: true }));
  websocket.onMessage(createEvent({ type: 'service', id: 3, name: 'first', data: {} }));
  token.resolve(credential);
  await flushPromises();

  expect(fetch).not.toHaveBeenCalled();
  expect(push).not.toHaveBeenCalled();
  expect(wrapper.get('[role="alert"]').text()).toContain('Select the service again');
  await action(wrapper, 'Deploy', 'first').trigger('click');
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(push).toHaveBeenCalledExactlyOnceWith({ name: 'deployment-detail', params: { id: 7 } });
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  wrapper.unmount();
});

it('ignores a start acknowledgement for a deployment deleted while the POST was pending', async () => {
  const { store, wrapper } = setup();
  const deployments = useDeployments();
  const websocket = createWebsocketClient();
  websocket.registerStore(deployments);
  websocket.onAuthenticationMessage({ type: "authentication", status: "success" });
  vi.spyOn(store, 'fetchServiceToken').mockResolvedValue('synthetic-credential');
  const deleted = deferred<Response>();
  const unaffected = deferred<Response>();
  const fetch = vi.fn().mockReturnValueOnce(deleted.promise).mockReturnValueOnce(unaffected.promise);
  vi.stubGlobal('fetch', fetch);
  const row = { id: 7, service_id: 1, started: '2026-11-01T00:00:00Z', finished: null, origin: 'fixture', user: 'fixture' };
  const reply = (body: typeof row) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
  await action(wrapper, 'Deploy', 'first').trigger('click');
  await action(wrapper, 'Deploy', 'second').trigger('click');
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);

  websocket.onMessage(createEvent({ ...row, type: 'deployment', deleted: true }));
  deleted.resolve(reply(row));
  await flushPromises();
  expect(push).not.toHaveBeenCalled();
  expect(deployments.deployments[7]).toBeUndefined();
  expect(wrapper.get('[role="alert"]').text()).toContain('Check its history');

  unaffected.resolve(reply({ ...row, id: 6, service_id: 2 }));
  await flushPromises();
  expect(deployments.deployments[6].serviceId).toBe(2);
  expect(push).toHaveBeenCalledExactlyOnceWith({ name: 'deployment-detail', params: { id: 6 } });
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

it('directs refused starts with an orphan backlog to deployment history', async () => {
  const { store, wrapper } = setup();
  vi.spyOn(store, 'fetchServiceToken').mockResolvedValue('synthetic-credential');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ detail: { code: 'orphan_backlog', message: 'synthetic-private-detail' } }),
    { status: 409, headers: { 'Content-Type': 'application/json' } },
  )));

  await action(wrapper, 'Deploy', 'first').trigger('click');
  await flushPromises();

  expect(wrapper.get('[role="alert"]').text()).toContain('Open deployment history to reconcile orphaned deployments');
  expect(wrapper.text()).not.toContain('synthetic-private-detail');
  expect(push).not.toHaveBeenCalled();
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


it('puts fixed token-issuance feedback in one contextual row alert', async () => {
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

it.each([{ service_id: 2 }, { id: 0 }, { started: 'invalid' }, { finished: false }])('never navigates after invalid successful launch response: %j', async invalid => {
  const { store, wrapper } = setup();
  vi.spyOn(store, 'fetchServiceToken').mockResolvedValue('synthetic-token');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    id: 7, service_id: 1, origin: 'frontend', user: 'synthetic',
    started: '2026-11-01T00:00:00Z', finished: null, ...invalid,
  }))));
  await action(wrapper, 'Deploy', 'first').trigger('click'); await flushPromises();
  expect(push).not.toHaveBeenCalled();
  expect(useDeployments().deployments).toEqual({});
  expect(wrapper.get('[role="alert"]').text()).toContain('history before retrying');
  wrapper.unmount();
});

it.each(['success', 'transport loss', 'HTTP conflict'])('settles a socket-confirmed deletion without affecting a replacement (%s)', async outcome => {
  const store = useServices();
  store.services[1] = { id: 1, name: 'first', data: {} };
  const response = deferred<unknown>();
  store.client.delete = vi.fn().mockReturnValue(response.promise);
  const websocket = createWebsocketClient();
  websocket.registerStore(store);
  websocket.onAuthenticationMessage({ type: 'authentication', status: 'success' });
  const first = store.deleteService(1);
  websocket.onMessage(createEvent({ ...store.services[1], type: 'service', deleted: true }));
  expect(store.services[1]).toBeUndefined();
  websocket.onMessage(createEvent({ type: 'service', id: 1, name: 'replacement', data: {} } as ServiceWithId));
  await expect(store.deleteService(1)).resolves.toBe(false);
  expect(store.client.delete).toHaveBeenCalledTimes(1);

  if (outcome === 'success') response.resolve(null);
  else if (outcome === 'transport loss') response.reject(new TypeError('Connection lost'));
  else response.reject({ response: { status: 409 } });
  await expect(first).resolves.toBe(outcome !== 'HTTP conflict');
  expect(store.services[1].name).toBe('replacement');
  expect(store.deleteErrors[1]).toBeUndefined();
  expect(store.pendingDeletes.has(1)).toBe(false);
});

it('settles a socket-confirmed deletion when HTTP returns 404 and a stale inventory is pending', async () => {
  const store = useServices();
  const service = { id: 1, name: 'first', data: {} };
  store.services[1] = service;
  const response = deferred<unknown>();
  const inventory = deferred<typeof service[]>();
  store.client.delete = vi.fn().mockReturnValue(response.promise);
  store.client.get = vi.fn().mockReturnValue(inventory.promise);
  const websocket = createWebsocketClient();
  websocket.registerStore(store);
  websocket.onAuthenticationMessage({ type: 'authentication', status: 'success' });

  const deleting = store.deleteService(1);
  const refreshing = store.fetchServices();
  websocket.onMessage(createEvent({ ...service, type: 'service', deleted: true }));
  expect(store.services[1]).toBeUndefined();
  response.reject({ response: { status: 404 } });
  await expect(deleting).resolves.toBe(true);
  expect(store.pendingDeletes.has(1)).toBe(false);
  expect(store.deleteErrors[1]).toBeUndefined();

  inventory.resolve([service]);
  await refreshing;
  expect(store.services[1]).toBeUndefined();
  expect(store.servicesError).toBe('');
});

it('keeps a transport failure unconfirmed when the socket deleted a different service', async () => {
  const { store, wrapper } = setup();
  const response = deferred<unknown>();
  store.client.delete = vi.fn().mockReturnValue(response.promise);
  const pending = store.deleteService(1);
  store.onMessage({ type: 'service', id: 2, deleted: true } as ServiceWithId);

  response.reject(new TypeError('Connection lost'));
  await expect(pending).resolves.toBe(false);
  expect(store.services[2]).toBeUndefined();
  expect(store.services[1].name).toBe('first');
  expect(store.deleteErrors[1]).toContain('Could not confirm deletion');
  wrapper.unmount();
});

it('ignores a socket-confirmed deletion from a retired session when its HTTP response is lost', async () => {
  const store = useServices();
  const auth = useAuth();
  const row = { id: 1, name: 'first', data: {} };
  store.services[1] = row;
  const old = deferred<unknown>();
  store.client.delete = vi.fn().mockReturnValue(old.promise);
  const retiring = store.deleteService(1);
  store.onMessage({ type: 'service', id: 1, deleted: true } as ServiceWithId);
  auth.logout();

  store.services[1] = row;
  const current = deferred<unknown>();
  store.client.delete = vi.fn().mockReturnValue(current.promise);
  const pending = store.deleteService(1);
  old.reject(new TypeError('Connection lost'));
  await expect(retiring).resolves.toBe(false);
  expect(store.pendingDeletes.has(1)).toBe(true);
  expect(store.services[1]).toEqual(row);
  expect(store.deleteErrors[1]).toBeUndefined();

  current.reject(new TypeError('Connection lost'));
  await expect(pending).resolves.toBe(false);
  expect(store.deleteErrors[1]).toContain('Could not confirm deletion');
});

it('keeps a confirmed deletion out of a pending snapshot', async () => {
  const store = useServices();
  const row = { id: 1, name: 'first', data: {} };
  store.services[1] = row;
  const snapshot = deferred<unknown>();
  const old = deferred<unknown>();
  store.client.get = vi.fn().mockReturnValue(snapshot.promise);
  store.client.delete = vi.fn().mockReturnValue(old.promise);
  const refresh = store.fetchServices();
  const first = store.deleteService(1);
  old.resolve(null);
  await expect(first).resolves.toBe(true);
  expect(store.deleteErrors[1]).toBeUndefined();
  snapshot.resolve([row]);
  await refresh;
  expect(store.services[1]).toBeUndefined();
});
