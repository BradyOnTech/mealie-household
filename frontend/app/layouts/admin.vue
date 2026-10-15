<template>
  <v-app>
    <TheSnackbar />

    <AppHeader />

    <v-main class="app-main" :class="{ 'app-main--tabbar': showTabBar }">
      <AppSectionNav :links="adminLinks" :label="$t('settings.admin-settings')" />
      <NuxtPage />
    </v-main>
    <AppTabBar v-if="showTabBar" />
  </v-app>
</template>

<script setup lang="ts">
import AppHeader from "@/components/Layout/LayoutParts/AppHeader.vue";
import AppSectionNav from "@/components/Layout/LayoutParts/AppSectionNav.vue";
import AppTabBar from "@/components/Layout/LayoutParts/AppTabBar.vue";
import TheSnackbar from "~/components/Layout/LayoutParts/TheSnackbar.vue";
import type { AppNavLink } from "~/composables/use-app-navigation";
import { useGlobalI18n } from "~/composables/use-global-i18n";

const i18n = useGlobalI18n();
const { smAndDown } = useDisplay();
const { $globals } = useNuxtApp();

const showTabBar = computed(() => smAndDown.value);

const adminLinks: AppNavLink[] = [
  {
    key: "site-settings",
    icon: $globals.icons.cog,
    to: "/admin/site-settings",
    title: i18n.t("sidebar.site-settings"),
  },
  {
    key: "users",
    icon: $globals.icons.user,
    to: "/admin/manage/users",
    title: i18n.t("user.users"),
  },
  {
    key: "households",
    icon: $globals.icons.household,
    to: "/admin/manage/households",
    title: i18n.t("household.households"),
  },
  {
    key: "groups",
    icon: $globals.icons.group,
    to: "/admin/manage/groups",
    title: i18n.t("group.groups"),
  },
  {
    key: "backups",
    icon: $globals.icons.database,
    to: "/admin/backups",
    title: i18n.t("sidebar.backups"),
  },
  {
    key: "maintenance",
    icon: $globals.icons.wrench,
    to: "/admin/maintenance",
    title: i18n.t("sidebar.maintenance"),
  },
  {
    key: "openai",
    icon: $globals.icons.robot,
    to: "/admin/debug/openai",
    title: i18n.t("admin.openai"),
  },
  {
    key: "parser",
    icon: $globals.icons.slotMachine,
    to: "/admin/debug/parser",
    title: i18n.t("sidebar.parser"),
  },
];
</script>
