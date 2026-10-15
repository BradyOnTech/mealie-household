<template>
  <div class="groceries-page paper-container">
    <header class="groceries-head">
      <div>
        <span class="paper-kicker">{{ $t('groceries.kicker', { week: weekNumber }) }}</span>
        <h1 class="groceries-head__title paper-headline">
          {{ $t('groceries.shop-title') }}
        </h1>
        <p class="groceries-head__dek">
          <template v-if="view?.week">
            {{ $t('groceries.left-of', { left: pendingPurchases.length, total: purchaseCount }) }}<template v-if="chosenStoreNames">
              · {{ chosenStoreNames }}
            </template>
          </template>
          <template v-else>
            {{ $t('groceries.subtitle') }}
          </template>
        </p>
      </div>
      <v-btn variant="text" :prepend-icon="$globals.icons.cartCheck" to="/household/groceries/products" class="groceries-head__catalog">
        {{ $t('groceries.catalog') }}
      </v-btn>
    </header>

    <v-alert v-if="error || catalogError" type="error" closable class="mb-4" @click:close="error = ''; catalogError = ''">
      {{ error || catalogError }}
    </v-alert>

    <section class="groceries-plan">
      <button type="button" class="groceries-plan__toggle" :aria-expanded="planOpen" @click="planOpen = !planOpen">
        <span class="groceries-plan__title">{{ $t('groceries.the-plan') }}</span>
        <span class="groceries-plan__summary">{{ planSummary }}</span>
        <v-icon size="20" :icon="planOpen ? $globals.icons.chevronUp : $globals.icons.chevronDown" />
      </button>
      <v-expand-transition>
        <div v-show="planOpen" class="groceries-plan__body">
          <div class="groceries-controls">
            <v-text-field
              v-model="dateInput"
              type="date"
              :label="$t('groceries.week-of')"
              :disabled="busy"
              hide-details
              density="compact"
              class="date-field"
            />
            <div class="groceries-stores" role="group" :aria-label="$t('groceries.stores-this-week')">
              <span class="groceries-label">{{ $t('groceries.stores-this-week') }}</span>
              <div class="groceries-stores__options">
                <button
                  v-for="store in groceryStores"
                  :key="store.value"
                  type="button"
                  role="checkbox"
                  class="store-toggle"
                  :class="{ 'store-toggle--on': selectedStores.includes(store.value) }"
                  :style="{ '--store-color': store.color }"
                  :aria-checked="selectedStores.includes(store.value)"
                  :disabled="busy"
                  @click="toggleStore(store.value)"
                >
                  <i />{{ store.title }}
                </button>
              </div>
            </div>
          </div>
          <div class="groceries-controls groceries-controls--second">
            <v-checkbox
              v-model="skipOnHand"
              :label="$t('groceries.skip-on-hand')"
              :hint="$t('groceries.skip-hint')"
              persistent-hint
              hide-details="auto"
              density="compact"
              class="groceries-skip"
            />
            <div class="groceries-controls__actions">
              <v-btn :disabled="busy" variant="text" @click="refresh">
                {{ $t('groceries.refresh') }}
              </v-btn>
              <v-btn color="primary" :loading="busy" :disabled="busy || !selectedStores.length || loading" @click="generate">
                {{ $t(view?.week ? 'groceries.update-week' : 'groceries.generate') }}
              </v-btn>
            </div>
          </div>
          <v-alert v-if="view?.week && formDirty" type="info" density="compact" class="mt-3">
            {{ $t('groceries.changes-pending') }}
          </v-alert>

          <div class="groceries-plan__grid">
            <div>
              <h3 class="groceries-subhead">
                {{ $t('groceries.dinners') }}
                <NuxtLink to="/household/mealplan/planner/edit" class="groceries-subhead__link">
                  {{ $t('groceries.plan-dinners') }}
                </NuxtLink>
              </h3>
              <p v-if="!scheduledMeals.length" class="groceries-muted py-4">
                {{ $t('groceries.no-dinners') }}
              </p>
              <div v-for="meal in scheduledMeals" :key="meal.id" class="meal-row">
                <div class="meal-row__day">
                  {{ friendlyDay(meal.date) }}
                </div>
                <div class="meal-row__main">
                  <NuxtLink v-if="meal.recipe" :to="recipeLink(meal.recipe.slug)" class="meal-row__title">
                    {{ meal.recipe.name }}
                  </NuxtLink>
                  <span v-else class="meal-row__title">{{ meal.title }}</span>
                  <span class="meal-row__type">{{ meal.entryType }}</span>
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
                  class="scale-field"
                  :disabled="busy"
                />
              </div>
              <p v-if="scheduledMeals.some(meal => meal.recipeId)" class="groceries-hint mt-3">
                {{ $t('groceries.multiplier-hint') }}
              </p>
            </div>
            <aside class="groceries-ideas">
              <h3 class="groceries-subhead">
                {{ $t('groceries.suggestions') }}
              </h3>
              <p class="groceries-hint mb-2">
                {{ $t('groceries.suggestions-hint') }}
              </p>
              <p v-if="!suggestions.length" class="groceries-muted">
                {{ $t('groceries.no-suggestions') }}
              </p>
              <div v-for="suggestion in suggestions.slice(0, 3)" :key="suggestion.recipe.id ?? suggestion.recipe.slug ?? 'suggestion'" class="idea-row">
                <NuxtLink :to="recipeLink(suggestion.recipe.slug)" class="idea-row__title">
                  {{ suggestion.recipe.name }}
                </NuxtLink>
                <p class="groceries-hint">
                  {{ suggestion.reasons.join(' · ') }}
                </p>
                <button type="button" class="paper-link idea-row__add" :disabled="busy" @click="plannedSuggestion = suggestion">
                  {{ $t('groceries.add-to-plan') }}
                </button>
              </div>
            </aside>
          </div>
        </div>
      </v-expand-transition>
    </section>

    <v-progress-linear v-if="loading" indeterminate color="tomato" class="mb-4" />
    <v-alert v-for="warning in view?.warnings ?? []" :key="warning" type="warning" class="mb-3">
      {{ warning }}
    </v-alert>

    <section v-if="!view?.week && !loading" class="groceries-empty paper-box">
      <h2 class="groceries-empty__title">
        {{ $t('groceries.no-list') }}
      </h2>
      <p class="groceries-muted mb-4">
        {{ $t('groceries.no-list-detail') }}
      </p>
      <v-btn color="primary" :loading="busy" :disabled="busy || !selectedStores.length" @click="generate">
        {{ $t('groceries.generate') }}
      </v-btn>
    </section>

    <template v-if="view?.week">
      <h2 class="groceries-list-title">
        {{ $t('groceries.the-list') }}
        <span>{{ pendingPurchases.length }} {{ $t('groceries.remaining') }}</span>
      </h2>
      <div class="groceries-tabs" role="tablist" :aria-label="$t('groceries.store')">
        <button
          v-for="tab in storeTabs"
          :key="tab.value"
          type="button"
          role="tab"
          class="groceries-tab"
          :class="{ 'groceries-tab--active': storeFilter === tab.value }"
          :style="{ '--store-color': tab.color }"
          :aria-selected="storeFilter === tab.value"
          @click="storeFilter = tab.value"
        >
          {{ tab.title }}<em>{{ tab.count }}</em>
        </button>
      </div>
      <div class="groceries-tools">
        <v-btn variant="text" size="small" :prepend-icon="$globals.icons.createAlt" :disabled="busy" @click="manualDialog = true">
          {{ $t('groceries.add-item') }}
        </v-btn>
        <v-btn variant="text" size="small" :prepend-icon="$globals.icons.contentCopy" @click="copyList">
          {{ copied ? $t('groceries.copied') : $t('groceries.copy') }}
        </v-btn>
        <v-btn v-if="view.shoppingList" variant="text" size="small" :prepend-icon="$globals.icons.formatListCheck" :to="`/shopping-lists/${view.shoppingList.id}`">
          {{ $t('groceries.stock-list') }}
        </v-btn>
      </div>

      <p v-if="!visiblePending.length" class="groceries-done">
        {{ $t('groceries.nothing-needed') }}
      </p>

      <section
        v-for="section in listSections"
        :key="section.store ?? 'unassigned'"
        class="store-section"
        :style="{ '--store-color': storeColor(section.store) }"
      >
        <h2 class="store-section__title">
          <i />{{ section.store ? storeTitle(section.store) : $t('groceries.unassigned') }}
          <small>{{ $t('groceries.left-in-store', { count: section.left }) }}</small>
        </h2>
        <div v-for="aisle in section.aisles" :key="aisle.name" class="aisle">
          <h3 class="aisle__title">
            {{ aisle.name }}
          </h3>
          <div
            v-for="purchase in aisle.purchases"
            :key="purchase.key"
            class="purchase"
            :class="{ 'purchase--done': isDone(purchase) }"
          >
            <v-checkbox-btn
              class="purchase__check"
              :model-value="isDone(purchase)"
              color="secondary"
              :false-icon="$globals.icons.checkboxBlankCircleOutline"
              :true-icon="$globals.icons.checkboxMarkedCircle"
              :disabled="busy"
              :aria-label="purchase.foodName"
              @update:model-value="checkPurchase(purchase, !!$event)"
            />
            <div class="purchase__body">
              <div class="purchase__name">
                {{ purchase.foodName }}
                <span v-if="isManualChoice(purchase)" class="purchase__badge">{{ $t('groceries.this-week') }}</span>
              </div>
              <div v-if="purchase.product" class="purchase__product">
                {{ purchase.product.name }}
                <a
                  v-if="purchase.product.url"
                  :href="purchase.product.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="purchase__link"
                  :aria-label="$t('groceries.open-product')"
                  @click.stop
                >
                  <v-icon size="14" :icon="$globals.icons.externalLink" />
                </a>
              </div>
              <div v-if="purchase.packageCount != null" class="purchase__buy">
                {{ $t('groceries.buy') }} {{ purchase.packageCount }} × {{ purchase.product?.packageQuantity }} {{ unitTitle(purchase.product?.packageUnit) }}
              </div>
              <div class="purchase__needs">
                {{ purchase.items.map(item => item.display).join(' + ') }}
              </div>
              <div v-if="purchase.quantityNote" class="purchase__warn">
                {{ purchase.quantityNote }}
              </div>
              <div v-if="purchase.product?.notes" class="purchase__note">
                {{ purchase.product.notes }}
              </div>
            </div>
            <v-menu location="bottom end" :offset="4">
              <template #activator="{ props: menuProps }">
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  class="purchase__more"
                  :aria-label="$t('groceries.item-actions', { name: purchase.foodName })"
                  v-bind="menuProps"
                >
                  <v-icon :icon="$globals.icons.dotsVertical" />
                </v-btn>
              </template>
              <v-list density="compact" min-width="240">
                <v-list-item
                  v-if="purchase.product?.url"
                  :href="purchase.product.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  :prepend-icon="$globals.icons.externalLink"
                  :title="$t('groceries.open-product')"
                />
                <v-list-item
                  :prepend-icon="$globals.icons.swapHorizontal"
                  :title="$t('groceries.assign')"
                  :disabled="busy"
                  @click="openAssignment(purchase)"
                />
                <v-list-item
                  v-if="!purchase.product && purchase.items[0]?.foodId"
                  :prepend-icon="$globals.icons.cartCheck"
                  :title="$t('groceries.add-product')"
                  :to="`/household/groceries/products?food_id=${purchase.items[0].foodId}`"
                />
                <v-list-item
                  v-if="manualIds(purchase).length"
                  :prepend-icon="$globals.icons.delete"
                  :title="$t('groceries.delete-manual')"
                  :disabled="busy"
                  @click="deleteManual(purchase)"
                />
              </v-list>
            </v-menu>
          </div>
        </div>
      </section>
    </template>
    <div class="groceries-source">
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
  </div>
