import { mande, MandeInstance } from "mande";
import { useAuth } from "./auth";
import { useSettings } from "./config";

/**
 * The HttpClient is used to make requests to the backend.
 * It's just a wrapper around the mande, which is just a wrapper
 * around the fetch function. Maybe we just use fetch directly
 * later on.
 */

export type HttpClient = MandeInstance;

/**
 * Just a dummy function to make the type checker happy. Only
 * get's triggered via tests, because fetch is not available
 * when called from jest.
 *
 * @param input {RequestInfo}
 * @param init {RequestInit | undefined }
 * @returns response { Promise<Response> }
 */
const dummyFetch = async (
  input: RequestInfo,
  init?: RequestInit | undefined
) => {
  // just a dummy function because fetch is not
  // available during tests
  return new Response();
};

/**
 * Use settings from config store and set fetch for tests.
 * Otherwise just mande.
 *
 * @returns client {HttpClient} unauthenticated client
 */
export const getClientWithoutAuth = ():HttpClient => {
  const settings = useSettings();
  const localFetch = typeof fetch != 'undefined' ? fetch : dummyFetch;
  const client:HttpClient = mande(settings.api, {}, localFetch);
  return client;
};

/**
 * Use access token from auth store to turn an unauthenticated
 * into an authenticated client.
 *
 * @returns client {HttpClient} authenticated client
 */
export const getClient = ():HttpClient => {
  const client = getClientWithoutAuth();
  const auth = useAuth();
  client.options.headers.Authorization = `Bearer ${auth.accessToken}`;
  return client;
};
