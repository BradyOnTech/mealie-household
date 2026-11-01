<template>
  <BaseDialog
    :model-value="modelValue"
    :title="$t('recipe.parse-ingredients')"
    :icon="$globals.icons.fileSign"
    :cancel-text="$t('recipe.parser.skip-for-now')"
    disable-submit-on-enter
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="state.step === ParseStep.LOADING" class="pa-3">
      <AppLoader class="my-6" :waiting-text="$t('recipe.parser.parsing-ingredients')" />
    </div>

    <v-empty-state
      v-else-if="state.step === ParseStep.ERROR"
      :icon="$globals.icons.alertCircle"
      color="error"
      :headline="$t('recipe.parser.parse-failed-title')"
      :text="$t('recipe.parser.parse-failed-body')"
    >
      <template #actions>
        <div class="d-flex flex-column align-center ga-3">
          <v-btn color="info" variant="flat" :prepend-icon="$globals.icons.refresh" @click="parseIngredients">
            {{ $t("recipe.parser.try-again") }}
          </v-btn>
          <ParseDialogChangeParser
            v-model="parser"
            :available-parsers="availableParsers"
            :show-nlp-language-hint="showNlpLanguageHint"
            @parse="parseIngredients"
          />
        </div>
      </template>
    </v-empty-state>

    <v-empty-state
      v-else-if="!items.length"
      :icon="$globals.icons.fileSign"
      :text="$t('recipe.parser.no-ingredients')"
    />

    <ParseDialogReview v-else :dialog-state="dialogState" />

    <template #custom-card-action>
      <BaseButton
        v-if="state.step === ParseStep.REVIEW && items.length"
        save
        :text="$t('recipe.parser.save-ingredients')"
        :icon="$globals.icons.save"
        :loading="state.saveLoading"
        @click="save"
      />
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { ParseStep, useParseIngredientsDialog } from "~/composables/recipes/use-parse-ingredients-dialog";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { RecipeIngredient } from "~/lib/api/types/recipe";

const props = defineProps<{
  modelValue: boolean;
  ingredients: NoUndefinedField<RecipeIngredient[]>;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "save", value: NoUndefinedField<RecipeIngredient[]>): void;
}>();

const dialogState = useParseIngredientsDialog(props.ingredients, ings => emit("save", ings));
const { items, state, parser, availableParsers, showNlpLanguageHint, parseIngredients, save } = dialogState;

watch(() => props.modelValue, () => {
  if (!props.modelValue) {
    return;
  }

  parseIngredients();
});
</script>