</template>

<script setup lang="ts">
import { useIntervalFn } from "@vueuse/core";
import { getISOWeek } from "date-fns";
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
// Display helpers for the redesigned list.
const { smAndDown } = useDisplay();
const planOpen = ref(true);
const weekNumber = computed(() => getISOWeek(new Date(`${weekStart.value}T12:00:00`)));
const purchaseCount = computed(() => (view.value?.purchases ?? []).length);
const chosenStoreNames = computed(() =>
  new Intl.ListFormat(i18n.locale.value, { style: "long", type: "conjunction" })
    .format((view.value?.week?.stores ?? []).map(store => storeTitle(store))),
);
const planSummary = computed(() => {
  const dinners = scheduledMeals.value.filter(meal => meal.entryType === "dinner").length;
  return i18n.t("groceries.plan-summary", {
    dinners: i18n.t("groceries.dinner-count", dinners),
    stores: i18n.t("groceries.store-count", selectedStores.value.length),
  });
});
function isDone(purchase: GroceryPurchaseOut) { return purchase.items.every(item => item.checked); }
const storeTabs = computed(() => {
  const unassigned = storeCount(null);
  return [
    { value: "all", title: i18n.t("groceries.all-stores"), color: "rgb(var(--v-theme-on-background))", count: pendingPurchases.value.length },
    ...groceryStores
      .filter(store => storeCount(store.value) > 0 || selectedStores.value.includes(store.value))
      .map(store => ({ value: store.value as string, title: store.title, color: store.color, count: storeCount(store.value) })),
    ...(unassigned ? [{ value: "unassigned", title: i18n.t("groceries.unassigned"), color: "rgb(var(--v-theme-ink-muted))", count: unassigned }] : []),
  ];
});
// Checked items stay in their aisle, struck through, after the ones still to find.
const listSections = computed(() => {
  const stores = [...groceryStores.map(store => store.value), null];
  const visible = (view.value?.purchases ?? []).filter(purchase => storeFilter.value === "all" || (purchase.store ?? "unassigned") === storeFilter.value);
  return stores.map((store) => {
    const purchases = visible.filter(purchase => purchase.store === store);
    const byAisle = new Map<string, GroceryPurchaseOut[]>();
    for (const purchase of purchases) {
      const aisle = purchase.items[0]?.label?.name ?? i18n.t("groceries.general-aisle");
      byAisle.set(aisle, [...(byAisle.get(aisle) ?? []), purchase]);
    }
    const aisles = Array.from(byAisle, ([name, aislePurchases]) => ({
      name,
      purchases: [...aislePurchases].sort((a, b) => Number(isDone(a)) - Number(isDone(b))),
    }));
    return { store, aisles, left: purchases.filter(purchase => !isDone(purchase)).length };
  }).filter(section => section.aisles.length);
});
// On phones the list leads; the plan folds away once there is a list to shop from.
const stopPlanWatch = watch(view, (next) => {
  if (!next) return;
  planOpen.value = !(next.week && smAndDown.value);
  stopPlanWatch();
});

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
  padding-top: 32px;
  padding-bottom: 72px;
}

