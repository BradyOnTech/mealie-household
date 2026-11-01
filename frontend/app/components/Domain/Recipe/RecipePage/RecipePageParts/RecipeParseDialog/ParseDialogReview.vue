<template>
  <div class="d-flex flex-column ga-3 pa-3">
    <!-- Where things stand: what came in, and how much still needs the user -->
    <header>
      <div class="d-flex align-baseline flex-wrap ga-2">
        <h3 class="text-h6 my-0">
          {{ $t("recipe.parser.summary-title", items.length) }}
        </h3>
        <v-spacer />
        <span class="text-body-2 text-medium-emphasis">
          {{ $t("recipe.parser.summary-progress", { ready: readyCount, total: items.length }) }}
        </span>
      </div>
      <v-progress-linear
        :model-value="items.length ? (readyCount / items.length) * 100 : 0"
        color="success"
        bg-color="warning"
        height="6"
        rounded
        class="my-2"
      />
      <div class="d-flex align-center flex-wrap ga-1">
        <span
          class="text-body-2 font-weight-medium"
          :class="needsInputCount ? 'text-warning' : 'text-success'"
        >
          {{ needsInputCount
            ? $t("recipe.parser.summary-needs-input", needsInputCount)
            : $t("recipe.parser.summary-all-ready") }}
        </span>
        <v-spacer />
        <v-btn
          v-if="!showExplainer"
          variant="text"
          size="small"
          color="info"
          :prepend-icon="$globals.icons.informationOutline"
          @click="showExplainer = true"
        >
          {{ $t("recipe.parser.explainer-show") }}
        </v-btn>
      </div>
    </header>

    <ParseDialogInfo v-if="showExplainer" @dismiss="dismissExplainer" />

    <template v-for="item in items" :key="item.key">
      <div v-if="item.ingredient.title" class="parse-review__section mt-2">
        {{ item.ingredient.title }}
      </div>
      <ParseDialogItem :item="item" :dialog-state="dialogState" />
    </template>

    <p v-if="needsInputCount" class="text-caption text-medium-emphasis my-0">
      {{ $t("recipe.parser.save-unresolved-hint") }}
    </p>

    <v-divider class="mt-1" />
    <ParseDialogChangeParser
      v-model="parser"
      :available-parsers="availableParsers"
      :show-nlp-language-hint="showNlpLanguageHint"
      @parse="parseIngredients"
    />
  </div>
</template>

<script setup lang="ts">
import type { useParseIngredientsDialog } from "~/composables/recipes/use-parse-ingredients-dialog";

const props = defineProps<{
  dialogState: ReturnType<typeof useParseIngredientsDialog>;
}>();

const {
  items,
  parser,
  availableParsers,
  showNlpLanguageHint,
  showExplainer,
  needsInputCount,
  readyCount,
  parseIngredients,
  dismissExplainer,
} = props.dialogState;
</script>

<style scoped>
.parse-review__section {
  font-family: var(--paper-serif, inherit);
  font-size: 1.05rem;
  font-weight: 600;
}
</style>
