import { getClient } from "./httpClient";
import { defineStore, acceptHMRUpdate } from "pinia";
import { Service, ServiceById, ServiceWithId, Message } from "../typings";

export const useServices = defineStore("services", {
  state: () => {
    const newService: Service = { name: "" };
    return {
      services: {} as ServiceById,
      new: newService,
      serviceTokenErrorMessage: "",
      serviceNames: [] as string[],
      client: getClient(),
    };
  },
  getters: {
    getAvailableServiceNames: (state): string[] => {
      const availableServiceNames: string[] = [];
      const addedServiceNames = new Set(
        Object.values(state.services).map((service) => service.name)
      );
      for (const serviceName of state.serviceNames) {
        if (!(addedServiceNames.has(serviceName))) {
          availableServiceNames.push(serviceName);
        }
      }
      return availableServiceNames;
    },
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useServices, meta.hot));
      }
    },
    async addService() {
      console.log("add service breakpoint");
      this.client
        .post<ServiceWithId>("/services/", this.new)
        .then((service) => {
          this.services[service.id] = service;
          this.new = { name: "" };
        })
        .catch((err) => {
          console.log("Error adding service", err);
        });
    },
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
    async fetchServices() {
      const services = await (<Promise<ServiceWithId[]>>(
        this.client.get("services/")
      ));
      for (const service of services) {
        this.services[service.id] = service;
      }
    },
    async fetchServiceNames() {
      this.client.get<string[]>("services/names/").then((names) => {
        this.serviceNames = names;
      });
    },
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
