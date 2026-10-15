<template>
  <RecipeScaleEditButton
    v-if="!isEditMode"
    v-model.number="scale"
    :recipe-servings="recipeServings"
    :edit-scale="hasFoodOrUnit && !isEditMode"
    :label="label"
  />
</template>

<script setup lang="ts">
import RecipeScaleEditButton from "~/components/Domain/Recipe/RecipeScaleEditButton.vue";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe } from "~/lib/api/types/recipe";
import { usePageState } from "~/composables/recipe-page/shared-state";

const props = withDefaults(defineProps<{ recipe: NoUndefinedField<Recipe>; label?: string }>(), {
  label: "",
});

const scale = defineModel<number>({ default: 1 });

const { isEditMode } = usePageState(props.recipe.slug);

const recipeServings = computed<number>(() => {
  return props.recipe.recipeServings || props.recipe.recipeYieldQuantity || 1;
});

const hasFoodOrUnit = computed(() => {
  if (props.recipe.recipeIngredient) {
    for (const ingredient of props.recipe.recipeIngredient) {
      if (ingredient.food || ingredient.unit) {
        return true;
      }
    }
  }
  return false;
});
</script>
