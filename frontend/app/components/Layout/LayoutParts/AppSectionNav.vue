<template>
  <nav class="app-section-nav d-print-none" :aria-label="label">
    <div class="app-section-nav__inner">
      <span v-if="label" class="app-section-nav__label">{{ label }}</span>
      <NuxtLink
        v-for="link in links"
        :key="link.key"
        :to="link.to"
        class="app-section-nav__link"
        :class="{ 'app-section-nav__link--active': isActive(link.to) }"
      >
        {{ link.title }}
      </NuxtLink>
    </div>
  </nav>
</template>

<script setup lang="ts">
import type { AppNavLink } from "~/composables/use-app-navigation";

defineProps<{
  links: AppNavLink[];
  label?: string;
}>();

const route = useRoute();

function isActive(to: string) {
  return route.path === to || route.path.startsWith(`${to}/`);
}
</script>

<style scoped>
.app-section-nav {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-background));
}

.app-section-nav__inner {
  display: flex;
  align-items: stretch;
  gap: 24px;
  max-width: 1296px;
  margin-inline: auto;
  padding-inline: var(--paper-gutter);
  overflow-x: auto;
  scrollbar-width: none;
}

.app-section-nav__inner::-webkit-scrollbar {
  display: none;
}

.app-section-nav__label {
  display: flex;
  align-items: center;
  padding-right: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-tomato));
  white-space: nowrap;
}

.app-section-nav__link {
  display: flex;
  align-items: center;
  height: 46px;
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
  font-size: 0.875rem;
  font-weight: 500;
  color: rgb(var(--v-theme-ink-muted));
  text-decoration: none;
  white-space: nowrap;
}

.app-section-nav__link:hover {
  color: rgb(var(--v-theme-on-background));
}

.app-section-nav__link--active {
  color: rgb(var(--v-theme-on-background));
  border-bottom-color: rgb(var(--v-theme-on-background));
  font-weight: 600;
}
</style>
