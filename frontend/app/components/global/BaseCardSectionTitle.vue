<template>
  <div
    class="section-title"
    :class="{ 'section-title--spaced': section }"
  >
    <h2 class="section-title__heading" :class="`section-title__heading--${size}`">
      <slot name="prepend-title" />
      <v-icon
        v-if="icon"
        size="small"
        class="section-title__icon"
      >
        {{ icon }}
      </v-icon>
      {{ title }}
      <slot name="append-title" />
    </h2>
    <p v-if="$slots.default" class="section-title__text">
      <slot />
    </p>
  </div>
</template>

<script setup lang="ts">
type Size = "large" | "medium" | "small";

defineProps({
  title: {
    type: String,
    required: true,
  },
  size: {
    type: String as () => Size,
    default: "large",
  },
  icon: {
    type: String,
    default: "",
  },
  section: {
    type: Boolean,
    default: false,
  },
});
</script>

<style scoped>
.section-title {
  margin-bottom: 14px;
}

.section-title--spaced {
  margin-top: 36px;
}

.section-title__heading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding-bottom: 6px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-weight: 450;
  line-height: 1.2;
  letter-spacing: -0.01em;
}

.section-title__heading--large {
  font-size: 1.5rem;
}

.section-title__heading--medium {
  font-size: 1.25rem;
}

.section-title__heading--small {
  font-size: 1.0625rem;
}

.section-title__icon {
  color: rgb(var(--v-theme-tomato));
}

.section-title__text {
  max-width: 68ch;
  margin: 8px 0 0;
  font-size: 0.9375rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}
</style>
