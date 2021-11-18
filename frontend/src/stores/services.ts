import { defineStore, acceptHMRUpdate } from "pinia";
import { Service } from "../typings";

export const useServices = defineStore("services", {
  state: () => {
    return {
      services: [] as Service[],
    };
  },
  getters: {
    foo: (state) => {
      return "bar";
    },
  },
  actions: {
    useHMRUpdate: (meta: any) => {
      if (meta.hot) {
        meta.hot.accept(acceptHMRUpdate(useServices, meta.hot));
      }
    },
    addService: (service: Service) => {
      console.log("add service: ", service);
    },
    onMessage: (message: any) => {
      console.debug("on message: ", message);
    },
  },
});
