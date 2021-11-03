<script setup lang="ts">

defineProps<{ message: Message }>();
</script>

<template>
    <p id="message">
        {{ message.name }} <br />
        in progress: {{ message.in_progress }} <br />
        done: {{ message.done }} <br />
        {{ message.state }} <br />
        {{ message.changed }}
    </p>
</template>
