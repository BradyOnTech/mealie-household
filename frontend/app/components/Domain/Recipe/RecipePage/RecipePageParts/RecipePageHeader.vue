<template>
  <div>
    <RecipePageInfoCard
      v-model:recipe-scale="recipeScale"
      :recipe="recipe"
      :landscape="landscape"
    />
    <RecipeActionMenu
      :recipe="recipe"
      :slug="recipe.slug"
      :recipe-scale="recipeScale"
      :can-edit="canEditRecipe"
      :name="recipe.name"
      :logged-in="isOwnGroup"
      :open="isEditMode"
      :recipe-id="recipe.id"
      class="recipe-actions"
      @close="$emit('close')"
      @json="toggleEditMode()"
      @edit="setMode(PageMode.EDIT)"
      @save="$emit('save')"
      @delete="$emit('delete')"
      @print="printRecipe"
    >
      <template v-if="!isEditMode && recipe.recipeInstructions?.length" #start>
        <v-btn
          color="primary"
          variant="flat"
          :size="$vuetify.display.xs ? 'default' : 'large'"
          :prepend-icon="$globals.icons.primary"
          @click="toggleCookMode()"
        >
          {{ $t("this-week.start-cooking") }}
        </v-btn>
      </template>
    </RecipeActionMenu>
  </div>
</template>

<script setup lang="ts">
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useRecipePermissions } from "~/composables/recipes";
import RecipePageInfoCard from "~/components/Domain/Recipe/RecipePage/RecipePageParts/RecipePageInfoCard.vue";
import RecipeActionMenu from "~/components/Domain/Recipe/RecipeActionMenu.vue";
import { useStaticRoutes, useUserApi } from "~/composables/api";
import type { HouseholdSummary } from "~/lib/api/types/household";
import type { Recipe } from "~/lib/api/types/recipe";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import { usePageState, usePageUser, PageMode } from "~/composables/recipe-page/shared-state";

interface Props {
  recipe: NoUndefinedField<Recipe>;
  landscape?: boolean;
}
const props = withDefaults(defineProps<Props>(), {
  landscape: false,
});

const recipeScale = defineModel<number>("recipeScale", { default: 1 });

defineEmits(["save", "delete", "print", "close"]);

const { recipeImage } = useStaticRoutes();
const { imageKey, setMode, toggleEditMode, toggleCookMode, isEditMode } = usePageState(props.recipe.slug);
const { user } = usePageUser();
const { isOwnGroup } = useLoggedInState();

const recipeHousehold = ref<HouseholdSummary>();
if (user) {
  const userApi = useUserApi();
  userApi.households.getOne(props.recipe.householdId).then(({ data }) => {
    recipeHousehold.value = data || undefined;
  });
}
const { canEditRecipe } = useRecipePermissions(props.recipe, recipeHousehold, user);

function printRecipe() {
  window.print();
}

const hideImage = ref(false);

const recipeImageUrl = computed(() => {
  return recipeImage(props.recipe.id, props.recipe.image, imageKey.value);
});

watch(
  () => recipeImageUrl.value,
  () => {
    hideImage.value = false;
  },
);
</script>

<style scoped>
.recipe-actions {
  margin-top: 14px;
}

.recipe-actions.fixed-bar {
  height: 60px;
  padding: 0;
}

@media (max-width: 959px) {
  .recipe-actions.fixed-bar {
    padding: 0 16px;
  }
}
</style>
