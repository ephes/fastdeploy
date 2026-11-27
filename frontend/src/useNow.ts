import { onBeforeUnmount, ref, type Ref } from "vue";

/** The current time, refreshed while the calling component is mounted. */
export function useNow(intervalMs: number): Ref<number> {
  const now = ref(Date.now());
  const timer = setInterval(() => { now.value = Date.now(); }, intervalMs);
  onBeforeUnmount(() => clearInterval(timer));
  return now;
}
