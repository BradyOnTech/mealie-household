<template>
  <div>
    <!-- Recipe Categories -->
    <section
      v-if="recipe.recipeCategory.length > 0 || isEditForm"
      class="recipe-filed"
    >
      <h3 class="recipe-filed__title">
        {{ $t("recipe.categories") }}
      </h3>
      <div class="recipe-filed__body">
        <RecipeOrganizerSelector
          v-if="isEditForm"
          v-model="recipe.recipeCategory"
          :return-object="true"
          :show-add="true"
          selector-type="categories"
        />
        <RecipeChips
          v-else
          :items="recipe.recipeCategory"
          v-bind="$attrs"
        />
      </div>
    </section>

    <!-- Recipe Tags -->
    <section
      v-if="recipe.tags.length > 0 || isEditForm"
      class="recipe-filed"
    >
      <h3 class="recipe-filed__title">
        {{ $t("tag.tags") }}
      </h3>
      <div class="recipe-filed__body">
        <RecipeOrganizerSelector
          v-if="isEditForm"
          v-model="recipe.tags"
          :return-object="true"
          :show-add="true"
          selector-type="tags"
        />
        <RecipeChips
          v-else
          :items="recipe.tags"
          url-prefix="tags"
          v-bind="$attrs"
        />
      </div>
    </section>

    <!-- Recipe Tools Edit -->
    <section
      v-if="isEditForm"
      class="recipe-filed"
    >
      <h3 class="recipe-filed__title">
        {{ $t('tool.required-tools') }}
      </h3>
      <div class="recipe-filed__body">
        <RecipeOrganizerSelector
          v-model="recipe.tools"
          selector-type="tools"
        />
      </div>
    </section>

    <RecipeNutrition
      v-if="recipe.settings.showNutrition"
      v-model="recipe.nutrition"
      class="mt-4"
      :edit="isEditForm"
    />
    <RecipeAssets
      v-if="recipe.settings.showAssets"
      v-model="recipe.assets"
      :edit="isEditForm"
      :slug="recipe.slug"
      :recipe-id="recipe.id"
    />
  </div>
</template>

<script setup lang="ts">
import { usePageState } from "~/composables/recipe-page/shared-state";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe } from "~/lib/api/types/recipe";
import RecipeOrganizerSelector from "@/components/Domain/Recipe/RecipeOrganizerSelector.vue";
import RecipeNutrition from "~/components/Domain/Recipe/RecipeNutrition.vue";
import RecipeChips from "@/components/Domain/Recipe/RecipeChips.vue";
import RecipeAssets from "@/components/Domain/Recipe/RecipeAssets.vue";

const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });
const { isEditForm } = usePageState(recipe.value.slug);
</script>

<style scoped>
.recipe-filed {
  margin-top: 28px;
}

.recipe-filed__title {
  padding-bottom: 6px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  font-family: var(--paper-sans);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-tomato));
}

.recipe-filed__body {
  padding-top: 10px;
}
</style>
