<template>
  <v-menu location="bottom end" :offset="8" :close-on-content-click="true">
    <template #activator="{ props: menuProps }">
      <button
        type="button"
        class="app-account-menu__trigger"
        :aria-label="$t('navigation.account')"
        v-bind="menuProps"
      >
        <v-badge
          :model-value="!!newAnnouncements.length"
          color="tomato"
          dot
          offset-x="2"
          offset-y="2"
        >
          <AppInitialsAvatar :name="user?.fullName || user?.username || ''" size="36" />
        </v-badge>
      </button>
    </template>
    <v-card min-width="280" max-width="320">
      <AppAccountActions />
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import AppAccountActions from "~/components/Layout/LayoutParts/AppAccountActions.vue";
import AppInitialsAvatar from "~/components/Layout/LayoutParts/AppInitialsAvatar.vue";
import { useAnnouncements } from "~/composables/use-announcements";

const auth = useMealieAuth();
const user = computed(() => auth.user.value);
const { newAnnouncements } = useAnnouncements();
</script>

<style scoped>
.app-account-menu__trigger {
  appearance: none;
  background: none;
  border: 0;
  padding: 0;
  display: inline-flex;
  border-radius: 50%;
  cursor: pointer;
}

.app-account-menu__trigger:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}
</style>
