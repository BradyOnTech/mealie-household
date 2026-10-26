<template>
  <v-app-bar
    :height="mdAndUp ? 68 : 56"
    flat
    color="background"
    class="app-masthead d-print-none"
  >
    <div class="app-masthead__inner">
      <v-btn
        v-if="backTarget && smAndDown"
        icon
        variant="text"
        size="small"
        class="app-masthead__back"
        :aria-label="$t('navigation.go-back')"
        @click="goBack"
      >
        <v-icon :icon="$globals.icons.chevronLeft" />
      </v-btn>
      <NuxtLink :to="homeLink" class="app-masthead__wordmark">
        Mealie
      </NuxtLink>

      <nav
        v-if="menu && mdAndUp && primaryLinks.length"
        class="app-masthead__nav"
        :aria-label="$t('navigation.main')"
      >
        <NuxtLink
          v-for="link in primaryLinks"
          :key="link.key"
          :to="link.to"
          class="app-masthead__link"
          :class="{ 'app-masthead__link--active': activeSection === link.key }"
        >
          {{ link.title }}
          <template v-if="link.badge">
            <span class="app-masthead__badge" aria-hidden="true">{{ link.badge > 99 ? "99+" : link.badge }}</span>
            <span class="d-sr-only">{{ $t("messages.unread", { count: link.badge }) }}</span>
          </template>
        </NuxtLink>
        <v-menu v-if="moreSections.length" location="bottom start" :offset="4">
          <template #activator="{ props: menuProps }">
            <button type="button" class="app-masthead__link app-masthead__more" v-bind="menuProps">
              {{ $t("navigation.more") }}
              <v-icon size="16" :icon="$globals.icons.chevronDown" />
            </button>
          </template>
          <v-list density="comfortable" min-width="260" class="py-2">
            <template v-for="section in moreSections" :key="section.key">
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
          </v-list>
        </v-menu>
      </nav>

      <v-spacer />

      <template v-if="menu">
        <button
          v-if="mdAndUp"
          type="button"
          class="app-masthead__search"
          @click="activateSearch"
        >
          <v-icon size="17" :icon="$globals.icons.search" />
          <span>{{ $t("navigation.search-recipes") }}</span>
          <kbd>/</kbd>
        </button>
        <v-btn
          v-else
          icon
          variant="text"
          size="small"
          :aria-label="$t('search.search')"
          @click="activateSearch"
        >
          <v-icon :icon="$globals.icons.search" />
        </v-btn>

        <v-menu v-if="createLinks.length" location="bottom end" :offset="8">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-if="mdAndUp"
              v-bind="menuProps"
              variant="outlined"
              class="ml-3"
              :prepend-icon="$globals.icons.createAlt"
            >
              {{ $t("navigation.add-recipe") }}
            </v-btn>
            <v-btn
              v-else
              v-bind="menuProps"
              icon
              variant="text"
              size="small"
              :aria-label="$t('navigation.add-recipe')"
            >
              <v-icon :icon="$globals.icons.createAlt" />
            </v-btn>
          </template>
          <v-list density="comfortable" min-width="290" class="py-2">
            <v-list-subheader>{{ $t("navigation.add-recipe") }}</v-list-subheader>
            <v-list-item
              v-for="link in createLinks"
              :key="link.key"
              :to="link.to"
              :prepend-icon="link.icon"
              :title="link.title"
              :subtitle="link.subtitle"
            />
          </v-list>
        </v-menu>

        <AppAccountMenu v-if="loggedIn && (mdAndUp || !isOwnGroup)" class="ml-3" />
        <v-btn
          v-else-if="!loggedIn"
          variant="outlined"
          class="ml-3"
          to="/login"
        >
          {{ $t("user.login") }}
        </v-btn>
      </template>
    </div>
    <RecipeDialogSearch ref="domSearchDialog" />
  </v-app-bar>
</template>

<script setup lang="ts">
import AppAccountMenu from "~/components/Layout/LayoutParts/AppAccountMenu.vue";
import { useAppNavigation } from "~/composables/use-app-navigation";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import type RecipeDialogSearch from "~/components/Domain/Recipe/RecipeDialogSearch.vue";

defineProps({
  menu: {
    type: Boolean,
    default: true,
  },
});

const route = useRoute();
const router = useRouter();
const { mdAndUp, smAndDown } = useDisplay();
const { loggedIn, isOwnGroup } = useLoggedInState();
const { homeLink, primaryLinks, activeSection, moreSections, createLinks, groupSlug } = useAppNavigation();

