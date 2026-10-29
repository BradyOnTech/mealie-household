import type { UserRecipeCreatePreferences } from "~/composables/use-users/preferences";
import { useRecipeCreatePreferences } from "~/composables/use-users/preferences";

/** The import settings, remembered on this device, and where to go once a recipe is imported */
export function useNewRecipeOptions() {
  const router = useRouter();
  const preferences = useRecipeCreatePreferences();

  function preference(key: keyof UserRecipeCreatePreferences) {
    return computed({
      get: () => preferences.value[key],
      set: (value: boolean) => {
        preferences.value[key] = value;
      },
    });
  }

  const organize = preference("organize");
  const createNewOrganizers = preference("createNewOrganizers");
  const translateRecipe = preference("translateRecipe");
  const parseRecipe = preference("parseRecipe");
  const stayInEditMode = preference("stayInEditMode");

  /** A site's own categories and keywords, kept as categories and tags. Once two settings, now one */
  const keepSourceLabels = computed({
    get: () => preferences.value.importKeywordsAsTags || preferences.value.importCategories,
    set: (value: boolean) => {
      preferences.value.importKeywordsAsTags = value;
      preferences.value.importCategories = value;
    },
  });

  function navigateToRecipe(recipeSlug: string, groupSlug: string, createPagePath: string) {
    const query = new URLSearchParams();
    if (stayInEditMode.value) {
      query.set("edit", "true");
    }
    if (parseRecipe.value) {
      query.set("parse", "true");
    }

    const queryString = query.toString();
    const recipeUrl = `/g/${groupSlug}/r/${recipeSlug}${queryString ? `?${queryString}` : ""}`;

    // Replace current entry to prevent re-import on back navigation
    router.replace(createPagePath).then(() => router.push(recipeUrl));
  }

  return {
    organize,
    createNewOrganizers,
    keepSourceLabels,
    translateRecipe,
    parseRecipe,
    stayInEditMode,
    navigateToRecipe,
  };
}