.groceries-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px 24px;
  margin-bottom: 26px;
}

.groceries-head__title {
  margin: 6px 0 6px;
  font-size: 3rem;
}

.groceries-head__dek {
  margin: 0;
  font-size: 0.9375rem;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-plan {
  margin-bottom: 30px;
}

.groceries-plan__toggle {
  appearance: none;
  display: flex;
  align-items: baseline;
  gap: 14px;
  width: 100%;
  padding: 0 0 8px;
  border: 0;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.groceries-plan__toggle .v-icon {
  align-self: center;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-plan__title {
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 450;
  letter-spacing: -0.01em;
}

.groceries-plan__summary {
  margin-left: auto;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-plan__body {
  padding-top: 18px;
}

.groceries-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px 28px;
}

.groceries-controls--second {
  margin-top: 10px;
}

.groceries-controls__actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.date-field {
  max-width: 200px;
  min-width: 160px;
}

.groceries-label {
  display: block;
  margin-bottom: 6px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-stores__options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.store-toggle {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 999px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-ink-muted));
  font: inherit;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.store-toggle i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  box-shadow: inset 0 0 0 1.5px var(--store-color);
}

.store-toggle--on {
  border-color: rgb(var(--v-theme-on-background));
  color: rgb(var(--v-theme-on-background));
}

.store-toggle--on i {
  background: var(--store-color);
  box-shadow: none;
}

.store-toggle:disabled {
  opacity: 0.6;
  cursor: default;
}

.store-toggle:focus-visible,
.groceries-tab:focus-visible,
.groceries-plan__toggle:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.groceries-skip {
  flex: 1 1 320px;
}

.groceries-plan__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 44px;
  margin-top: 22px;
}

.groceries-subhead {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0 0 4px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  font-family: var(--paper-serif);
  font-size: 1.125rem;
  font-weight: 450;
}

.groceries-subhead__link {
  margin-left: auto;
  font-family: var(--paper-sans);
  font-size: 0.8125rem;
  font-weight: 600;
  color: rgb(var(--v-theme-tomato));
  text-decoration: none;
}

.groceries-muted {
  margin: 0;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-hint {
  margin: 0;
  font-size: 0.78125rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
}

.meal-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.meal-row__day {
  flex: none;
  width: 104px;
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.meal-row__main {
  flex: 1;
  min-width: 0;
}

.meal-row__title {
  display: block;
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  line-height: 1.25;
  color: inherit;
  text-decoration: none;
}

a.meal-row__title:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.meal-row__type {
  font-size: 0.75rem;
  color: rgb(var(--v-theme-ink-muted));
}

.scale-field {
  flex: 0 0 156px;
  max-width: 156px;
}

.idea-row {
  padding: 10px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.idea-row__title {
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  color: inherit;
  text-decoration: none;
}

.idea-row__title:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.idea-row__add {
  appearance: none;
  margin-top: 4px;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 600;
}

.groceries-empty {
  padding: 28px 28px 30px;
  text-align: center;
}

.groceries-empty__title {
  margin-bottom: 6px;
  font-family: var(--paper-serif);
  font-size: 1.5rem;
  font-weight: 420;
}

.groceries-list-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 450;
  letter-spacing: -0.01em;
}

.groceries-list-title span {
  margin-left: auto;
  font-family: var(--paper-sans);
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: 0;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-tabs {
  display: flex;
  gap: 22px;
  overflow-x: auto;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  scrollbar-width: none;
}

.groceries-tabs::-webkit-scrollbar {
  display: none;
}

.groceries-tab {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: -1px;
  padding: 12px 0 10px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  color: rgb(var(--v-theme-ink-muted));
  font: inherit;
  font-size: 0.9375rem;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}

.groceries-tab em {
  font-style: normal;
  font-size: 0.75rem;
  font-weight: 400;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-tab--active {
  border-bottom-color: var(--store-color);
  color: rgb(var(--v-theme-on-background));
  font-weight: 600;
}

.groceries-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 8px 0 4px -12px;
}

.groceries-done {
  padding: 28px 0;
  font-family: var(--paper-serif);
  font-size: 1.125rem;
  font-style: italic;
  text-align: center;
  color: rgb(var(--v-theme-ink-muted));
}

.store-section {
  margin-top: 26px;
}

.store-section__title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-family: var(--paper-serif);
  font-size: 1.5rem;
  font-weight: 420;
  letter-spacing: -0.015em;
}

.store-section__title i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--store-color);
}

.store-section__title small {
  margin-left: auto;
  font-family: var(--paper-sans);
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: 0;
  color: rgb(var(--v-theme-ink-muted));
}

.aisle__title {
  margin: 14px 0 0;
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  font-style: italic;
  font-weight: 400;
  color: rgb(var(--v-theme-ink-muted));
}

.purchase {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  align-items: start;
  gap: 6px;
  padding: 8px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.purchase__check {
  grid-area: auto;
  grid-column: 1;
  grid-row: 1;
  margin-top: -6px;
}

.purchase__body {
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
  padding-top: 2px;
}

.purchase__name {
  font-size: 1.0625rem;
  font-weight: 500;
  line-height: 1.3;
}

.purchase__name::first-letter {
  text-transform: uppercase;
}

.purchase__badge {
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgb(var(--v-theme-wash));
  font-size: 0.6875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-tomato));
  vertical-align: 2px;
}

