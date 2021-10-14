<script setup lang="ts">

defineProps<{ message: Message }>();
</script>

<template>
    <div id="message">{{ message.message }}</div>
</template>
