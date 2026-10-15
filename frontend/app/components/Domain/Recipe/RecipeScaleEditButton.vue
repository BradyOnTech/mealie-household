<template>
  <div v-if="yieldDisplay" class="recipe-scale">
    <span v-if="label" class="recipe-scale__label">{{ label }}</span>
    <button
      v-if="canEditScale"
      type="button"
      class="recipe-scale__step"
      :disabled="disableDecrement"
      :aria-label="$t('recipe.decrease-scale-label')"
      @click="recalculateScale(yieldQuantity - 1)"
    >
      −
    </button>
    <v-menu
      v-model="menu"
      :disabled="!canEditScale"
      location="bottom"
      :offset="6"
      :close-on-content-click="false"
    >
      <template #activator="{ props: activatorProps }">
        <button
          type="button"
          class="recipe-scale__value"
          :class="{ 'recipe-scale__value--editable': canEditScale }"
          :disabled="!canEditScale"
          :title="canEditScale ? $t('recipe.edit-scale') : undefined"
          :aria-label="yieldDisplay"
          v-bind="activatorProps"
        >
          <!-- eslint-disable-next-line vue/no-v-html -->
          <span v-html="amountDisplay" />
        </button>
      </template>
      <v-card min-width="300px">
        <v-card-title class="mb-0">
          {{ $t("recipe.servings") }}
        </v-card-title>
        <v-card-text class="mt-n5">
          <div class="mt-4 d-flex align-center">
            <v-number-input
              :model-value="yieldQuantity"
              :precision="null"
              :min="0"
              variant="underlined"
              control-variant="hidden"
              @update:model-value="recalculateScale($event || 0)"
            />
            <v-tooltip location="end">
              <template #activator="{ props: resetTooltipProps }">
                <v-btn
                  v-bind="resetTooltipProps"
                  icon
                  variant="text"
                  class="mx-1"
                  size="small"
                  @click="scale = 1"
                >
                  <v-icon>
                    {{ $globals.icons.undo }}
                  </v-icon>
                </v-btn>
              </template>
              <span> {{ $t("recipe.reset-servings-count") }} </span>
            </v-tooltip>
          </div>
        </v-card-text>
      </v-card>
    </v-menu>
    <button
      v-if="canEditScale"
      type="button"
      class="recipe-scale__step"
      :aria-label="$t('recipe.increase-scale-label')"
      @click="recalculateScale(yieldQuantity + 1)"
    >
      +
    </button>
  </div>
</template>

<script setup lang="ts">
import { useScaledAmount } from "~/composables/recipes/use-scaled-amount";

interface Props {
  recipeServings?: number;
  editScale?: boolean;
  label?: string;
}
const props = withDefaults(defineProps<Props>(), {
  recipeServings: 0,
  editScale: false,
  label: "",
});

const scale = defineModel<number>({ required: true });

const i18n = useI18n();
const menu = ref<boolean>(false);
const canEditScale = computed(() => props.editScale && props.recipeServings > 0);

function recalculateScale(newYield: number) {
  if (isNaN(newYield) || newYield <= 0) {
    return;
  }

  if (props.recipeServings <= 0) {
    scale.value = 1;
  }
  else {
    scale.value = newYield / props.recipeServings;
  }
}

const recipeYieldAmount = computed(() => {
  return useScaledAmount(props.recipeServings, scale.value);
});
const yieldQuantity = computed(() => recipeYieldAmount.value.scaledAmount);
const amountDisplay = computed(() => recipeYieldAmount.value.scaledAmountDisplay);
const yieldDisplay = computed(() => {
  return yieldQuantity.value
    ? i18n.t(
      "recipe.serves-amount", { amount: recipeYieldAmount.value.scaledAmountDisplay },
    ) as string
    : "";
});

const disableDecrement = computed(() => {
  return yieldQuantity.value <= 1;
});
</script>

<style scoped>
.recipe-scale {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.recipe-scale__label {
  margin-right: 6px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: rgb(var(--v-theme-ink-muted));
}

.recipe-scale__step,
.recipe-scale__value {
  appearance: none;
  border: 0;
  padding: 0;
  background: none;
  color: inherit;
  font: inherit;
}

.recipe-scale__step {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  font-family: var(--paper-sans);
  font-size: 1.125rem;
  line-height: 1;
  color: rgb(var(--v-theme-tomato));
  cursor: pointer;
}

.recipe-scale__step:hover:not(:disabled) {
  background: rgb(var(--v-theme-wash));
}

.recipe-scale__step:disabled {
  opacity: 0.35;
  cursor: default;
}

.recipe-scale__value {
  min-width: 1.4em;
  font-family: var(--paper-serif);
  font-size: 1.125rem;
  text-align: center;
}

.recipe-scale__value--editable {
  cursor: pointer;
  text-decoration: underline dotted rgb(var(--v-theme-rule));
  text-underline-offset: 4px;
}

.recipe-scale__step:focus-visible,
.recipe-scale__value:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}
</style>