.purchase__product {
  margin-top: 2px;
  font-size: 0.875rem;
}

.purchase__link {
  margin-left: 2px;
  color: rgb(var(--v-theme-tomato));
}

.purchase__buy {
  margin-top: 2px;
  font-family: var(--paper-serif);
  font-size: 0.9375rem;
}

.purchase__needs,
.purchase__note {
  margin-top: 2px;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
}

.purchase__warn {
  margin-top: 2px;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-warning));
}

.purchase__more {
  grid-column: 3;
  grid-row: 1;
  color: rgb(var(--v-theme-ink-muted));
}

.purchase--done .purchase__name {
  color: rgb(var(--v-theme-ink-muted));
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}

.purchase--done .purchase__product,
.purchase--done .purchase__buy,
.purchase--done .purchase__needs,
.purchase--done .purchase__note {
  opacity: 0.55;
}

.groceries-source {
  margin-top: 40px;
  font-size: 0.75rem;
  color: rgb(var(--v-theme-ink-muted));
}

.groceries-source a {
  color: inherit;
}

@media (max-width: 959px) {
  .groceries-page {
    padding-top: 22px;
  }

  .groceries-head__title {
    font-size: 2.25rem;
  }

  .groceries-head__catalog {
    margin-left: -12px;
  }

  .groceries-plan__grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 28px;
  }

  .groceries-controls__actions {
    margin-left: 0;
  }

  .meal-row {
    flex-wrap: wrap;
  }

  .meal-row__day {
    width: 100%;
  }

  .scale-field {
    flex-basis: 110px;
  }
}
</style>
