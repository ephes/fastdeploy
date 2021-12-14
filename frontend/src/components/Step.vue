<script setup lang="ts">

import { Step } from "../typings";
import { useSteps } from "../stores/step";
import { ref, watchEffect, computed } from "vue";

const stepsStore = useSteps();
const props = defineProps<{ step: Step }>();
const el = ref<null | HTMLElement>(null);

/**
 * Calculate step duration
 */
const duration = computed(() => {
  if (props.step.finished && props.step.started) {
    return (props.step.finished as any - (props.step.started as any)) / 1000;
  }
});

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

/**
 * Get the css class for the step.
 *
 * @param step {Step}
 * @returns cssClass {string}
 */
function getStepClass(step: Step): string {
  if (step.inProgress) {
    return "in-progress";
  }
  if (step.finished) {
    return "finished";
  }
  return "not-started";
}
</script>

<template>
  <p :class="getStepClass(step)" ref="el" id="step">
    {{ step.deploymentId }} {{ step.id }} {{ step.name }}
    <br />
    duration: {{ duration }}
    <br />
    in progress: {{ step.inProgress }}
    <br />
    done: {{ step.done }}
    <br />
    {{ step.state }}
    <br />
    {{ step.changed }}
  </p>
</template>
<style scoped>
.not-started {
  background-color: #a8b313;
}
.in-progress {
  background-color: #ffd700;
}
.finished {
  background-color: #00ff00;
}
</style>
