<template>
  <div class="recipe-explorer paper-container">
    <header class="recipe-explorer__head">
      <span class="paper-kicker">{{ $t("general.recipes") }}</span>
      <h1 class="recipe-explorer__title paper-headline">
        {{ $t("recipe-explorer.title") }}
      </h1>
      <p class="recipe-explorer__dek paper-dek">
        {{ $t("recipe-explorer.subtitle") }}
      </p>
    </header>
    <RecipeExplorerPageSearch
      ref="searchComponent"
      @ready="onSearchReady"
    />
    <div class="recipe-explorer__results">
      <RecipeCardSection
        v-if="ready"
        :icon="$globals.icons.silverwareForkKnife"
        :recipes="recipes"
        :query="searchQuery"
        disable-sort
        @item-selected="onItemSelected"
        @replace-recipes="replaceRecipes"
        @append-recipes="appendRecipes"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import RecipeExplorerPageSearch from "./RecipeExplorerPageParts/RecipeExplorerPageSearch.vue";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import RecipeCardSection from "~/components/Domain/Recipe/RecipeCardSection.vue";
import { useLazyRecipes } from "~/composables/recipes";

const auth = useMealieAuth();
const route = useRoute();

const { isOwnGroup } = useLoggedInState();
const groupSlug = computed(() => route.params.groupSlug as string || auth.user.value?.groupSlug || "");

const { recipes, appendRecipes, replaceRecipes } = useLazyRecipes(isOwnGroup.value ? null : groupSlug.value);

const ready = ref(false);
const searchComponent = ref<InstanceType<typeof RecipeExplorerPageSearch>>();

const searchQuery = computed(() => {
  return searchComponent.value?.passedQueryWithSeed || {};
});

function onSearchReady() {
  ready.value = true;
}

function onItemSelected(item: any, urlPrefix: string) {
  searchComponent.value?.filterItems(item, urlPrefix);
}
</script>

<style scoped>
.recipe-explorer {
  padding-top: 36px;
  padding-bottom: 72px;
}

.recipe-explorer__title {
  margin: 6px 0 10px;
  font-size: 3rem;
}

.recipe-explorer__dek {
  margin: 0;
  max-width: 52ch;
  font-size: 1.125rem;
}

.recipe-explorer__results {
  padding-top: 8px;
}

@media (max-width: 599px) {
  .recipe-explorer {
    padding-top: 22px;
  }

  .recipe-explorer__title {
    font-size: 2.25rem;
  }

  .recipe-explorer__dek {
    font-size: 1rem;
  }
}
</style>
