import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useServices } from '../src/stores/service';
import { useAuth } from '../src/stores/auth';
import { useDeployments } from '../src/stores/deployment';
import { initPinia } from './conftest';

const token = 'synthetic-credential';
const valid = { service_token: token, token_type: 'bearer', jti: 'synthetic-id', expires_at: '2030-01-01T00:00:00Z' };
const failure = 'Could not issue a service token. Check your permissions and inputs, then retry.';

beforeEach(initPinia);
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function respond(body: string, status = 200) {
  const fetch = vi.fn().mockResolvedValue(new Response(body, { status }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

describe('service token response admission through the HTTP client', () => {
  const malformed: [string, unknown][] = [
    ['missing token', { token_type: 'bearer' }],
    ['null token', { ...valid, service_token: null }],
    ['object token', { ...valid, service_token: { secret: token } }],
    ['numeric token', { ...valid, service_token: 42 }],
    ['empty token', { ...valid, service_token: '' }],
    ['whitespace token', { ...valid, service_token: ' \t' }],
    ['control character', { ...valid, service_token: token + '\u0000' }],
    ['DEL character', { ...valid, service_token: token + '\u007f' }],
    ['non-ASCII token', { ...valid, service_token: token + '\u2603' }],
    ['embedded whitespace', { ...valid, service_token: token + '\nvalue' }],
    ['oversized token', { ...valid, service_token: 'x'.repeat(16 * 1024 + 1) }],
    ['missing type', { service_token: token }],
    ['wrong type', { ...valid, token_type: 'other' }],
    ['array', [valid]],
    ['null response', null],
    ['primitive', token],
  ];

  it.each(malformed)('rejects %s without exposing credentials', async (_label, body) => {
    const store = useServices();
    const logs = ['log', 'info', 'warn', 'error', 'debug'].map(method =>
      vi.spyOn(console, method as 'log').mockImplementation(() => {}));
    const fetch = respond(JSON.stringify(body));
    expect(await store.fetchServiceToken('fixture-service', 'frontend')).toBeNull();
    expect(store.serviceTokenErrorMessage).toBe(failure);
    expect(fetch).toHaveBeenCalledTimes(1);
    for (const log of logs) expect(log).not.toHaveBeenCalled();
  });

  it('rejects invalid JSON with request-local feedback', async () => {
    const store = useServices();
    store.serviceTokenErrorMessage = 'other request';
    respond('{"service_token":"' + token);
    const onError = vi.fn();
    expect(await store.fetchServiceToken('fixture-service', 'frontend', 1, onError)).toBeNull();
    expect(onError).toHaveBeenCalledExactlyOnceWith(failure);
    expect(store.serviceTokenErrorMessage).toBe('other request');
  });

  it('never launches a deployment with a malformed token', async () => {
    const store = useServices();
    store.services = { 1: { id: 1, name: 'fixture-service', data: {} } };
    respond(JSON.stringify({ ...valid, service_token: { secret: token } }));
    const client = { post: vi.fn(), options: { headers: {} } };
    const onError = vi.fn();
    expect(await useDeployments().startDeployment('fixture-service', client as any, onError)).toBeNull();
    expect(client.post).not.toHaveBeenCalled();
    expect(client.options.headers).toEqual({});
    expect(onError).toHaveBeenCalledExactlyOnceWith(failure);
  });

  it('does not reflect a transport exception in diagnostics', async () => {
    const store = useServices();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error(token)));
    expect(await store.fetchServiceToken('fixture-service', 'frontend')).toBeNull();
    expect(store.serviceTokenErrorMessage).toBe(failure);
  });

  it.each([token.length, 16 * 1024])('returns an admitted token of length %s', async length => {
    const value = 'x'.repeat(length);
    const store = useServices();
    store.serviceTokenErrorMessage = 'previous failure';
    const fetch = respond(JSON.stringify({ ...valid, service_token: value }));
    expect(await store.fetchServiceToken('fixture-service', 'frontend')).toBe(value);
    expect(store.serviceTokenErrorMessage).toBe('');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([403, 404, 422, 500])('never reflects body or exception text for status %s', async status => {
    const store = useServices();
    const onError = vi.fn();
    respond(JSON.stringify({ detail: token }), status);
    expect(await store.fetchServiceToken('fixture-service', 'frontend', 1, onError)).toBeNull();
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).not.toContain(token);
    expect(store.serviceTokenErrorMessage).toBe('');
  });

  it.each([valid, { ...valid, service_token: {} }])('retires a token response after logout and a new session', async body => {
    const store = useServices();
    let resolve!: (response: Response) => void;
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise<Response>(yes => { resolve = yes; })));
    const onError = vi.fn();
    const pending = store.fetchServiceToken('fixture-service', 'frontend', 1, onError);
    useAuth().logout();
    useAuth().sessionId++;
    store.serviceTokenErrorMessage = 'new-session feedback';
    resolve(new Response(JSON.stringify(body)));
    expect(await pending).toBeNull();
    expect(onError).not.toHaveBeenCalled();
    expect(store.serviceTokenErrorMessage).toBe('new-session feedback');
  });
});
