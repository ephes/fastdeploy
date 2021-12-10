<script setup lang="ts">

import { Step } from "../typings";
import { ref, watchEffect, computed } from "vue";

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
 * Scroll to step if it's in progress
 */
watchEffect(() => {
  if (props.step.inProgress) {
    console.log("scroll to: ", props.step.id, el.value);
    if (el.value) {
      el.value.scrollIntoView({ behavior: "smooth" });
    }
  }
});
</script>

<template>
  <p ref="el" id="step">
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
