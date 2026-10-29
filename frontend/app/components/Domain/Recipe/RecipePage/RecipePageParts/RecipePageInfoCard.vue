<template>
  <header class="recipe-hero">
    <RecipePageInfoCardImage
      v-if="recipe.image"
      :recipe="recipe"
      class="recipe-hero__image"
    />
    <div class="recipe-hero__body">
      <span v-if="kicker" class="paper-kicker">{{ kicker }}</span>
      <h1 class="recipe-hero__title paper-headline">
        {{ recipe.name }}
      </h1>
      <SafeMarkdown
        v-if="recipe.description"
        :source="recipe.description"
        class="recipe-hero__dek paper-dek"
      />

      <RecipeSourceLink :url="recipe.orgURL" class="mt-4 d-print-none" />

      <dl class="recipe-hero__facts">
        <div v-if="recipe.totalTime" class="recipe-hero__fact">
          <dt>{{ $t("recipe.total-time") }}</dt>
          <dd>{{ recipe.totalTime }}</dd>
        </div>
        <div v-if="recipe.prepTime" class="recipe-hero__fact">
          <dt>{{ $t("recipe.prep-time") }}</dt>
          <dd>{{ recipe.prepTime }}</dd>
        </div>
        <div v-if="recipe.performTime" class="recipe-hero__fact">
          <dt>{{ $t("recipe.perform-time") }}</dt>
          <dd>{{ recipe.performTime }}</dd>
        </div>
        <div v-if="recipeServings" class="recipe-hero__fact">
          <dt>{{ $t("recipe.servings") }}</dt>
          <dd>
            <span v-if="isEditMode">{{ recipeServings }}</span>
            <RecipePageScale v-else v-model="scale" :recipe="recipe" />
          </dd>
        </div>
        <div v-if="recipe.recipeYield || (!recipeServings && recipe.recipeYieldQuantity)" class="recipe-hero__fact">
          <dt>{{ $t("recipe.yield") }}</dt>
          <dd>
            <RecipeYield
              :yield-quantity="recipe.recipeYieldQuantity"
              :yield-text="recipe.recipeYield"
              :scale="scale"
              inline
            />
          </dd>
        </div>
        <div class="recipe-hero__fact">
          <dt>{{ $t("general.rating") }}</dt>
          <dd>
            <RecipeRating
              :key="recipe.slug"
              :model-value="recipe.rating"
              :recipe-id="recipe.id"
              :slug="recipe.slug"
              small
            />
          </dd>
        </div>
        <div v-if="isOwnGroup" class="recipe-hero__fact">
          <dt>{{ $t("general.last-made") }}</dt>
          <dd><RecipeLastMade :recipe="recipe" compact /></dd>
        </div>
      </dl>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useLoggedInState } from "~/composables/use-logged-in-state";
import RecipeRating from "~/components/Domain/Recipe/RecipeRating.vue";
import RecipeSourceLink from "~/components/Domain/Recipe/RecipeSourceLink.vue";
import RecipeLastMade from "~/components/Domain/Recipe/RecipeLastMade.vue";
import RecipeYield from "~/components/Domain/Recipe/RecipeYield.vue";
import RecipePageInfoCardImage from "~/components/Domain/Recipe/RecipePage/RecipePageParts/RecipePageInfoCardImage.vue";
import RecipePageScale from "~/components/Domain/Recipe/RecipePage/RecipePageParts/RecipePageScale.vue";
import type { Recipe } from "~/lib/api/types/recipe";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import { usePageState } from "~/composables/recipe-page/shared-state";

interface Props {
  recipe: NoUndefinedField<Recipe>;
  landscape?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  landscape: false,
});

const scale = defineModel<number>("recipeScale", { default: 1 });

const { isOwnGroup } = useLoggedInState();
const { isEditMode } = usePageState(props.recipe.slug);

const recipeServings = computed(() => props.recipe.recipeServings || 0);

/** Categories first, then tags: "Dinner · Thai-inspired". */
const kicker = computed(() =>
  [...(props.recipe.recipeCategory || []), ...(props.recipe.tags || [])]
    .slice(0, 3)
    .map(item => item.name)
    .join(" · "),
);
</script>

<style scoped>
.recipe-hero__image {
  border-radius: 2px;
}

.recipe-hero__body {
  padding-top: 26px;
}

.recipe-hero__title {
  margin: 8px 0 12px;
  font-size: 3.25rem;
}

.recipe-hero__dek {
  max-width: 54ch;
  font-size: 1.1875rem;
}

.recipe-hero__dek :deep(p) {
  margin: 0;
}

.recipe-hero__facts {
  display: flex;
  flex-wrap: wrap;
  margin: 24px 0 0;
  border-top: 1px solid rgb(var(--v-theme-rule));
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.recipe-hero__fact {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  justify-content: center;
  min-width: 112px;
  padding: 10px 18px;
}

.recipe-hero__fact + .recipe-hero__fact {
  border-left: 1px solid rgb(var(--v-theme-rule));
}

.recipe-hero__fact dt {
  margin-bottom: 3px;
  font-size: 0.65625rem;
  font-weight: 500;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.recipe-hero__fact dd {
  display: flex;
  align-items: center;
  min-height: 28px;
  margin: 0;
  font-family: var(--paper-serif);
  font-size: 1.125rem;
  line-height: 1.2;
}

@media (max-width: 959px) {
  .recipe-hero__body {
    padding: 20px 20px 0;
  }

  .recipe-hero__title {
    font-size: 2.375rem;
  }

  .recipe-hero__dek {
    font-size: 1.0625rem;
  }

  .recipe-hero__fact {
    flex-basis: 33%;
    min-width: 0;
    padding: 9px 10px;
  }

  .recipe-hero__fact:nth-child(3n + 1) {
    border-left: 0;
  }

  .recipe-hero__fact:nth-child(n + 4) {
    border-top: 1px solid rgb(var(--v-theme-rule));
  }
}
</style>
