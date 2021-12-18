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
  return step.state
}
</script>

<template>
  <p :class="step.state" ref="el" id="step">
    {{ step.name }}
    <br />
    duration: {{ duration }}
    <br />
    {{ step.state }}
    <br />
    {{ step.changed }}
    <div v-if="step.message">
      <br />
      {{ step.message }}
    </div>
  </p>
</template>
<style scoped>
.pending {
  background-color: #d9dbbc;
}
.running {
  background-color: #f7e604;
}
.success {
  background-color: #00ff00;
}
.failure {
  background-color: #ff1326a6;
}

</style>
