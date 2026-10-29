<template>
  <div />
</template>

<script setup lang="ts">
definePageMeta({
  redirect: to => ({ path: `/g/${to.params.groupSlug}/r/create/url`, query: to.query }),
});
</script>
