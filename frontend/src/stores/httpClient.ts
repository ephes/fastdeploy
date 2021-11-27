import { mande, MandeInstance } from "mande";
import { useAuth } from "./auth";
import { useSettings } from "./config";

export type HttpClient = MandeInstance;

const dummyFetch = async (
  input: RequestInfo,
  init?: RequestInit | undefined
) => {
  // just a dummy function because fetch is not
  // available during tests
  return new Response();
};

export const getClientWithoutAuth = ():HttpClient => {
  const settings = useSettings();
  const localFetch = typeof fetch != 'undefined' ? fetch : dummyFetch;
  const client:HttpClient = mande(settings.api, {}, localFetch);
  return client;
};

export const getClient = ():HttpClient => {
  const client = getClientWithoutAuth();
  const auth = useAuth();
  client.options.headers.Authorization = `Bearer ${auth.accessToken}`;
  return client;
};
