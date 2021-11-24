import { defineStore, acceptHMRUpdate } from "pinia";
import { Service, ServiceById, ServiceWithId, Message } from "../typings";

export const useServices = defineStore("services", {
  state: () => {
    const newService: Service = { name: "", collect: "", deploy: "" };
    return {
      services: {} as ServiceById,
      new: newService,
    };
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useServices, meta.hot));
      }
    },
    async addService() {
      const service = await this.client.addService(this.new);
      this.services[service.id] = service;
    },
    async deleteService(service_id: number) {
      const deletedId = await this.client.deleteService(service_id);
      if (deletedId) {
        delete this.services[deletedId];
      }
    },
    async fetchServices() {
      const services = await this.client.fetchServices();
      for (const service of services) {
        this.services[service.id] = service;
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
