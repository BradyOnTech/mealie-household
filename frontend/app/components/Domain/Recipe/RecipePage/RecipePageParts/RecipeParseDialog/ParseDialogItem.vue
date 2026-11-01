<template>
  <v-card
    variant="outlined"
    class="parse-item"
    :class="{ 'parse-item--attention': attention }"
  >
    <!-- Linked recipes aren't read by the parser, so there's nothing to check -->
    <div v-if="isRecipeLink(item)" class="d-flex align-center ga-3 pa-3">
      <v-icon color="success">
        {{ $globals.icons.checkboxMarkedCircle }}
      </v-icon>
      <div class="parse-item__grow">
        <div class="text-caption text-medium-emphasis">
          {{ $t("recipe.parser.linked-recipe") }}
        </div>
        <div class="text-body-1 font-weight-medium">
          {{ preview(item) }}
        </div>
      </div>
    </div>

    <!-- Ready and folded away: one line, tap to open -->
    <button
      v-else-if="!open"
      type="button"
      class="parse-item__summary d-flex align-center ga-3 pa-3 w-100 text-left"
      :aria-expanded="false"
      @click="expanded = true"
    >
      <v-icon color="success">
        {{ $globals.icons.checkboxMarkedCircle }}
      </v-icon>
      <div class="parse-item__grow">
        <div class="text-body-1 font-weight-medium">
          {{ preview(item) }}
        </div>
        <div class="text-caption text-medium-emphasis text-truncate">
          {{ $t("recipe.parser.imported-text") }}: {{ item.input }}
        </div>
      </div>
      <v-icon>{{ $globals.icons.chevronDown }}</v-icon>
    </button>

    <div v-else class="pa-3 d-flex flex-column ga-3">
      <div class="d-flex align-center ga-2">
        <v-chip
          size="small"
          label
          variant="tonal"
          :color="attention ? 'warning' : 'success'"
          :prepend-icon="attention ? $globals.icons.alertCircle : $globals.icons.checkboxMarkedCircle"
        >
          {{ attention ? $t("recipe.parser.status-needs-input") : $t("recipe.parser.status-ready") }}
        </v-chip>
        <v-spacer />
        <v-btn
          v-if="!editing"
          variant="text"
          size="small"
          color="info"
          :prepend-icon="$globals.icons.edit"
          @click="editing = true"
        >
          {{ $t("general.edit") }}
        </v-btn>
        <v-btn
          variant="text"
          size="small"
          icon
          :aria-label="$t('recipe.parser.remove-line')"
          :title="$t('recipe.parser.remove-line')"
          @click="remove(item)"
        >
          <v-icon>{{ $globals.icons.delete }}</v-icon>
        </v-btn>
        <v-btn
          v-if="!attention && !editing"
          variant="text"
          size="small"
          icon
          :aria-label="$t('general.close')"
          @click="expanded = false"
        >
          <v-icon>{{ $globals.icons.chevronUp }}</v-icon>
        </v-btn>
      </div>

      <section>
        <div class="parse-item__label">
          {{ $t("recipe.parser.imported-text") }}
        </div>
        <p class="parse-item__imported my-0">
          {{ item.input }}
        </p>
      </section>

      <section v-if="!editing">
        <div class="parse-item__label">
          {{ $t("recipe.parser.split-into") }}
        </div>
        <dl class="parse-item__parts">
          <dt>{{ $t("recipe.parser.field-quantity") }}</dt>
          <dd :class="{ 'text-disabled': !item.ingredient.quantity }">
            {{ item.ingredient.quantity ? formatQuantity(item.ingredient.quantity) : $t("recipe.parser.empty-value") }}
          </dd>

          <dt>{{ $t("recipe.parser.field-unit") }}</dt>
          <dd v-if="unitUnresolved(item)">
            {{ item.unmatchedUnit }}
            <v-chip size="x-small" label color="warning" variant="flat" class="ml-1">
              {{ $t("recipe.parser.status-not-in-list") }}
            </v-chip>
          </dd>
          <dd v-else :class="{ 'text-disabled': !item.ingredient.unit }">
            {{ item.ingredient.unit?.name || $t("recipe.parser.empty-value") }}
          </dd>

          <dt>{{ $t("recipe.parser.field-food") }}</dt>
          <dd v-if="foodUnresolved(item)">
            {{ item.unmatchedFood }}
            <v-chip size="x-small" label color="warning" variant="flat" class="ml-1">
              {{ $t("recipe.parser.status-not-in-list") }}
            </v-chip>
          </dd>
          <dd v-else :class="{ 'text-disabled': !item.ingredient.food }">
            {{ item.ingredient.food?.name || $t("recipe.parser.empty-value") }}
          </dd>

          <dt>{{ $t("recipe.parser.field-note") }}</dt>
          <dd :class="{ 'text-disabled': !item.ingredient.note }">
            {{ item.ingredient.note || $t("recipe.parser.empty-value") }}
          </dd>
        </dl>
      </section>

      <section v-else>
        <RecipeIngredientEditor
          v-model="ingredient"
          show-labels
          :unit-error="unitUnresolved(item)"
          :unit-error-tooltip="$t('recipe.parser.this-unit-could-not-be-parsed-automatically')"
          :food-error="foodUnresolved(item)"
          :food-error-tooltip="$t('recipe.parser.this-food-could-not-be-parsed-automatically')"
        />
        <div class="d-flex flex-wrap align-center ga-2 mt-1">
          <v-btn
            v-if="canRemember(item, 'unit')"
            variant="text"
            size="small"
            color="info"
            :loading="busy === 'unit'"
            @click="rememberAsAlias(item, 'unit')"
          >
            {{ $t("recipe.parser.remember-alias", { text: item.unmatchedUnit, item: item.ingredient.unit?.name }) }}
          </v-btn>
          <v-btn
            v-if="canRemember(item, 'food')"
            variant="text"
            size="small"
            color="info"
            :loading="busy === 'food'"
            @click="rememberAsAlias(item, 'food')"
          >
            {{ $t("recipe.parser.remember-alias", { text: item.unmatchedFood, item: item.ingredient.food?.name }) }}
          </v-btn>
          <v-spacer />
          <v-btn
            color="info"
            variant="flat"
            size="small"
            :prepend-icon="$globals.icons.check"
            @click="finishEditing"
          >
            {{ $t("general.done") }}
          </v-btn>
        </div>
      </section>

      <!-- Questions: what the user needs to decide, one block each -->
      <div
        v-if="item.splitSuggestion"
        class="parse-item__question"
      >
        <div class="font-weight-bold">
          {{ $t("recipe.parser.split-question", { count: item.splitSuggestion.parts.length }) }}
        </div>
        <p class="text-body-2 my-1">
          {{ amountText
            ? $t("recipe.parser.split-question-help-amount", { count: item.splitSuggestion.parts.length, amount: amountText })
            : $t("recipe.parser.split-question-help", { count: item.splitSuggestion.parts.length }) }}
        </p>
        <div class="d-flex flex-wrap ga-1 mb-2">
          <v-chip
            v-for="part in item.splitSuggestion.parts"
            :key="part"
            size="small"
            variant="outlined"
          >
            {{ part }}
          </v-chip>
        </div>
        <div class="d-flex flex-wrap ga-2">
          <v-btn
            color="warning"
            variant="flat"
            size="small"
            :prepend-icon="$globals.icons.check"
            @click="splitLine(item)"
          >
            {{ $t("recipe.parser.split-lines", { count: item.splitSuggestion.parts.length }) }}
          </v-btn>
          <v-btn variant="outlined" size="small" @click="keepAsOneLine(item)">
            {{ $t("recipe.parser.keep-one-line") }}
          </v-btn>
        </div>
      </div>

      <div
        v-if="!item.splitSuggestion && unitUnresolved(item)"
        class="parse-item__question"
      >
        <div class="font-weight-bold">
          {{ $t("recipe.parser.unit-question", { unit: item.unmatchedUnit }) }}
        </div>
        <p class="text-body-2 my-1">
          {{ $t("recipe.parser.unit-question-help") }}
        </p>
        <div class="d-flex flex-wrap ga-2">
          <v-btn
            color="warning"
            variant="flat"
            size="small"
            :prepend-icon="$globals.icons.createAlt"
            :loading="busy === 'unit'"
            :disabled="!!busy && busy !== 'unit'"
            @click="addUnmatched(item, 'unit')"
          >
            {{ $t("recipe.parser.add-new", { name: item.unmatchedUnit }) }}
          </v-btn>
          <v-btn v-if="!editing" variant="outlined" size="small" @click="editing = true">
            {{ $t("recipe.parser.pick-existing") }}
          </v-btn>
          <v-btn variant="text" size="small" @click="keepAsNote(item, 'unit')">
            {{ $t("recipe.parser.keep-as-note") }}
          </v-btn>
        </div>
      </div>

      <div
        v-if="!item.splitSuggestion && foodUnresolved(item)"
        class="parse-item__question"
      >
        <div class="font-weight-bold">
          {{ $t("recipe.parser.food-question", { food: item.unmatchedFood }) }}
        </div>
        <p class="text-body-2 my-1">
          {{ $t("recipe.parser.food-question-help") }}
        </p>
        <div class="d-flex flex-wrap ga-2">
          <v-btn
            color="warning"
            variant="flat"
            size="small"
            :prepend-icon="$globals.icons.createAlt"
            :loading="busy === 'food'"
            :disabled="!!busy && busy !== 'food'"
            @click="addUnmatched(item, 'food')"
          >
            {{ $t("recipe.parser.add-new", { name: item.unmatchedFood }) }}
          </v-btn>
          <v-btn v-if="!editing" variant="outlined" size="small" @click="editing = true">
            {{ $t("recipe.parser.pick-existing") }}
          </v-btn>
          <v-btn variant="text" size="small" @click="keepAsNote(item, 'food')">
            {{ $t("recipe.parser.keep-as-note") }}
          </v-btn>
        </div>
      </div>

      <div
        v-if="!item.splitSuggestion && !unitUnresolved(item) && !foodUnresolved(item) && isUnsure(item) && !editing"
        class="parse-item__question"
      >
        <div class="font-weight-bold">
          {{ $t("recipe.parser.unsure-question") }}
        </div>
        <p class="text-body-2 my-1">
          {{ $t("recipe.parser.unsure-question-help") }}
        </p>
        <div class="d-flex flex-wrap ga-2">
          <v-btn
            color="warning"
            variant="flat"
            size="small"
            :prepend-icon="$globals.icons.check"
            @click="confirm(item)"
          >
            {{ $t("recipe.parser.looks-right") }}
          </v-btn>
          <v-btn variant="outlined" size="small" @click="editing = true">
            {{ $t("recipe.parser.fix-it") }}
          </v-btn>
        </div>
      </div>

      <section class="parse-item__result">
        <div class="parse-item__label">
          {{ $t("recipe.parser.shows-as") }}
        </div>
        <div class="text-body-1 font-weight-medium">
          {{ preview(item) || $t("recipe.parser.empty-value") }}
        </div>
      </section>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import type { ParseReviewItem, useParseIngredientsDialog } from "~/composables/recipes/use-parse-ingredients-dialog";

