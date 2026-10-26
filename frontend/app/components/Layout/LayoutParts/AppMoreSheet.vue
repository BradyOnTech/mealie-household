<template>
  <v-bottom-sheet v-model="open" max-height="88vh" scrollable>
    <v-card class="app-more-sheet">
      <div class="app-more-sheet__head">
        <span class="app-more-sheet__title">{{ $t("navigation.more") }}</span>
        <v-btn
          icon
          variant="text"
          size="small"
          :aria-label="$t('general.close')"
          @click="open = false"
        >
          <v-icon :icon="$globals.icons.close" />
        </v-btn>
      </div>
      <v-card-text class="pa-0">
        <v-list density="comfortable" bg-color="transparent" class="py-1">
          <template v-for="section in sections" :key="section.key">
            <v-list-subheader>{{ section.title }}</v-list-subheader>
            <v-list-item
              v-for="link in section.links"
              :key="link.key"
              :to="link.to"
              :prepend-icon="link.icon"
              :title="link.title"
              :subtitle="link.subtitle"
            />
          </template>
          <v-list-subheader>{{ $t("navigation.account") }}</v-list-subheader>
        </v-list>
        <AppAccountActions class="pb-4" />
      </v-card-text>
    </v-card>
  </v-bottom-sheet>
</template>

<script setup lang="ts">
import AppAccountActions from "~/components/Layout/LayoutParts/AppAccountActions.vue";
import { useAppNavigation, type AppNavSection } from "~/composables/use-app-navigation";

const open = defineModel<boolean>({ default: false });

const i18n = useI18n();
const { primaryLinks, moreSections, createLinks } = useAppNavigation();

const sections = computed<AppNavSection[]>(() => {
  const cookbooksIndex = primaryLinks.value.find(link => link.key === "cookbooks");
  const result = moreSections.value.map(section => ({ ...section, links: [...section.links] }));

  // The tab bar leaves Ask out, so it leads the sheet
  const ask = primaryLinks.value.find(link => link.key === "ask");
  const plan = result.find(section => section.key === "plan");
  if (ask && plan) {
    plan.links.unshift(ask);
  }

  if (cookbooksIndex) {
    const cookbookSection = result.find(section => section.key === "cookbooks");
    if (cookbookSection) {
      cookbookSection.links.unshift(cookbooksIndex);
    }
    else {
      result.push({ key: "cookbooks", title: cookbooksIndex.title, links: [cookbooksIndex] });
    }
  }

  if (createLinks.value.length) {
    result.push({ key: "create", title: i18n.t("navigation.add-recipe"), links: createLinks.value });
  }
  return result;
});
</script>

<style scoped>
.app-more-sheet {
  background: rgb(var(--v-theme-background));
  padding-bottom: env(safe-area-inset-bottom);
}

.app-more-sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 12px 10px 20px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.app-more-sheet__title {
  font-family: var(--paper-serif);
  font-size: 1.5rem;
  font-weight: 420;
  letter-spacing: -0.015em;
}
</style>
