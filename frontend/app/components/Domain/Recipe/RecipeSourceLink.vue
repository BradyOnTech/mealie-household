<template>
  <v-btn
    v-if="instagramUrl"
    :href="instagramUrl"
    target="_blank"
    rel="noopener noreferrer"
    :prepend-icon="$globals.icons.play"
    variant="tonal"
    color="primary"
  >
    {{ $t('recipe.watch-on-instagram') }}
  </v-btn>
</template>

<script setup lang="ts">
const props = defineProps<{ url?: string | null }>();

const instagramUrl = computed(() => {
  if (!props.url) return null;
  try {
    const url = new URL(props.url.trim());
    if (!["https:", "http:"].includes(url.protocol)) return null;
    if (url.hostname === "instagram.com" || url.hostname.endsWith(".instagram.com")) {
      return props.url.trim();
    }
  }
  catch {
    // Invalid or non-web source URLs should not become a video action.
  }
  return null;
});
</script>
