<template>
  <v-container class="groceries-page" max-width="1400">
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-6">
      <div>
        <h1 class="text-h4">
          {{ $t('groceries.title') }}
        </h1>
        <p class="text-body-1 text-medium-emphasis mt-2">
          {{ $t('groceries.subtitle') }}
        </p>
      </div>
      <v-btn variant="outlined" to="/household/groceries/products">
        {{ $t('groceries.catalog') }}
      </v-btn>
    </div>
    <v-alert v-if="error || catalogError" type="error" closable class="mb-4" @click:close="error = ''; catalogError = ''">
      {{ error || catalogError }}
    </v-alert>
    <v-card variant="outlined" class="pa-5 mb-5 control-card">
      <div class="d-flex flex-wrap align-center ga-3 mb-4">
        <v-text-field
          v-model="dateInput"
          type="date"
          :label="$t('groceries.week-of')"
          :disabled="busy"
          hide-details
          density="compact"
          variant="outlined"
          class="date-field"
        />
        <v-spacer />
        <v-btn :disabled="busy" variant="text" @click="refresh">
          {{ $t('groceries.refresh') }}
        </v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" :disabled="busy || !selectedStores.length || loading" @click="generate">
          {{ $t(view?.week ? 'groceries.update-week' : 'groceries.generate') }}
        </v-btn>
      </div>
      <p class="text-subtitle-2 mb-3">
        {{ $t('groceries.stores-this-week') }}
      </p>
      <div class="d-flex flex-wrap ga-2">
        <v-chip
          v-for="store in groceryStores"
          :key="store.value"
          :color="selectedStores.includes(store.value) ? store.color : undefined"
          :variant="selectedStores.includes(store.value) ? 'flat' : 'outlined'"
          :disabled="busy"
          tabindex="0"
          role="checkbox"
          :aria-checked="selectedStores.includes(store.value)"
          @click="toggleStore(store.value)"
          @keydown.enter="toggleStore(store.value)"
        >
          {{ selectedStores.includes(store.value) ? '✓ ' : '' }}{{ store.title }}
        </v-chip>
      </div>
      <v-checkbox
        v-model="skipOnHand"
        :label="$t('groceries.skip-on-hand')"
        :hint="$t('groceries.skip-hint')"
        persistent-hint
        hide-details="auto"
        density="compact"
        class="mt-3"
      />
      <v-alert v-if="view?.week && formDirty" type="info" variant="tonal" density="compact" class="mt-3">
        {{ $t('groceries.changes-pending') }}
      </v-alert>
    </v-card>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />
    <v-row class="mb-5">
      <v-col cols="12" lg="8">
        <v-card variant="outlined" class="pa-5 plan-card">
          <div class="d-flex align-center justify-space-between ga-2 mb-3">
            <h2 class="text-h6">
              {{ $t('groceries.dinners') }}
            </h2>
            <v-btn size="small" variant="text" to="/household/mealplan/planner/edit">
              {{ $t('groceries.plan-dinners') }}
            </v-btn>
          </div>
          <p v-if="!scheduledMeals.length" class="text-body-2 text-medium-emphasis py-5">
            {{ $t('groceries.no-dinners') }}
          </p>
          <div v-for="meal in scheduledMeals" :key="meal.id" class="meal-row d-flex align-center ga-3 py-2">
            <div class="meal-date text-body-2 font-weight-bold">
              {{ friendlyDay(meal.date) }}
            </div>
            <div class="flex-grow-1">
              <NuxtLink v-if="meal.recipe" :to="recipeLink(meal.recipe.slug)" class="text-body-1 recipe-link">{{ meal.recipe.name }}</NuxtLink>
              <span v-else>{{ meal.title }}</span>
              <p class="text-caption text-medium-emphasis">
                {{ meal.entryType }}
              </p>
            </div>
            <v-text-field
              v-if="meal.recipeId"
              v-model="mealScales[String(meal.id)]"
              :label="$t('groceries.recipe-multiplier')"
              type="number"
              min="0"
              max="100"
              step="0.5"
              hide-details
              density="compact"
              variant="outlined"
              class="scale-field"
              :disabled="busy"
            />
          </div>
          <p v-if="scheduledMeals.some(meal => meal.recipeId)" class="text-caption text-medium-emphasis mt-3">
            {{ $t('groceries.multiplier-hint') }}
          </p>
        </v-card>
      </v-col>
      <v-col cols="12" lg="4">
        <v-card variant="tonal" class="pa-5">
          <h2 class="text-h6 mb-2">
            {{ $t('groceries.suggestions') }}
          </h2>
          <p class="text-caption text-medium-emphasis mb-3">
            {{ $t('groceries.suggestions-hint') }}
          </p>
          <p v-if="!suggestions.length" class="text-body-2 text-medium-emphasis">
            {{ $t('groceries.no-suggestions') }}
          </p>
          <div v-for="suggestion in suggestions.slice(0, 3)" :key="suggestion.recipe.id ?? suggestion.recipe.slug ?? 'suggestion'" class="suggestion-row py-3">
            <NuxtLink :to="recipeLink(suggestion.recipe.slug)" class="font-weight-medium recipe-link">{{ suggestion.recipe.name }}</NuxtLink>
            <p class="text-caption text-medium-emphasis mt-1">
              {{ suggestion.reasons.join(' · ') }}
            </p>
            <v-btn
              size="small"
              color="primary"
              variant="text"
              :disabled="busy"
              class="mt-1"
              @click="plannedSuggestion = suggestion"
            >
              {{ $t('groceries.add-to-plan') }}
            </v-btn>
          </div>
        </v-card>
      </v-col>
    </v-row>
    <v-alert v-for="warning in view?.warnings ?? []" :key="warning" type="warning" variant="tonal" class="mb-3">
      {{ warning }}
    </v-alert>
    <v-card v-if="!view?.week && !loading" variant="tonal" class="pa-8 text-center">
      <h2 class="text-h6">
        {{ $t('groceries.no-list') }}
      </h2><p class="mt-3">
        {{ $t('groceries.no-list-detail') }}
      </p>
    </v-card>
    <template v-if="view?.week">
      <div class="d-flex flex-wrap align-center ga-3 mb-4">
        <h2 class="text-h6">
          {{ pendingPurchases.length }} {{ $t('groceries.remaining') }}
        </h2><v-spacer />
        <v-btn variant="outlined" :disabled="busy" @click="manualDialog = true">
          {{ $t('groceries.add-item') }}
        </v-btn>
        <v-btn variant="text" @click="copyList">
          {{ copied ? $t('groceries.copied') : $t('groceries.copy') }}
        </v-btn>
      </div>
      <v-chip-group v-model="storeFilter" mandatory class="mb-5">
        <v-chip value="all" variant="outlined">
          {{ $t('groceries.all-stores') }}
        </v-chip>
        <v-chip v-for="store in groceryStores" :key="store.value" :value="store.value" :color="store.color" variant="outlined">
          {{ store.title }} · {{ storeCount(store.value) }}
        </v-chip>
        <v-chip value="unassigned" variant="outlined">
          {{ $t('groceries.unassigned') }} · {{ storeCount(null) }}
        </v-chip>
      </v-chip-group>
      <p v-if="!visiblePending.length" class="pa-6 text-medium-emphasis text-center">
        {{ $t('groceries.nothing-needed') }}
      </p>
      <section v-for="section in storeSections" :key="section.store ?? 'unassigned'" class="store-section mb-6">
        <div class="d-flex align-center ga-3 mb-3">
          <span class="store-dot" :style="{ backgroundColor: storeColor(section.store) }" />
          <h2 class="text-h6">
            {{ section.store ? storeTitle(section.store) : $t('groceries.unassigned') }}
          </h2>
        </div>
        <div v-for="aisle in section.aisles" :key="aisle.name" class="mb-4">
          <h3 class="text-overline text-medium-emphasis mb-2">
            {{ aisle.name }}
          </h3>
          <v-card v-for="purchase in aisle.purchases" :key="purchase.key" variant="outlined" class="purchase-card mb-2">
            <div class="d-flex align-start ga-2 pa-3">
              <v-checkbox-btn class="flex-grow-0 flex-shrink-0" :model-value="false" :disabled="busy" :aria-label="purchase.foodName" @update:model-value="checkPurchase(purchase, true)" />
              <div class="flex-grow-1 purchase-detail">
                <div class="d-flex flex-wrap align-center ga-2">
                  <strong class="text-body-1">{{ purchase.foodName }}</strong>
                  <v-chip v-if="isManualChoice(purchase)" size="x-small" variant="tonal">
                    {{ $t('groceries.this-week') }}
                  </v-chip>
                </div>
                <p v-if="purchase.product" class="text-body-2 mt-1">
                  {{ purchase.product.name }}
                </p>
                <p v-if="purchase.packageCount != null" class="text-body-2 font-weight-medium mt-1">
                  {{ $t('groceries.buy') }} {{ purchase.packageCount }} × {{ purchase.product?.packageQuantity }} {{ unitTitle(purchase.product?.packageUnit) }}
                </p>
                <p class="text-caption text-medium-emphasis mt-1">
                  {{ $t('groceries.needs') }}: {{ purchase.items.map(item => item.display).join(' + ') }}
                </p>
                <p v-if="purchase.quantityNote" class="text-caption text-warning mt-1">
                  {{ purchase.quantityNote }}
                </p>
                <p v-if="purchase.product?.notes" class="text-caption mt-1">
                  {{ purchase.product.notes }}
                </p>
                <div class="d-flex flex-wrap ga-1 mt-2">
                  <v-btn
                    v-if="purchase.product?.url"
                    size="small"
                    color="primary"
                    :href="purchase.product.url"
                    target="_blank"
                    rel="noopener noreferrer"
                    variant="text"
                  >
                    {{ $t('groceries.open-product') }}
                  </v-btn>
                  <v-btn size="small" variant="text" :disabled="busy" @click="openAssignment(purchase)">
                    {{ $t('groceries.assign') }}
                  </v-btn>
                  <v-btn v-if="!purchase.product && purchase.items[0]?.foodId" size="small" variant="text" :to="`/household/groceries/products?food_id=${purchase.items[0].foodId}`">
                    {{ $t('groceries.add-product') }}
                  </v-btn>
                  <v-btn v-if="manualIds(purchase).length" size="small" variant="text" :disabled="busy" @click="deleteManual(purchase)">
                    {{ $t('groceries.delete-manual') }}
                  </v-btn>
                </div>
              </div>
            </div>
          </v-card>
        </div>
      </section>
      <v-expansion-panels v-if="checkedPurchases.length" variant="accordion" class="mb-5">
        <v-expansion-panel :title="`${$t('groceries.checked')} (${checkedPurchases.length})`">
          <v-expansion-panel-text>
            <div v-for="purchase in checkedPurchases" :key="purchase.key" class="d-flex align-center ga-3 mb-2">
              <v-checkbox-btn class="flex-grow-0 flex-shrink-0" :model-value="true" :disabled="busy" :aria-label="purchase.foodName" @update:model-value="checkPurchase(purchase, false)" />
              <div>
                <span>{{ purchase.foodName }}</span><p class="text-caption text-medium-emphasis">
                  {{ purchase.items.map(item => item.display).join(' + ') }} · {{ storeTitle(purchase.store) }}
                </p>
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
      <v-btn v-if="view.shoppingList" variant="text" :to="`/shopping-lists/${view.shoppingList.id}`">
        {{ $t('groceries.stock-list') }}
      </v-btn>
    </template>
    <div class="text-caption text-medium-emphasis mt-6">
      <a href="/api/households/groceries/source">{{ $t('groceries.source') }}</a> · Mealie / AGPL-3.0
    </div>
    <v-dialog :model-value="!!assignment" max-width="560" :persistent="busy" @update:model-value="assignment = null">
      <v-card :title="$t('groceries.assignment-title')">
        <v-card-text>
          <p class="mb-4 text-body-2">
            {{ $t('groceries.assignment-hint') }}
          </p>
          <v-select v-model="assignmentChoice" :items="assignmentOptions" :label="$t('groceries.product-name')" />
          <v-select v-if="assignmentChoice === 'manual'" v-model="assignmentStore" :items="groceryStores" :label="$t('groceries.store')" />
        </v-card-text><v-card-actions>
          <v-spacer /><v-btn :disabled="busy" @click="assignment = null">
            {{ $t('groceries.cancel') }}
          </v-btn>
          <v-btn color="primary" variant="flat" :loading="busy" @click="saveAssignment">
            {{ $t('groceries.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog v-model="manualDialog" max-width="560" :persistent="busy">
      <v-card :title="$t('groceries.add-item')">
        <v-card-text>
          <v-autocomplete
            v-model="manual.foodId"
            :items="foods"
            item-title="name"
            item-value="id"
            clearable
            :label="$t('groceries.ingredient')"
          />
          <v-text-field v-model="manual.note" :label="$t('groceries.item-name')" :hint="$t('groceries.manual-item-hint')" persistent-hint class="mb-4" />
          <v-row>
            <v-col cols="6">
              <v-text-field v-model="manual.quantity" type="number" min="0.001" step="any" :label="$t('groceries.amount')" />
            </v-col>
            <v-col cols="6">
              <v-select v-model="manual.unit" :items="groceryUnits" :label="$t('groceries.unit')" />
            </v-col>
          </v-row>
          <v-select v-model="manual.store" :items="groceryStores" clearable :label="$t('groceries.store')" />
        </v-card-text><v-card-actions>
          <v-spacer /><v-btn :disabled="busy" @click="manualDialog = false">
            {{ $t('groceries.cancel') }}
          </v-btn>
          <v-btn color="primary" variant="flat" :loading="busy" :disabled="!manual.foodId && !manual.note.trim()" @click="addManual">
            {{ $t('groceries.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog :model-value="!!plannedSuggestion" max-width="440" :persistent="busy" @update:model-value="plannedSuggestion = null">
      <v-card :title="$t('groceries.add-to-plan')">
        <v-card-text>
          <p class="mb-4">
            {{ plannedSuggestion?.recipe.name }}
          </p>
          <v-text-field v-model="suggestionDate" type="date" :label="$t('groceries.choose-date')" />
        </v-card-text>
        <v-card-actions>
          <v-spacer /><v-btn :disabled="busy" @click="plannedSuggestion = null">
            {{ $t('groceries.cancel') }}
          </v-btn>
          <v-btn color="primary" variant="flat" :loading="busy" @click="addSuggestion">
            {{ $t('groceries.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { useIntervalFn } from "@vueuse/core";
import { useGroceryWeek } from "~/composables/groceries/use-grocery-week";
import { useGroceryCatalog } from "~/composables/groceries/use-grocery-catalog";
import { groceryError, groceryStores, groceryUnits, isoLocalDate, mondayFor, storeTitle, unitTitle } from "~/composables/groceries/grocery-utils";
import type { GroceryPurchaseOut, GroceryStore, GrocerySuggestionOut, GroceryUnit, GroceryWeekGenerate } from "~/lib/api/types/grocery";

definePageMeta({ middleware: ["household-only"] });
const route = useRoute();
const auth = useMealieAuth();
const i18n = useI18n();
const initialDate = typeof route.query.week === "string" && /^\d{4}-\d{2}-\d{2}$/.test(route.query.week) ? route.query.week : isoLocalDate(new Date());
const weekStart = ref(mondayFor(initialDate));
const dateInput = ref(weekStart.value);
const { api, view, suggestions, busy, loading, error, load, loadSuggestions, mutate } = useGroceryWeek(weekStart);
const { products, foods, error: catalogError, load: loadCatalog } = useGroceryCatalog();
const selectedStores = ref<GroceryStore[]>(groceryStores.map(store => store.value));
const skipOnHand = ref(true);
const mealScales = ref<Record<string, number | string>>({});
const storeFilter = ref<string>("all");
const copied = ref(false);
const manualDialog = ref(false);
const manual = reactive<{ foodId: string | null; note: string; quantity: number | string; unit: GroceryUnit; store: GroceryStore | null }>({ foodId: null, note: "", quantity: 1, unit: "count", store: null });
const assignment = ref<GroceryPurchaseOut | null>(null);
const assignmentChoice = ref("automatic");
const assignmentStore = ref<GroceryStore>("walmart");
const plannedSuggestion = ref<GrocerySuggestionOut | null>(null);
const suggestionDate = ref(weekStart.value);
const revision = computed(() => view.value?.week?.revision ?? 0);
const scheduledMeals = computed(() => (view.value?.meals ?? []).filter(meal => meal.entryType === "dinner" || meal.entryType === "side"));
const pendingPurchases = computed(() => (view.value?.purchases ?? []).filter(purchase => !purchase.items.every(item => item.checked)));
const checkedPurchases = computed(() => (view.value?.purchases ?? []).filter(purchase => purchase.items.every(item => item.checked)));
const visiblePending = computed(() => pendingPurchases.value.filter(purchase => storeFilter.value === "all" || (purchase.store ?? "unassigned") === storeFilter.value));
const effectiveScales = computed(() => Object.fromEntries(scheduledMeals.value.filter(meal => meal.recipeId).map(meal => [String(meal.id), Number(mealScales.value[String(meal.id)] ?? 1)])));
const formDirty = computed(() => !!view.value?.week && (
  JSON.stringify(selectedStores.value) !== JSON.stringify(view.value.week.stores)
  || skipOnHand.value !== view.value.week.skipOnHand
  || JSON.stringify(effectiveScales.value) !== JSON.stringify(view.value.week.mealScales)
));
const storeSections = computed(() => {
  const stores = [...groceryStores.map(store => store.value), null];
  return stores.map((store) => {
    const purchases = visiblePending.value.filter(purchase => purchase.store === store);
    const byAisle = new Map<string, GroceryPurchaseOut[]>();
    for (const purchase of purchases) {
      const aisle = purchase.items[0]?.label?.name ?? i18n.t("groceries.general-aisle");
      byAisle.set(aisle, [...(byAisle.get(aisle) ?? []), purchase]);
    }
    return { store, aisles: Array.from(byAisle, ([name, aislePurchases]) => ({ name, purchases: aislePurchases })) };
  }).filter(section => section.aisles.length);
});
const assignmentOptions = computed(() => {
  const foodId = assignment.value?.items[0]?.foodId;
  return [
    { title: i18n.t("groceries.automatic"), value: "automatic" },
    ...products.value.filter(product => product.enabled && product.foodId === foodId).map(product => ({ title: `${storeTitle(product.store)} — ${product.name}`, value: product.id })),
    { title: i18n.t("groceries.manual-store"), value: "manual" },
  ];
});

watch(dateInput, (value) => { if (/^\d{4}-\d{2}-\d{2}$/.test(value)) weekStart.value = mondayFor(value); });
watch(view, (next, previous) => {
  if (!next) return;
  const wasDirty = previous?.week && (
    JSON.stringify(selectedStores.value) !== JSON.stringify(previous.week.stores)
    || skipOnHand.value !== previous.week.skipOnHand
    || JSON.stringify(effectiveScales.value) !== JSON.stringify(previous.week.mealScales)
  );
  if (!wasDirty || previous?.weekStart !== next.weekStart) {
    selectedStores.value = next.week?.stores ?? groceryStores.map(store => store.value);
    skipOnHand.value = next.week?.skipOnHand ?? true;
    mealScales.value = Object.fromEntries((next.meals ?? []).filter(meal => meal.recipeId).map(meal => [String(meal.id), next.week?.mealScales[String(meal.id)] ?? 1]));
  }
});
watch(weekStart, () => { suggestionDate.value = weekStart.value; });

function toggleStore(store: GroceryStore) {
  selectedStores.value = selectedStores.value.includes(store) ? selectedStores.value.filter(value => value !== store) : [...selectedStores.value, store];
}
function recipeLink(slug?: string | null) { return `/g/${auth.user.value?.groupSlug}/r/${slug}`; }
function friendlyDay(value: string) { return new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }); }
function storeColor(store?: string | null) { return groceryStores.find(item => item.value === store)?.color ?? "#8B8B8B"; }
function storeCount(store: string | null) { return pendingPurchases.value.filter(purchase => purchase.store === store).length; }
function isManualChoice(purchase: GroceryPurchaseOut) { return purchase.items.some(item => item.extras?.["shop.store_override"] || item.extras?.["shop.product_override"]); }
function manualIds(purchase: GroceryPurchaseOut) { return purchase.items.filter(item => item.extras?.["shop.source"] !== "week").map(item => item.id); }
async function refresh() { await Promise.all([load(), loadSuggestions(), loadCatalog()]); }
async function generate() {
  if (!selectedStores.value.length) return;
  await mutate(() => api.groceries.generate(weekStart.value, { stores: selectedStores.value as GroceryWeekGenerate["stores"], mealScales: effectiveScales.value, skipOnHand: skipOnHand.value, expectedRevision: revision.value }));
}
function itemIds(items: { id: string }[]): [string, ...string[]] {
  const [first, ...rest] = items;
  if (!first) throw new Error("The item changed. Refresh the list and try again.");
  return [first.id, ...rest.map(item => item.id)];
}
async function checkPurchase(purchase: GroceryPurchaseOut, checked: boolean) {
  await mutate(() => api.groceries.check(weekStart.value, { itemIds: itemIds(purchase.items), checked, expectedRevision: revision.value }));
}
function openAssignment(purchase: GroceryPurchaseOut) {
  assignment.value = purchase;
  const extras = purchase.items[0]?.extras;
  const productOverride = extras?.["shop.product_override"];
  assignmentChoice.value = typeof productOverride === "string" ? productOverride : (extras?.["shop.store_override"] ? "manual" : "automatic");
  assignmentStore.value = purchase.store ?? "walmart";
}
async function saveAssignment() {
  if (!assignment.value) return;
  const ok = await mutate(() => api.groceries.assign(weekStart.value, { itemIds: itemIds(assignment.value!.items), expectedRevision: revision.value, store: assignmentChoice.value === "manual" ? assignmentStore.value : null, productId: ["manual", "automatic"].includes(assignmentChoice.value) ? null : assignmentChoice.value }));
  if (ok) assignment.value = null;
}
async function addManual() {
  const ok = await mutate(() => api.groceries.addItem(weekStart.value, { ...manual, note: manual.note ?? "", quantity: Number(manual.quantity), expectedRevision: revision.value }));
  if (ok) { manualDialog.value = false; Object.assign(manual, { foodId: null, note: "", quantity: 1, unit: "count", store: null }); }
}
async function deleteManual(purchase: GroceryPurchaseOut) {
  await mutate(() => api.groceries.deleteItems(weekStart.value, { itemIds: itemIds(manualIds(purchase).map(id => ({ id }))), expectedRevision: revision.value }));
}
async function addSuggestion() {
  if (!plannedSuggestion.value) return;
  busy.value = true;
  try {
    const result = await api.mealplans.createOne({ date: suggestionDate.value, entryType: "dinner", recipeId: plannedSuggestion.value.recipe.id });
    if (!result.data) throw result.error;
    plannedSuggestion.value = null;
    await Promise.all([load(), loadSuggestions()]);
  }
  catch (cause) { error.value = groceryError(cause); }
  finally { busy.value = false; }
}
async function copyList() {
  const text = storeSections.value.map(section => `${storeTitle(section.store)}\n${section.aisles.flatMap(aisle => aisle.purchases.map(purchase => `☐ ${purchase.foodName}${purchase.product ? ` — ${purchase.product.name}` : ""}${purchase.packageCount != null ? ` (${purchase.packageCount} packages)` : `: ${purchase.items.map(item => item.display).join(" + ")}`}${purchase.product?.url ? `\n  ${purchase.product.url}` : ""}`)).join("\n")}`).join("\n\n");
  try { await navigator.clipboard.writeText(text); copied.value = true; }
  catch (cause) { error.value = groceryError(cause); }
}
useIntervalFn(() => { if (!busy.value && !loading.value && !formDirty.value && !manualDialog.value && !assignment.value) void load(); }, 12000);
onMounted(refresh);
</script>

<style scoped>
.groceries-page {
  padding-top: 28px;
  padding-bottom: 72px;
}
.control-card,
.plan-card,
.purchase-card {
  border-radius: 14px;
}
.date-field {
  max-width: 220px;
  min-width: 160px;
}
.scale-field {
  flex: 0 0 130px;
  max-width: 130px;
}
.meal-date {
  min-width: 95px;
}
.meal-row + .meal-row,
.suggestion-row + .suggestion-row {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.09);
}
.recipe-link {
  color: inherit;
  text-decoration: none;
}
.recipe-link:hover {
  text-decoration: underline;
}
.store-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}
.purchase-detail {
  min-width: 0;
}
@media (max-width: 600px) {
  .groceries-page {
    padding-left: 12px;
    padding-right: 12px;
  }
  .meal-date {
    min-width: 64px;
    max-width: 72px;
    font-size: 12px !important;
  }
  .scale-field {
    flex-basis: 98px;
    max-width: 98px;
  }
}
</style>
