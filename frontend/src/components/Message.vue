<script setup lang="ts">

import {ref, watchEffect, onMounted} from "vue";

const props = defineProps<{ message: Message }>();
const item = ref(null)

watchEffect(() => {
  if (props.message.in_progress) {
    console.log("scroll to: ", props.message.name, item.value);
    if (item.value) {
      item.value.scrollIntoView({ behavior: "smooth" });
    }
  }
});
</script>

<template>
    <p ref="item" id="message">
        {{ message.name }} <br />
        in progress: {{ message.in_progress }} <br />
        done: {{ message.done }} <br />
        {{ message.state }} <br />
        {{ message.changed }}
    </p>
</template>
