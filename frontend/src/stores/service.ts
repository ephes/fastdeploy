import { defineStore, acceptHMRUpdate } from "pinia";
import { Service, Message } from "../typings";

export function createService(message: any): Service {
  const service: Service = {
    id: message.id,
    name: message.name,
    collect: message.collect,
    deploy: message.deploy,
    deleted: message.deleted,
  };
  return service;
}

export const useServices = defineStore("services", {
  state: () => {
    return {
      services: new Map<number | undefined, Service>(),
      logMessages: false as boolean,
      messages: [] as any[],
    };
  },
  getters: {
    foo: (state) => {
      return "bar";
    },
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useServices, meta.hot));
      }
    },
    async addService(service: Service) {
      const serviceWithId = await this.client.addService(service)
      const newService = createService(serviceWithId);
      this.services.set(newService.id, newService);
    },
    async deleteService(id: number) {
      const deletedId = await this.client.deleteService(id);
      if (deletedId) {
        this.services.delete(deletedId);
      }
    },
    async fetchServices() {
      const services = await this.client.fetchServices();
      for (const service of services) {
        this.services.set(service.id, createService(service));
      }
    },
    onMessage(message: Message) {
      console.debug("on message in services store: ", message);
      if (this.logMessages) {
        this.messages.push(message);
      }
      if (message.type === "service") {
        const service = createService(message);
        if (service.deleted) {
          this.services.delete(service.id);
        } else {
          this.services.set(service.id, service);
        }
      }
    },
  },
});