const props = defineProps<{
  item: ParseReviewItem;
  dialogState: ReturnType<typeof useParseIngredientsDialog>;
}>();

const {
  state,
  isRecipeLink,
  unitUnresolved,
  foodUnresolved,
  isUnsure,
  needsInput,
  canRemember,
  preview,
  confirm,
  splitLine,
  keepAsOneLine,
  keepAsNote,
  addUnmatched,
  rememberAsAlias,
  updateIngredient,
  remove,
} = props.dialogState;

const ingredient = computed({
  get: () => props.item.ingredient,
  set: value => updateIngredient(props.item, value),
});

const expanded = ref(false);
const editing = ref(false);

const attention = computed(() => needsInput(props.item));
/** Lines that need an answer always stay open; ready ones fold away unless the user opens them */
const open = computed(() => attention.value || editing.value || expanded.value);
const busy = computed(() => state.busy[props.item.key]);

function finishEditing() {
  editing.value = false;
  // Having looked at it and closed the editor counts as checking the split
  confirm(props.item);
}

const { locale } = useI18n();
function formatQuantity(quantity: number) {
  return quantity.toLocaleString(locale.value, { maximumFractionDigits: 3 });
}

/** "1 teaspoon": the amount each line gets when a list is split */
const amountText = computed(() => {
  const { quantity, unit } = props.item.ingredient;
  if (!quantity) {
    return "";
  }
  return [formatQuantity(quantity), unit?.name || props.item.unmatchedUnit].filter(Boolean).join(" ");
});
</script>

<style scoped>
.parse-item {
  border-color: rgba(var(--v-border-color), 0.24);
}
.parse-item--attention {
  border-color: rgb(var(--v-theme-warning));
  border-width: 2px;
}
.parse-item__grow {
  flex: 1 1 auto;
  min-width: 0;
}
.parse-item__summary {
  background: none;
  border: 0;
  color: inherit;
  cursor: pointer;
}
.parse-item__label {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0.7;
  margin-bottom: 2px;
}
.parse-item__imported {
  font-family: var(--paper-serif, inherit);
  font-style: italic;
  font-size: 1.15rem;
  line-height: 1.4;
}
.parse-item__parts {
  display: grid;
  grid-template-columns: max-content 1fr;
  column-gap: 16px;
  row-gap: 6px;
  margin: 0;
}
.parse-item__parts dt {
  opacity: 0.7;
}
.parse-item__parts dd {
  margin: 0;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.parse-item__question {
  background: rgba(var(--v-theme-warning), 0.12);
  border-radius: 8px;
  padding: 12px;
}
.parse-item__result {
  border-top: 1px dashed rgba(var(--v-border-color), 0.24);
  padding-top: 10px;
}
</style>
