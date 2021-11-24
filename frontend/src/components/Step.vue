<script setup lang="ts">

import { Step } from "../typings";
import {ref, watchEffect } from "vue";

const props = defineProps<{ step: Step }>();
const el = ref<null | HTMLElement>(null);

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
        {{ step.deploymentId }} {{ step.id }} {{ step.name }} <br />
        created: {{ step.created }} <br />
        started: {{ step.started }} <br />
        finished: {{ step.finished }} <br />
        in progress: {{ step.inProgress }} <br />
        done: {{ step.done }} <br />
        {{ step.state }} <br />
        {{ step.changed }}
    </p>
</template>
