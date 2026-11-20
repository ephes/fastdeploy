import { mande, MandeInstance, Options, ResponseAsTypes } from "mande";
import { useAuth } from "./auth";
import { useSettings } from "./config";
import { readStrictJson } from "../strictJson";

/**
 * The HttpClient is used to make requests to the backend.
 * It's just a wrapper around the mande, which is just a wrapper
 * around the fetch function. Maybe we just use fetch directly
 * later on.
 */

export type HttpClient = MandeInstance;

/** Whole request budget, including reading/decoding the response body. */
export const REQUEST_TIMEOUT_MS = 30_000;
export const MAX_RESPONSE_BYTES = 1024 * 1024;

/**
 * Request options plus an optional observer of the actual body bytes received.
 * It is called per streamed chunk before decoding; throwing from it cancels the body.
 */
export type BoundedOptions<R extends ResponseAsTypes = ResponseAsTypes> = Options<R> & { onBodyBytes?: (bytes: number) => void };

async function decodeBounded(
  response: Response, signal: AbortSignal, responseAs: Options['responseAs'], onBodyBytes?: (bytes: number) => void,
) {
  const reader = response.body?.getReader();
  const overflow = () => new Error('Server response is too large. Refresh before retrying.');
  if (!reader) return responseAs === 'response' ? response : null;
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener('abort', cancel, { once: true });
  try {
    if (Number(response.headers.get('Content-Length')) > MAX_RESPONSE_BYTES) throw overflow();
    const chunks: Uint8Array[] = [];
    let length = 0;
    while (true) {
      signal.throwIfAborted();
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_RESPONSE_BYTES) throw overflow();
      onBodyBytes?.(value.byteLength);
      chunks.push(value);
    }
    const bytes = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    if (responseAs === 'response') return new Response(bytes, { status: response.status, statusText: response.statusText, headers: response.headers });
    const text = new TextDecoder().decode(bytes);
    if (responseAs === 'text') return text;
    try { return readStrictJson(text); } catch { return null; }
  } catch (error) {
    cancel();
    throw error;
  } finally {
    signal.removeEventListener('abort', cancel);
    reader.releaseLock();
  }
}

async function withDeadline<T>(request: (signal: AbortSignal) => Promise<T>, caller?: AbortSignal | null): Promise<T> {
  if (caller?.aborted) throw caller.reason ?? new DOMException("Request cancelled", "AbortError");
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancel!: () => void;
  const interrupted = new Promise<never>((_resolve, reject) => {
    const abort = (reason: unknown) => {
      // Settle even when a transport does not cooperate with cancellation.
      reject(reason);
      controller.abort(reason);
    };
    cancel = () => abort(caller?.reason ?? new DOMException("Request cancelled", "AbortError"));
    caller?.addEventListener("abort", cancel, { once: true });
    timer = setTimeout(() => abort(new DOMException(
      "Request timed out. Refresh before retrying a deployment or sync.", "TimeoutError"
    )), REQUEST_TIMEOUT_MS);
  });
  try {
    return await Promise.race([interrupted, request(controller.signal)]);
  } finally {
    clearTimeout(timer);
    caller?.removeEventListener("abort", cancel);
  }
}

/** Keep mande's public overloads, with a fresh signal and options for each call. */
export const getClientWithoutAuth = (
  api = useSettings().api,
  isCurrent: () => boolean = () => useSettings().api === api,
): HttpClient => {
  const client = mande(api);
  const checkDestination = (response?: Response) => {
    if (isCurrent()) return;
    void response?.body?.cancel().catch(() => {});
    throw new Error('API destination or login session changed. Log in again.');
  };
  for (const method of ["get", "delete", "post", "put", "patch"] as const) {
    const send = client[method].bind(client) as (...args: any[]) => Promise<unknown>;
    client[method] = ((...args: any[]) => {
      const hasUrl = typeof args[0] === "string" || typeof args[0] === "number";
      const reads = method === "get" || method === "delete";
      const url = hasUrl ? args[0] : "";
      const data = hasUrl ? args[1] : args[0];
      const options: BoundedOptions | undefined = reads
        ? (hasUrl ? args[1] : args[0])
        : (hasUrl ? args[2] : args[1]);
      const { onBodyBytes, ...fetchOptions } = options ?? {};
      return withDeadline(async signal => {
        checkDestination();
        const boundedOptions = { ...fetchOptions, signal, responseAs: 'response' };
        let response: Response;
        try {
          response = await (reads ? send(url, boundedOptions) : send(url, data, boundedOptions)) as Response;
        } catch (error) {
          if (!(error instanceof Error) || !('response' in error)) {
            checkDestination();
            throw error;
          }
          response = (error as Error & { response: Response }).response;
        }
        checkDestination(response);
        const body = await decodeBounded(
          response, signal, options?.responseAs ?? client.options.responseAs ?? 'json', onBodyBytes,
        );
        checkDestination();
        if (!response.ok) {
          throw Object.assign(new Error(response.statusText), { response, body });
        }
        return body;
      }, options?.signal);
    }) as typeof client[typeof method];
  }
  return client;
};

/**
 * Use access token from auth store to turn an unauthenticated
 * into an authenticated client. Without an access token (not logged
 * in, or logged out) the client stays unauthenticated: it carries no
 * Authorization header at all.
 *
 * @returns client {HttpClient} authenticated client
 */
export const getClient = ():HttpClient => {
  const auth = useAuth();
  const api = useSettings().api;
  if (auth.accessToken && auth.authenticatedApi !== api) auth.endSession();
  const sessionId = auth.sessionId;
  const client = getClientWithoutAuth(api, () => useSettings().api === api && auth.sessionId === sessionId);
  if (auth.accessToken) {
    client.options.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  return client;
};
