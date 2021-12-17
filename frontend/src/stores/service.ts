import { getClient } from "./httpClient";
import { defineStore, acceptHMRUpdate } from "pinia";
import { Service, ServiceById, ServiceWithId, Message } from "../typings";

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
      /**
       * Error message received from backend when trying to fetch
       * a service token.
       */
      serviceTokenErrorMessage: "",
      /**
       * List of available service names.
       */
      serviceNames: [] as string[],
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
    getServices: (state): Service[] => {
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
     */
    async syncServices() {
      this.client
        .post("/services/sync")
        .then(() => {
          console.log("Services synced");
        })
        .catch((err) => {
          console.log("Error syncing services", err)
        });
    },
    /**
     * Delete a service from the store. This is called by the event
     * handler when a service message is received which has the deleted
     * attribute set to true.
     *
     * @param service_id {number} - The id of the service to delete
     */
    async deleteService(service_id: number) {
      this.client
        .delete<number>(`/services/${service_id}`)
        .then((deletedId) => {
          delete this.services[deletedId];
        })
        .catch((err) => {
          console.log("delete service error: ", err);
        });
    },
    /**
     * Fetch all services from the backend. Used to display the list
     * of services.
     */
    async fetchServices() {
      const services = await (<Promise<ServiceWithId[]>>(
        this.client.get("services/")
      ));
      for (const service of services) {
        this.services[service.id] = service;
      }
    },
    /**
     * Fetch all available service names from backend and store
     * them in the store.
     */
    async fetchServiceNames() {
      this.client.get<string[]>("services/names/").then((names) => {
        this.serviceNames = names;
      });
    },
    /**
     * Fetch a service token for a service. This service token then can
     * be used to start deployments for a service. The origin can be set
     * to generate a token for a specific origin like GitHub. Save the
     * error message in store and return null on error.
     *
     * @param serviceName {string} - The name of the service for the service token
     * @param origin {string} - The origin of the service token (frontend, github)
     * @param expirationInDays {number} - The expiration of the service token in days (0 - 180)
     * @returns serviceToken {string | null} - The service token or null on error
     */
    async fetchServiceToken(
      serviceName: string,
      origin: string,
      expirationInDays: number = 1
    ) {
      this.serviceTokenErrorMessage = "";
      try {
        const response = await (<Promise<{ service_token: string }>>(
          this.client.post("service-token/", {
            service: serviceName,
            origin: origin,
            expiration_in_days: expirationInDays,
          })
        ));
        return response.service_token;
      } catch (err: any) {
        this.serviceTokenErrorMessage =
          err.message + " " + JSON.stringify(err.body);
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
        if (service.deleted) {
          delete this.services[service.id];
        } else {
          this.services[service.id] = service;
        }
      }
    },
  },
});
