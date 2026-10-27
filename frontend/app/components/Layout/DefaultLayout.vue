<template>
  <v-app>
    <TheSnackbar />
    <AppHeader />
    <v-main class="app-main" :class="{ 'app-main--tabbar': showTabBar }">
      <NuxtPage />
    </v-main>
    <AppTabBar v-if="showTabBar" />
  </v-app>
</template>

<script setup lang="ts">
import AppHeader from "~/components/Layout/LayoutParts/AppHeader.vue";
import AppTabBar from "~/components/Layout/LayoutParts/AppTabBar.vue";
import TheSnackbar from "~/components/Layout/LayoutParts/TheSnackbar.vue";
import { useHouseholdMessageWatcher } from "~/composables/use-household-messages";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useWebPush } from "~/composables/use-web-push";

const { smAndDown } = useDisplay();
const { isOwnGroup } = useLoggedInState();

const showTabBar = computed(() => smAndDown.value && isOwnGroup.value);

useHouseholdMessageWatcher();
// Re-send this device's push subscription on every launch, since iOS can drop or replace it quietly
const webPush = useWebPush();
watch(isOwnGroup, (own) => {
  if (own) void webPush.refresh();
}, { immediate: true });
</script>

<style>
.app-main--tabbar {
  padding-bottom: calc(var(--v-layout-bottom) + env(safe-area-inset-bottom)) !important;
}

.app-tabbar.v-bottom-navigation {
  height: calc(64px + env(safe-area-inset-bottom)) !important;
  padding-bottom: env(safe-area-inset-bottom);
}
</style>
