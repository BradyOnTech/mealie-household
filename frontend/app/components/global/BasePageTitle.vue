<template>
  <header class="page-title" :class="{ 'page-title--divider': divider }">
    <div v-if="$slots.header" class="page-title__header">
      <slot name="header" />
    </div>
    <h1 class="page-title__title">
      <slot name="title">
        👋 Here's a Title
      </slot>
    </h1>
    <p v-if="$slots.default" class="page-title__dek">
      <slot />
    </p>
    <section v-if="$slots.content" class="page-title__content">
      <slot name="content" />
    </section>
  </header>
</template>

<script setup lang="ts">
defineProps({
  divider: {
    type: Boolean,
    default: false,
  },
});
</script>

<style scoped>
.page-title {
  margin-top: 16px;
  margin-bottom: 8px;
}

.page-title--divider {
  padding-bottom: 18px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
}

.page-title__title {
  margin: 0;
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-size: 2.5rem;
  font-weight: 420;
  line-height: 1.05;
  letter-spacing: -0.022em;
  text-wrap: balance;
}

.page-title__dek {
  max-width: 60ch;
  margin: 10px 0 0;
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-size: 1.0625rem;
  font-style: italic;
  font-weight: 350;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

.page-title__content {
  display: flex;
  margin-top: 16px;
}

@media (max-width: 599px) {
  .page-title__title {
    font-size: 2rem;
  }
}
</style>