/** Detail pages get a back button on phones, where an installed app has no browser chrome. */
const backTarget = computed(() => {
  const path = route.path.replace(/\/$/, "");
  const parents: [RegExp, string][] = [
    [/^\/g\/[^/]+\/r\/[^/]+$/, `/g/${groupSlug.value}`],
    [/^\/g\/[^/]+\/r\/create(\/.*)?$/, `/g/${groupSlug.value}`],
    [/^\/g\/[^/]+\/cookbooks\/[^/]+$/, `/g/${groupSlug.value}/cookbooks`],
    [/^\/g\/[^/]+\/recipes\/.+$/, `/g/${groupSlug.value}`],
    [/^\/shopping-lists\/[^/]+$/, "/shopping-lists"],
    [/^\/household\/groceries\/.+$/, "/household/groceries"],
    [/^\/household\/mealplan\/.+$/, "/household/week"],
    [/^\/user\/profile\/.+$/, "/user/profile"],
    [/^\/user\/[^/]+\/favorites$/, "/user/profile"],
    [/^\/group\/.+$/, "/group/data"],
  ];
  const adminDetail = path.match(/^\/admin\/manage\/([^/]+)\/.+$/);
  if (adminDetail) {
    return `/admin/manage/${adminDetail[1]}`;
  }
  return parents.find(([pattern]) => pattern.test(path))?.[1] ?? null;
});

function goBack() {
  if (window.history.state?.back) {
    router.back();
  }
  else if (backTarget.value) {
    router.push(backTarget.value);
  }
}

const domSearchDialog = ref<InstanceType<typeof RecipeDialogSearch> | null>(null);

function activateSearch() {
  domSearchDialog.value?.open();
}

function handleKeyEvent(e: KeyboardEvent) {
  const activeTag = document.activeElement?.tagName;
  if (e.key === "/" && activeTag !== "INPUT" && activeTag !== "TEXTAREA") {
    e.preventDefault();
    activateSearch();
  }
}

onMounted(() => {
  document.addEventListener("keydown", handleKeyEvent);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", handleKeyEvent);
});
</script>

<style scoped>
.app-masthead {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.app-masthead :deep(.v-toolbar__content) {
  padding: 0;
}

.app-masthead__inner {
  display: flex;
  align-items: center;
  width: 100%;
  max-width: 1296px;
  height: 100%;
  margin-inline: auto;
  padding-inline: var(--paper-gutter);
}

.app-masthead__back {
  margin-inline: -10px 2px;
}

.app-masthead__wordmark {
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-style: italic;
  font-weight: 500;
  font-size: 1.75rem;
  line-height: 1;
  letter-spacing: -0.01em;
  color: rgb(var(--v-theme-on-background));
  text-decoration: none;
  white-space: nowrap;
}

.app-masthead__nav {
  display: flex;
  align-self: stretch;
  gap: 28px;
  margin-left: 44px;
}

.app-masthead__link {
  appearance: none;
  background: none;
  border: 0;
  padding: 0;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
  font-size: 0.90625rem;
  font-weight: 500;
  color: rgb(var(--v-theme-ink-muted));
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.15s ease;
}

.app-masthead__badge {
  min-width: 18px;
  height: 18px;
  margin-left: 4px;
  padding: 0 5px;
  border-radius: 9px;
  background: rgb(var(--v-theme-tomato));
  color: rgb(var(--v-theme-on-tomato));
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
}

.app-masthead__link:hover {
  color: rgb(var(--v-theme-on-background));
}

.app-masthead__link--active {
  color: rgb(var(--v-theme-on-background));
  border-bottom-color: rgb(var(--v-theme-on-background));
  font-weight: 600;
}

.app-masthead__link:focus-visible,
.app-masthead__search:focus-visible,
.app-masthead__wordmark:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 3px;
  border-radius: 2px;
}

.app-masthead__search {
  appearance: none;
  font-family: inherit;
  display: flex;
  align-items: center;
  gap: 9px;
  width: 248px;
  height: 38px;
  padding: 0 8px 0 15px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 999px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-ink-muted));
  font-size: 0.84375rem;
  cursor: text;
  transition: border-color 0.15s ease;
}

.app-masthead__search:hover {
  border-color: rgba(var(--v-border-color), 0.4);
}

.app-masthead__search span {
  flex: 1;
  text-align: left;
}

.app-masthead__search kbd {
  display: inline-grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 6px;
  font-family: var(--paper-sans);
  font-size: 0.75rem;
  color: rgb(var(--v-theme-ink-muted));
}
</style>
