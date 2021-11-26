import { mande } from "mande";
import { useAuth } from "./auth";
import { useSettings } from "./config";

export const getClient = () => {
  const auth = useAuth();
  const settings = useSettings();
  const client = mande(settings.api);
  client.options.headers.Authorization = `Bearer ${auth.accessToken}`;
  return client;
};
