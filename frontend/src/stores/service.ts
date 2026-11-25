import { markRaw } from "vue";
import { getClient } from "./httpClient";
import { serviceSnapshot, serviceNamesSnapshot, serviceToken, syncReceipt, syncRefusal, type SyncReceipt, type SyncRefusal } from "../restAdmission";
import { rememberSession } from "./session";
import { defineStore, acceptHMRUpdate } from "pinia";
import { Service, ServiceById, ServiceWithId, Message } from "../typings";

export type { SyncRefusal } from "../restAdmission";

/**
 * This store is used to store information about services. And
 * to add new services. And to retrieve service tokens which can
 * be used to start deployments.
 *
 * The reason why we have to add services is because we need to
 * be authenticated as a user to create a service. And we don't
 * want to store user access tokens in the ansible vault for now.
 */
export const useServices = defineStore("services", {
  state: () => {
    return {
      /**
       * Services are retrievable by id from this object.
       */
      services: {} as ServiceById,
      fetchGeneration: 0,
      pendingFetches: [] as Set<number>[],
      servicesLoading: false,
      servicesError: "",
      deleteErrors: {} as Record<number, string>,
      pendingDeletes: new Map<number, { removed: boolean }>(),
      /**
       * Error message received from backend when trying to fetch
       * a service token.
       */
      serviceTokenErrorMessage: "",
      /**
       * Set when the backend requests confirmation of the deletion candidates.
       * Cleared on the next sync attempt.
       */
      syncRefusal: null as SyncRefusal | null,
      syncReceipt: null as SyncReceipt | null,
      /**
       * Error message of a failed services sync (other than a refusal).
       */
      syncErrorMessage: "",
      syncGeneration: 0,
      /**
       * List of available service names.
       */
      serviceNames: [] as string[],
      serviceNamesGeneration: 0,
      serviceNamesLoading: false,
      serviceNamesError: "",
      client: getClient(),
    };
  },
  getters: {
    /**
     * Only services which are known to the backend can be added.
     * To choose a valid service name, users have to know which ones
     * are available. This method fetches all available names from
     * the backend.
     *
     * @returns availableServiceNames {string[]} - An array of valid service names from backend
     */
    getAvailableServiceNames: (state): string[] => {
      const availableServiceNames: string[] = [];
      const addedServiceNames = new Set(
        Object.values(state.services).map((service) => service.name)
      );
      for (const serviceName of state.serviceNames) {
        if (!addedServiceNames.has(serviceName)) {
          availableServiceNames.push(serviceName);
        }
      }
      return availableServiceNames;
    },
    /**
     * Returns sorted list of all services.
     *
     * @returns services {Service[]} - An array of services
     */
    getServices: (state): ServiceWithId[] => {
      return Object.values(state.services).sort((a, b) => {
        return a.name.localeCompare(b.name);
      })
    },
  },
  actions: {
    /**
     * Support for HMR
     * @param {any} meta
     */
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useServices, meta.hot));
      }
    },
    /**
     * Sync services between filesystem and database on the backend.
     *
     * The backend can require confirmation of the current deletion candidates.
     * @param confirmation - Confirmation from the refusal shown to the user
     * @returns synced {boolean} - Whether the sync succeeded
     */
    async syncServices(confirmation?: string): Promise<boolean> {
      this.syncRefusal = null;
      this.syncReceipt = null;
      this.syncErrorMessage = "";
      const isCurrentSession = rememberSession();
      const generation = ++this.syncGeneration;
      const isCurrent = () => isCurrentSession() && generation === this.syncGeneration;
      let response: unknown;
      try {
        response = await this.client.post<unknown>(
          "/services/sync",
          undefined,
          confirmation === undefined ? {} : { query: { force: "true", confirmation } }
        );
      } catch (err: any) {
        if (!isCurrent()) {
          return false;
        }
        const detail = err?.body?.detail;
        if (err?.response?.status === 409) {
          this.syncRefusal = syncRefusal(detail);
          if (!this.syncRefusal) this.syncErrorMessage = "Services sync failed";
        } else {
          const reason = typeof detail === "string" ? detail : err?.message;
          this.syncErrorMessage = `Services sync failed${reason ? ": " + reason : ""}`;
        }
        return false;
      }

      if (!isCurrent()) return false;
      try {
        this.syncReceipt = syncReceipt(response);
      } catch {
        this.syncErrorMessage = "Could not verify the services sync receipt. Refresh services before retrying.";
        return false;
      }
      await this.fetchServices();
      return isCurrent();
    },
    /** Delete only the requested row after a confirmed current-session response. */
    async deleteService(serviceId: number): Promise<boolean> {
      if (this.pendingDeletes.has(serviceId)) return false;
      const isCurrentSession = rememberSession();
      const attempt = markRaw({ removed: false });
      this.pendingDeletes.set(serviceId, attempt);
      const ownsAttempt = () => this.pendingDeletes.get(serviceId) === attempt;
      delete this.deleteErrors[serviceId];
      try {
        await this.client.delete(`/services/${serviceId}`);
        if (!isCurrentSession() || !ownsAttempt()) return false;
        if (attempt.removed) return true;
        for (const pending of this.pendingFetches) pending.add(serviceId);
        delete this.services[serviceId];
        delete this.deleteErrors[serviceId];
        return true;
      } catch (error: any) {
        if (isCurrentSession() && ownsAttempt() && !attempt.removed) {
          this.deleteErrors[serviceId] = error?.response?.status === 409
            ? "Cannot delete this service while a deployment is running. Wait for it to finish and retry."
            : error?.response?.status === 404
              ? "This service no longer exists. Refresh services."
              : "Could not confirm deletion. Refresh services before retrying.";
        }
        return false;
      } finally {
        if (ownsAttempt()) this.pendingDeletes.delete(serviceId);
      }
    },
    /**
     * Fetch all services from the backend. Used to display the list
     * of services.
     */
    async fetchServices(ownsRefresh: () => boolean = () => true) {
      const isCurrentSession = rememberSession();
      const generation = ++this.fetchGeneration;
      const isCurrent = () => isCurrentSession() && ownsRefresh() && generation === this.fetchGeneration;
      const changed = markRaw(new Set<number>());
      this.pendingFetches.push(changed);
      this.servicesLoading = true;
      this.servicesError = "";
      try {
        const services = await this.client.get<unknown>("services/");
        if (!isCurrent()) return;
        const snapshot: ServiceById = {};
        for (const service of Object.values(serviceSnapshot(services))) {
          if (!changed.has(service.id)) snapshot[service.id] = service;
        }
        for (const id of changed) {
          if (this.services[id]) snapshot[id] = this.services[id];
        }
        this.services = snapshot;
        for (const id of Object.keys(this.deleteErrors)) {
          if (!snapshot[Number(id)]) delete this.deleteErrors[Number(id)];
        }
      } catch {
        if (isCurrent()) this.servicesError = "Could not load services. Try again.";
      } finally {
        this.pendingFetches = this.pendingFetches.filter(pending => pending !== changed);
        if (isCurrentSession() && generation === this.fetchGeneration) this.servicesLoading = false;
      }
    },
    /**
     * Fetch all available service names from backend and store
     * them in the store.
     */
    async fetchServiceNames(ownsRefresh: () => boolean = () => true) {
      const isCurrentSession = rememberSession();
      const generation = ++this.serviceNamesGeneration;
      const isCurrent = () => isCurrentSession() && ownsRefresh() && generation === this.serviceNamesGeneration;
      this.serviceNamesLoading = true;
      this.serviceNamesError = "";
      try {
        const names = await this.client.get<unknown>("services/names/");
        if (isCurrent()) this.serviceNames = serviceNamesSnapshot(names);
      } catch {
        if (isCurrent()) this.serviceNamesError = "Could not load service names. Try again.";
      } finally {
        if (isCurrentSession() && generation === this.serviceNamesGeneration) this.serviceNamesLoading = false;
      }
    },
    /**
     * Fetch a service token for a service. This service token then can
     * be used to start deployments for a service. The origin can be set
     * to generate a token for a specific origin like GitHub. Save the
     * error message in store and return null on error.
     *
     * @param serviceName {string} - The name of the service for the service token
     * @param origin {string} - The origin of the service token (frontend, github)
     * @param expirationInDays {number} - The expiration of the service token in days (1 - 90 by default)
     * @param onError optional request-local error callback instead of shared list feedback
     * @returns serviceToken {string | null} - The service token or null on error
     */
    async fetchServiceToken(
      serviceName: string,
      origin: string,
      expirationInDays: number = 1,
      onError?: (message: string) => void
    ): Promise<string | null> {
      if (!onError) this.serviceTokenErrorMessage = "";
      const isCurrentSession = rememberSession();
      try {
        const response = await this.client.post<unknown>("service-token", {
          service: serviceName,
          origin: origin,
          expiration_in_days: expirationInDays,
        });
        // a token that arrives after logout is not handed out anymore
        return isCurrentSession() ? serviceToken(response) : null;
      } catch (err: any) {
        if (!isCurrentSession()) {
          return null;
        }
        const status = err?.response?.status;
        const message = status === 403
          ? "Service token issuance requires an administrator."
          : status === 404
          ? "The selected service no longer exists. Refresh services before retrying."
          : "Could not issue a service token. Check your permissions and inputs, then retry.";
        if (onError) onError(message);
        else this.serviceTokenErrorMessage = message;
        return null;
      }
    },
    /**
     * Event handler which is triggered by a message from the backend
     * which has the type "service". Services can be added, updated or
     * deleted.
     *
     * @param message {Message} the message which is received from the backend
     */
    onMessage(message: Message) {
      if (message.type === "service") {
        const service = message as ServiceWithId;
        for (const pending of this.pendingFetches) pending.add(service.id);
        if (service.deleted) {
          delete this.services[service.id];
          const attempt = this.pendingDeletes.get(service.id);
          if (attempt) attempt.removed = true;
          delete this.deleteErrors[service.id];
        } else {
          this.services[service.id] = service;
        }
      }
    },
  },
});
