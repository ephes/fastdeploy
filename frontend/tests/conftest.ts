import { createApp } from "vue";
import { setActivePinia, createPinia } from "pinia";

export function createEvent(data: any): MessageEvent {
  return { data: JSON.stringify(data) } as MessageEvent;
}

export function initPinia() {
  const app = createApp({});
  const pinia = createPinia();
  app.use(pinia);
  setActivePinia(pinia);
}
