<template>
  <v-card
    variant="outlined"
    :to="link.to"
    height="100%"
    class="profile-link-card d-flex flex-column mt-4"
  >
    <v-card-title class="profile-link-card__title">
      <slot name="title" />
    </v-card-title>
    <v-card-text class="profile-link-card__text">
      <slot name="default" />
    </v-card-text>
    <v-spacer />
    <div class="profile-link-card__action">
      {{ link.text }} →
    </div>
  </v-card>
</template>

<script setup lang="ts">
interface LinkProp {
  text: string;
  url?: string;
  to: string;
}

defineProps({
  link: {
    type: Object as () => LinkProp,
    required: true,
  },
  image: {
    type: String,
    required: false,
    default: "",
  },
});
</script>

<style scoped>
.profile-link-card {
  padding: 6px 4px 4px;
  background: rgb(var(--v-theme-surface));
}

.profile-link-card__title {
  font-size: 1.25rem;
  white-space: normal;
}

.profile-link-card__text {
  font-size: 0.9375rem;
  color: rgb(var(--v-theme-ink-muted));
}

.profile-link-card__action {
  padding: 4px 16px 14px;
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-tomato));
}
</style>
