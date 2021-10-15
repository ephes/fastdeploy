<script setup lang="ts">

defineProps<{ message: Message }>();
</script>

<template>
    <p id="message">
        {{ message.name }} <br />
        {{ message.state }} <br />
        {{ message.changed }}
    </p>
</template>
