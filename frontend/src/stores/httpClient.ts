import { mande, MandeInstance, Options } from "mande";
import { useAuth } from "./auth";
import { useSettings } from "./config";

/**
 * The HttpClient is used to make requests to the backend.
 * It's just a wrapper around the mande, which is just a wrapper
 * around the fetch function. Maybe we just use fetch directly
 * later on.
 */

export type HttpClient = MandeInstance;

/** Whole request budget, including reading/decoding the response body. */
export const REQUEST_TIMEOUT_MS = 30_000;

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
export const getClientWithoutAuth = (): HttpClient => {
  const client = mande(useSettings().api);
  for (const method of ["get", "delete", "post", "put", "patch"] as const) {
    const send = client[method].bind(client) as (...args: any[]) => Promise<unknown>;
    client[method] = ((...args: any[]) => {
      const hasUrl = typeof args[0] === "string" || typeof args[0] === "number";
      const reads = method === "get" || method === "delete";
      const url = hasUrl ? args[0] : "";
      const data = hasUrl ? args[1] : args[0];
      const options: Options | undefined = reads
        ? (hasUrl ? args[1] : args[0])
        : (hasUrl ? args[2] : args[1]);
      return withDeadline(signal => reads
        ? send(url, { ...options, signal })
        : send(url, data, { ...options, signal }), options?.signal);
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
  const client = getClientWithoutAuth();
  const auth = useAuth();
  if (auth.accessToken) {
    client.options.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  return client;
};
