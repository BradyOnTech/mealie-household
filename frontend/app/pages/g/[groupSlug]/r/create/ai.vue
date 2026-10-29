<template>
  <div />
</template>

<script setup lang="ts">
// Every kind of import now starts from the one import box, which works out what it's been given.
// Kept as a redirect so existing links and bookmarks still land somewhere useful.
definePageMeta({
  redirect: to => ({ path: `/g/${to.params.groupSlug}/r/create/url`, query: to.query }),
});
</script>
