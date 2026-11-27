import { vi } from 'vitest';
import { initPinia } from './conftest';
import { getClientWithoutAuth } from '../src/stores/httpClient';
const limit = 1024 * 1024;
beforeEach(() => initPinia());
afterEach(() => vi.unstubAllGlobals());
it.each([{}, { 'Content-Length': '1' }, { 'Content-Length': String(limit + 1) }])('bounds streamed success/error bodies despite headers: %j', async headers => {
  for (const status of [200, 409, 404]) {
    let reads = 0;
    const cancel = vi.fn();
    const body = new ReadableStream({
      pull(controller) { if (reads === 20) { controller.close(); return; } reads++; controller.enqueue(new Uint8Array(64 * 1024)); }, cancel,
    }, { highWaterMark: 0 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status, headers: headers as Record<string, string> })));
    const deletion = getClientWithoutAuth().delete('services/1');
    if (status === 200) {
      await expect(deletion).rejects.toThrow(/response.*large/i);
    } else {
      await expect(deletion).rejects.toMatchObject({ response: { status }, body: null });
    }
    expect(reads).toBe(headers['Content-Length'] === String(limit + 1) ? 0 : 17);
    expect(cancel).toHaveBeenCalledTimes(1);
  }
});
it('admits exactly the byte limit, preserves bounded error JSON, and auth headers', async () => {
  const json = JSON.stringify('x'.repeat(limit - 2));
  const fetch = vi.fn().mockResolvedValueOnce(new Response(json)).mockResolvedValueOnce(new Response('{"detail":"refused"}', { status: 409 }));
  vi.stubGlobal('fetch', fetch);
  const client = getClientWithoutAuth(); client.options.headers.Authorization = 'Bearer synthetic';
  expect((await client.get<string>('services/')).length).toBe(limit - 2);
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer synthetic');
  await expect(client.get('services/')).rejects.toMatchObject({ response: { status: 409 }, body: { detail: 'refused' } });
});

it('reports invalid JSON encoding and preserves text and raw response modes', async () => {
  const bytes = new Uint8Array([0x22, 0xff, 0x22]);
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(bytes))));
  const client = getClientWithoutAuth();
  await expect(client.get('services/')).rejects.toThrow('Server JSON response is not valid UTF-8.');
  await expect(client.get('services/', { responseAs: 'text' })).resolves.toBe('"�"');
  const raw = await client.get('services/', { responseAs: 'response' });
  expect(new Uint8Array(await raw.arrayBuffer())).toEqual(bytes);
});

it('keeps the status of an HTTP refusal whose JSON body is not valid UTF-8', async () => {
  const bytes = new Uint8Array([0x7b, 0xff, 0x7d]);
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(bytes, { status: 429, statusText: 'Too Many Requests' }))));
  const error = await getClientWithoutAuth().post('login/', {}).catch(e => e);
  expect(error).toMatchObject({ message: 'Too Many Requests', response: { status: 429 }, body: null });
});

it('copies tiny fragments into a bounded number of buffers as they arrive', async () => {
  const payload = 'déploy 🚀 '.repeat(512);
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const fragments = new WeakSet<Uint8Array>();
  const buffers = new Set<Uint8Array>();
  const set = Uint8Array.prototype.set;
  let copied = 0;
  let copiedBeforeClose = 0;
  const copy = vi.spyOn(Uint8Array.prototype, 'set').mockImplementation(function (
    this: Uint8Array, source: ArrayLike<number>, offset?: number,
  ) {
    if (source instanceof Uint8Array && fragments.has(source)) {
      buffers.add(this);
      copied += source.byteLength;
    }
    set.call(this, source, offset);
  });
  let offset = 0;
  const body = new ReadableStream({
    pull(controller) {
      if (offset === bytes.length) {
        copiedBeforeClose = copied;
        controller.close();
        return;
      }
      const fragment = bytes.subarray(offset, offset + 1);
      offset++;
      fragments.add(fragment);
      controller.enqueue(fragment);
    },
  }, { highWaterMark: 0 });
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(body))
    .mockResolvedValueOnce(new Response(bytes)));

  try {
    const client = getClientWithoutAuth();
    expect(await client.get<string>('deployments/')).toBe(payload);
    expect(await client.get<string>('deployments/')).toBe(payload);
    expect(copiedBeforeClose).toBe(bytes.length);
    expect(buffers.size).toBeLessThanOrEqual(Math.ceil(Math.log2(bytes.length)) + 1);
  } finally {
    copy.mockRestore();
  }
});
