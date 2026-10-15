<template>
  <div v-if="value && value.length > 0">
    <div
      v-if="!isCookMode"
      class="recipe-ingredients__head"
    >
      <h2 class="recipe-ingredients__title">
        {{ $t("recipe.ingredients") }}
      </h2>
      <AppButtonCopy
        btn-class="ml-auto"
        :copy-text="ingredientCopyText"
      />
    </div>
    <div>
      <div
        v-for="(ingredient, index) in value"
        :key="'ingredient' + index"
      >
        <h3
          v-if="showTitleEditor[index]"
          class="recipe-ingredients__section"
        >
          {{ ingredient.title }}
        </h3>
        <v-list-item
          density="compact"
          class="px-0 py-1 ingredient-list-item"
          @click.stop="toggleChecked(index)"
        >
          <template #prepend>
            <v-checkbox
              :model-value="isChecked(index)"
              hide-details
              class="pt-0 mt-0"
              color="secondary"
              :false-icon="icons.checkboxBlankCircleOutline"
              :true-icon="icons.checkboxMarkedCircle"
              density="comfortable"
              @click.stop
              @update:model-value="setChecked(index, !!$event)"
            />
          </template>
          <v-list-item-title>
            <RecipeIngredientListItem
              :ingredient="ingredient"
              :scale="scale"
              show-substitutions
            />
          </v-list-item-title>
        </v-list-item>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import RecipeIngredientListItem from "./RecipeIngredientListItem.vue";
import { useSessionStorage } from "@vueuse/core";
import { useIngredientTextParser } from "~/composables/recipes";
import { icons } from "~/lib/icons";
import type { RecipeIngredient } from "~/lib/api/types/recipe";

interface Props {
  value?: RecipeIngredient[];
  scale?: number;
  isCookMode?: boolean;
  storageKey?: string;
}
const props = withDefaults(defineProps<Props>(), {
  value: () => [],
  scale: 1,
  isCookMode: false,
  storageKey: undefined,
});

const { parseIngredientText } = useIngredientTextParser();

function validateTitle(title?: string | null) {
  return !(title === undefined || title === "" || title === null);
}

const transientChecked = ref<Record<string, boolean>>({});
const sessionChecked = props.storageKey
  ? useSessionStorage<Record<string, boolean>>(props.storageKey, {})
  : null;
const showTitleEditor = computed(() => props.value.map(x => validateTitle(x.title)));

const ingredientCopyText = computed(() => {
  const components: string[] = [];
  props.value.forEach((ingredient) => {
    if (ingredient.title) {
      if (components.length) {
        components.push("");
      }

      components.push(`[${ingredient.title}]`);
    }

    components.push(parseIngredientText(ingredient, props.scale, false));
  });

  return components.join("\n");
});

function toggleChecked(index: number) {
  setChecked(index, !isChecked(index));
}

function checkedState() {
  return sessionChecked?.value ?? transientChecked.value;
}

function checkedKey(index: number) {
  const referenceId = props.value[index]?.referenceId;
  return referenceId ? `ref:${referenceId}` : `idx:${index}`;
}

function isChecked(index: number) {
  return !!checkedState()[checkedKey(index)];
}

function setChecked(index: number, value: boolean) {
  const state = checkedState();
  state[checkedKey(index)] = value;

  if (sessionChecked) {
    sessionChecked.value = { ...state };
  }
  else {
    transientChecked.value = { ...state };
  }
}
</script>

<style>
.dense-markdown p {
  margin: auto !important;
}

/* vuetify clips both of these, which would swallow the substitution button's tap target
   where it reaches past the line of text */
.ingredient-list-item .v-list-item__content,
.ingredient-list-item .v-list-item-title {
  overflow: visible;
}

.ingredient-list-item {
  align-items: flex-start;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  border-radius: 0;
}

.ingredient-list-item .ingredient-qty,
.ingredient-list-item .ingredient-unit {
  font-family: var(--paper-serif);
  color: rgb(var(--v-theme-tomato));
}

.ingredient-list-item .text-bold {
  font-weight: 550;
}

.recipe-ingredients__head {
  display: flex;
  align-items: center;
  padding-bottom: 4px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
}

.recipe-ingredients__title {
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 450;
  letter-spacing: -0.01em;
}

.recipe-ingredients__section {
  margin: 18px 0 2px;
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  font-style: italic;
  font-weight: 400;
  color: rgb(var(--v-theme-ink-muted));
}

.ingredient-list-item .v-list-item__prepend,
.ingredient-list-item .v-list-item__content {
  align-self: flex-start;
}

.ingredient-list-item .v-selection-control {
  align-self: flex-start;
  margin-top: -9px;
}
</style>
