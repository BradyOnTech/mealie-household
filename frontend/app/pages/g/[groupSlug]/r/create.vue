<template>
  <div class="recipe-create paper-container">
    <NuxtPage />
  </div>
</template>

<script setup lang="ts">
definePageMeta({
  middleware: ["group-only"],
});
</script>
