<script setup lang="ts">

import { Step } from "../typings";
import { useSteps } from "../stores/step";
import { ref, watchEffect, computed } from "vue";
import { formatDuration } from "../format";

const stepsStore = useSteps();
const props = defineProps<{ step: Step }>();
const el = ref<null | HTMLElement>(null);

/**
 * Calculate step duration
 */
const duration = computed(() => {
  if (props.step.finished && props.step.started) {
    return formatDuration(props.step.started, props.step.finished);
  }
});
const stateLabels = { pending: "Waiting", running: "Running", success: "Done", failure: "Failed" };

/**
 * Scroll to step if it's the one before in progress.
 */
watchEffect(() => {
  //if (props.step.inProgress) {
  if (stepsStore.shouldScrollToStep(props.step)) {
    console.log("scroll to: ", props.step.id, el.value);
    if (el.value) {
      el.value.scrollIntoView({ behavior: "smooth" });
    }
  }
});

</script>

<template>
  <div class="step" :class="step.state" ref="el">
    <span class="node" aria-hidden="true"></span>
    <div class="line">
      <span class="name">{{ step.name }}</span>
      <span class="sr-only">{{ stateLabels[step.state] }}</span>
      <span v-if="duration" class="duration num"><span class="sr-only">duration: </span>{{ duration }}</span>
      <span v-else-if="step.state === 'running'" class="duration now">running</span>
    </div>
    <pre v-if="step.message" class="message" tabindex="0" role="region" :aria-label="`Output of ${step.name}`">{{ step.message }}</pre>
  </div>
</template>
<style scoped>
.step {
  position: relative;
  display: grid;
  grid-template-columns: 1.25rem minmax(0, 1fr);
  column-gap: 0.85rem;
  padding: 0.45rem 0;
  /* clear the sticky masthead */
  scroll-margin-top: 5rem;
}
/* The rail that connects a step to the next one. */
.step::before {
  content: "";
  position: absolute;
  top: 1.7rem;
  bottom: -0.45rem;
  left: calc(0.625rem - 1px);
  width: 2px;
  border-radius: 1px;
  background: var(--line);
}
.success::before { background: color-mix(in srgb, var(--ok) 45%, var(--line)); }

.node {
  position: relative;
  width: 1.25rem;
  height: 1.25rem;
  margin-top: 0.1rem;
  border-radius: 50%;
  border: 2px solid var(--idle);
  background: var(--bg);
}
.success .node { border-color: var(--ok); background: var(--ok); }
.failure .node { border-color: var(--fail); background: var(--fail); }
.running .node {
  border-color: color-mix(in srgb, var(--run-fill) 35%, var(--bg));
  border-top-color: var(--run-fill);
  animation: spin 0.9s linear infinite;
}
/* check mark */
.success .node::after {
  content: "";
  position: absolute;
  left: 5.5px;
  top: 2.5px;
  width: 5px;
  height: 9px;
  border: solid var(--bg);
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}
/* cross */
.failure .node::before,
.failure .node::after {
  content: "";
  position: absolute;
  left: 7px;
  top: 3px;
  width: 2px;
  height: 10px;
  border-radius: 1px;
  background: var(--bg);
  transform: rotate(45deg);
}
.failure .node::after { transform: rotate(-45deg); }

@keyframes spin {
  to { transform: rotate(360deg); }
}

.line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  min-height: 1.45rem;
}
.name { overflow-wrap: anywhere; }
.pending .name { color: var(--muted); }
.running .name, .failure .name { font-weight: 650; }
.failure .name { color: var(--fail); }
.duration {
  flex: none;
  color: var(--muted);
  font-size: 0.875rem;
}
.duration.now { color: var(--run); font-weight: 600; }

.message {
  grid-column: 2;
  margin: 0.4rem 0 0.35rem;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface);
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 22rem;
  overflow: auto;
}
.failure .message {
  border-color: color-mix(in srgb, var(--fail) 35%, var(--line));
  background: var(--fail-soft);
}
</style>
