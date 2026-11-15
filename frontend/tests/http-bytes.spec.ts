import { vi } from 'vitest';
import { initPinia } from './conftest';
import { getClientWithoutAuth } from '../src/stores/httpClient';
const limit = 1024 * 1024;
beforeEach(() => initPinia());
afterEach(() => vi.unstubAllGlobals());
it.each([{}, { 'Content-Length': '1' }, { 'Content-Length': String(limit + 1) }])('bounds streamed success/error bodies despite headers: %j', async headers => {
  for (const status of [200, 400]) {
    let reads = 0;
    const cancel = vi.fn();
    const body = new ReadableStream({
      pull(controller) { if (reads === 20) { controller.close(); return; } reads++; controller.enqueue(new Uint8Array(64 * 1024)); }, cancel,
    }, { highWaterMark: 0 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status, headers: headers as Record<string, string> })));
    await expect(getClientWithoutAuth().get('deployments/')).rejects.toThrow(/response.*large/i);
    expect(reads).toBeLessThanOrEqual(17);
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
