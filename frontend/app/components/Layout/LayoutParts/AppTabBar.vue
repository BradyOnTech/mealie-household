<template>
  <!-- order -1 keeps the tabs on the bottom edge, below page-level bottom drawers -->
  <v-bottom-navigation
    grow
    :order="-1"
    :height="64"
    bg-color="background"
    class="app-tabbar d-print-none"
    :aria-label="$t('navigation.main')"
  >
    <v-btn
      v-for="link in tabLinks"
      :key="link.key"
      :to="link.to"
      :active="!moreOpen && activeSection === link.key"
      color="tomato"
      :ripple="false"
    >
      <v-icon :icon="link.icon" size="22" />
      <span class="app-tabbar__label">{{ link.title }}</span>
    </v-btn>
    <v-btn
      :active="moreOpen"
      color="tomato"
      :ripple="false"
      @click="moreOpen = true"
    >
      <v-badge
        :model-value="!!newAnnouncements.length"
        color="tomato"
        dot
        offset-x="-2"
        offset-y="2"
      >
        <v-icon :icon="$globals.icons.dotsHorizontal" size="22" />
      </v-badge>
      <span class="app-tabbar__label">{{ $t("navigation.more") }}</span>
    </v-btn>
  </v-bottom-navigation>
  <AppMoreSheet v-model="moreOpen" />
</template>

<script setup lang="ts">
import AppMoreSheet from "~/components/Layout/LayoutParts/AppMoreSheet.vue";
import { useAnnouncements } from "~/composables/use-announcements";
import { useAppNavigation } from "~/composables/use-app-navigation";

const { primaryLinks, activeSection } = useAppNavigation();
const { newAnnouncements } = useAnnouncements();

/** Phones get three sections plus "More"; cookbooks live in the sheet. */
const tabLinks = computed(() => primaryLinks.value.filter(link => link.key !== "cookbooks"));
const moreOpen = ref(false);

const route = useRoute();
watch(() => route.fullPath, () => {
  moreOpen.value = false;
});
</script>

<style scoped>
.app-tabbar {
  border-top: 1px solid rgb(var(--v-theme-rule));
  box-shadow: none !important;
}

.app-tabbar :deep(.v-btn) {
  color: rgb(var(--v-theme-ink-muted));
  font-weight: 500;
  letter-spacing: 0;
  min-width: 0;
}

.app-tabbar :deep(.v-btn--active) {
  color: rgb(var(--v-theme-tomato));
  font-weight: 600;
}

.app-tabbar :deep(.v-btn__overlay) {
  display: none;
}

.app-tabbar :deep(.v-btn__content) {
  gap: 3px;
}

.app-tabbar__label {
  font-size: 0.6875rem;
  line-height: 1.1;
  white-space: nowrap;
}
</style>
