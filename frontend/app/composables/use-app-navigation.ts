import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useGroupSelf } from "~/composables/use-groups";
import { useCookbookPreferences } from "~/composables/use-users/preferences";
import { useCookbookStore, usePublicCookbookStore } from "~/composables/store/use-cookbook-store";
import type { ReadCookBook } from "~/lib/api/types/cookbook";

export interface AppNavLink {
  key: string;
  title: string;
  icon: string;
  to: string;
  /** Only shown to signed-in members of the group being viewed. */
  restricted?: boolean;
  subtitle?: string;
}

export interface AppNavSection {
  key: string;
  title: string;
  links: AppNavLink[];
}

/**
 * Every destination in the app, grouped the way the masthead, the phone tab bar and the
 * "More" sheet present them.
 */
export function useAppNavigation() {
  const i18n = useI18n();
  const { $globals } = useNuxtApp();
  const auth = useMealieAuth();
  const route = useRoute();
  const { loggedIn, isOwnGroup } = useLoggedInState();
  const { group } = useGroupSelf();

  const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");
  const user = computed(() => auth.user.value);

  function visible(links: AppNavLink[]) {
    return links.filter(link => !link.restricted || isOwnGroup.value);
  }

  const homeLink = computed(() => {
    if (isOwnGroup.value) {
      return "/household/week";
    }
    return groupSlug.value ? `/g/${groupSlug.value}` : "/";
  });

  /** The four sections of the masthead and the phone tab bar. */
  const primaryLinks = computed<AppNavLink[]>(() => visible([
    {
      key: "week",
      title: i18n.t("this-week.title"),
      icon: $globals.icons.calendarWeekBegin,
      to: "/household/week",
      restricted: true,
    },
    {
      key: "recipes",
      title: i18n.t("general.recipes"),
      icon: $globals.icons.silverwareForkKnife,
      to: `/g/${groupSlug.value}`,
    },
    {
      key: "groceries",
      title: i18n.t("groceries.title"),
      icon: $globals.icons.cartOutline,
      to: "/household/groceries",
      restricted: true,
    },
    {
      key: "cookbooks",
      title: i18n.t("cookbook.cookbooks"),
      icon: $globals.icons.book,
      to: `/g/${groupSlug.value}/cookbooks`,
      restricted: true,
    },
    // The assistant needs the group's AI provider
    ...(group.value?.aiProviderSettings?.aiEnabled
      ? [{
          key: "ask",
          title: i18n.t("assistant.nav"),
          icon: $globals.icons.chatOutline,
          to: "/household/assistant",
          restricted: true,
        }]
      : []),
  ]));

  /** Which primary section the current page belongs to. */
  const activeSection = computed(() => {
    const path = route.path;
    if (path.startsWith("/household/week")) return "week";
    if (path.startsWith("/household/assistant")) return "ask";
    if (path.startsWith("/household/groceries") || path.startsWith("/shopping-lists")) return "groceries";
    if (path.startsWith("/household/mealplan")) return "week";
    if (/^\/g\/[^/]+\/cookbooks/.test(path)) return "cookbooks";
    if (/^\/g\/[^/]+(\/|$)/.test(path)) return "recipes";
    return "";
  });

  const cookbookPreferences = useCookbookPreferences();
  const ownCookbookStore = computed(() => isOwnGroup.value ? useCookbookStore(i18n) : null);
  const publicCookbookStoreCache = ref<Record<string, ReturnType<typeof usePublicCookbookStore>>>({});

  function getPublicCookbookStore(slug: string) {
    if (!publicCookbookStoreCache.value[slug]) {
      publicCookbookStoreCache.value[slug] = usePublicCookbookStore(slug, i18n);
    }
    return publicCookbookStoreCache.value[slug];
  }

  const cookbooks = computed<ReadCookBook[]>(() => {
    if (ownCookbookStore.value) {
      return ownCookbookStore.value.store.value;
    }
    else if (groupSlug.value) {
      const publicStore = getPublicCookbookStore(groupSlug.value);
      return unref(publicStore.store);
    }
    return [];
  });

  /** Cookbooks of the user's own household first; other households follow unless hidden. */
  const cookbookLinks = computed<AppNavLink[]>(() => {
    const sorted = [...(cookbooks.value || [])].sort((a, b) => (a.position || 0) - (b.position || 0));
    const toLink = (cookbook: ReadCookBook): AppNavLink => ({
      key: cookbook.slug || cookbook.id,
      title: cookbook.name,
      icon: $globals.icons.pages,
      to: `/g/${groupSlug.value}/cookbooks/${cookbook.slug || ""}`,
      subtitle: cookbook.householdId !== user.value?.householdId ? cookbook.household?.name || undefined : undefined,
    });

    const own = sorted.filter(cookbook => cookbook.householdId === user.value?.householdId);
    const others = sorted
      .filter(cookbook => cookbook.householdId !== user.value?.householdId)
      .sort((a, b) => (a.household?.name || "").localeCompare(b.household?.name || ""));

    if (user.value && cookbookPreferences.value.hideOtherHouseholds) {
      return own.map(toLink);
    }
    return [...own, ...others].map(toLink);
  });

  /** Everything that does not fit in the masthead, grouped for the "More" menu and sheet. */
  const moreSections = computed<AppNavSection[]>(() => {
    const sections: AppNavSection[] = [
      {
        key: "plan",
        title: i18n.t("this-week.plan-and-shop"),
        links: visible([
          {
            key: "planner",
            title: i18n.t("meal-plan.meal-planner"),
            icon: $globals.icons.calendarMultiselect,
            to: "/household/mealplan/planner/view",
            restricted: true,
          },
          {
            key: "shopping-lists",
            title: i18n.t("shopping-list.shopping-lists"),
            icon: $globals.icons.formatListCheck,
            to: "/shopping-lists",
            restricted: true,
          },
          {
            key: "products",
            title: i18n.t("groceries.catalog"),
            icon: $globals.icons.cartCheck,
            to: "/household/groceries/products",
            restricted: true,
          },
        ]),
      },
      {
        key: "recipes",
        title: i18n.t("general.recipes"),
        links: visible([
          {
            key: "finder",
            title: i18n.t("recipe-finder.recipe-finder"),
            icon: $globals.icons.search,
            to: `/g/${groupSlug.value}/recipes/finder`,
          },
          {
            key: "favorites",
            title: i18n.t("user.favorite-recipes"),
            icon: $globals.icons.heartOutline,
            to: user.value ? `/user/${user.value.id}/favorites` : "",
            restricted: true,
          },
          {
            key: "timeline",
            title: i18n.t("recipe.timeline"),
            icon: $globals.icons.timelineText,
            to: `/g/${groupSlug.value}/recipes/timeline`,
            restricted: true,
          },
          {
            key: "categories",
            title: i18n.t("sidebar.categories"),
            icon: $globals.icons.categories,
            to: `/g/${groupSlug.value}/recipes/categories`,
            restricted: true,
          },
          {
            key: "tags",
            title: i18n.t("sidebar.tags"),
            icon: $globals.icons.tags,
            to: `/g/${groupSlug.value}/recipes/tags`,
            restricted: true,
          },
          {
            key: "tools",
            title: i18n.t("tool.tools"),
            icon: $globals.icons.potSteam,
            to: `/g/${groupSlug.value}/recipes/tools`,
            restricted: true,
          },
        ]).filter(link => link.to),
      },
    ];

    if (cookbookLinks.value.length) {
      sections.push({ key: "cookbooks", title: i18n.t("cookbook.cookbooks"), links: cookbookLinks.value });
    }
    return sections.filter(section => section.links.length);
  });

  /** Ways to add a recipe. */
  const createLinks = computed<AppNavLink[]>(() => {
    if (!isOwnGroup.value) {
      return [];
    }
    const links: AppNavLink[] = [
      {
        key: "import-url",
        title: i18n.t("general.import"),
        subtitle: i18n.t("new-recipe.import-by-url"),
        icon: $globals.icons.link,
        to: `/g/${groupSlug.value}/r/create/url`,
      },
    ];
    if (group.value?.aiProviderSettings?.aiEnabled) {
      links.push({
        key: "import-ai",
        title: i18n.t("recipe.import-with-ai"),
        subtitle: i18n.t("recipe.import-with-ai-subtitle"),
        icon: $globals.icons.autoFix,
        to: `/g/${groupSlug.value}/r/create/ai`,
      });
    }
    links.push({
      key: "create-new",
      title: i18n.t("general.create"),
      subtitle: i18n.t("new-recipe.create-manually"),
      icon: $globals.icons.edit,
      to: `/g/${groupSlug.value}/r/create/new`,
    });
    return links;
  });

  /** Profile and settings destinations, filtered by the user's permissions. */
  const accountLinks = computed<AppNavLink[]>(() => {
    if (!loggedIn.value || !user.value) {
      return [];
    }
    const links: AppNavLink[] = [
      {
        key: "profile",
        title: i18n.t("profile.user-settings"),
        icon: $globals.icons.user,
        to: "/user/profile",
      },
    ];
    if (user.value.canManageHousehold) {
      links.push({
        key: "household",
        title: i18n.t("profile.household-settings"),
        icon: $globals.icons.household,
        to: "/household",
      });
    }
    if (user.value.canManage) {
      links.push({
        key: "data",
        title: i18n.t("data-pages.data-management"),
        icon: $globals.icons.manageData,
        to: "/group/data",
      });
    }
    if (user.value.admin) {
      links.push({
        key: "admin",
        title: i18n.t("settings.admin-settings"),
        icon: $globals.icons.wrench,
        to: "/admin/site-settings",
      });
    }
    return links;
  });

  return {
    groupSlug,
    homeLink,
    primaryLinks,
    activeSection,
    moreSections,
    cookbookLinks,
    createLinks,
    accountLinks,
  };
}
