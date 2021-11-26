import { mande } from 'mande';
import { useSettings } from './config';
import { useAuth } from './auth';


export const getClient = () => {
    const auth = useAuth();
    const settings = useSettings();
    const client = mande(settings.api);
    client.options.headers.Authorization = `Bearer ${auth.accessToken}`;
    return client;
}
