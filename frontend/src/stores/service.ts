import { getClient } from "./sharedGetters";
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
  getters: {
    getClient: () => getClient,
  },
  actions: {
    useHMRUpdate(meta: any) {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useServices, meta.hot));
      }
    },
    async addService() {
      this.getClient().post<ServiceWithId>(
        "/services",
        this.new
      ).then(service => {
        this.services[service.id] = service;
        this.new = { name: "", collect: "", deploy: "" };
      }).catch(err => {
        console.log("Error adding service", err);
      });
    },
    async deleteService(service_id: number) {
      this.getClient()
        .delete<number>(`/services/${service_id}`)
        .then((deletedId) => {
          delete this.services[deletedId];
        }).catch((err) => {
          console.log("delete service error: ", err);
        });
    },
    async fetchServices() {
      const services = await (<Promise<ServiceWithId[]>>(
        this.getClient().get("services")
      ));
      console.log("got services: ", services);
      for (const service of services) {
        this.services[service.id] = service;
      }
    },
    async fetchServiceToken(serviceName: string, origin: string) {
      const response = await (<Promise<{ service_token: string }>>(
        this.getClient().post("service-token", {
          service: serviceName,
          origin: origin,
        })
      ));
      return response.service_token;
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
