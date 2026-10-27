<template>
  <!-- A steady height, so the dialog doesn't jump around as a search narrows the list -->
  <v-dialog v-model="opened" :fullscreen="smAndDown" :height="smAndDown ? undefined : 760" max-width="600" scrollable>
    <v-card class="common-items">
      <header class="common-items__head">
        <div>
          <span class="paper-kicker">{{ $t("common-items.kicker") }}</span>
          <h2 class="common-items__title">
            {{ $t("common-items.title") }}
          </h2>
          <p class="common-items__where">
            {{ whereSentence }}
          </p>
        </div>
        <v-btn icon variant="text" size="small" :aria-label="$t('common-items.close')" @click="opened = false">
          <v-icon :icon="$globals.icons.close" />
        </v-btn>
      </header>

      <div v-if="items.length" class="common-items__tools">
        <v-text-field
          v-model="search"
          :placeholder="$t('common-items.search')"
          :aria-label="$t('common-items.search')"
          :prepend-inner-icon="$globals.icons.search"
          clearable
          hide-details
          density="compact"
          rounded="pill"
          autocomplete="off"
        />
        <div v-if="storeOptions.length > 2" class="common-items__stores" role="group" :aria-label="$t('common-items.stores')">
          <button
            v-for="option in storeOptions"
            :key="option.value ?? 'all'"
            type="button"
            class="common-store"
            :class="{ 'common-store--on': store === option.value }"
            :style="{ '--store-color': option.color }"
            :aria-pressed="store === option.value"
            @click="store = option.value"
          >
            <i v-if="option.value" />{{ option.title }}
          </button>
        </div>
      </div>

      <v-card-text class="common-items__body">
        <v-progress-linear v-if="loading && !common" indeterminate color="tomato" class="mt-4" />
        <v-alert
          v-if="error || restockError"
          type="error"
          density="compact"
          class="mt-4"
          closable
          @click:close="error = ''; restockError = ''"
        >
          {{ error || restockError }}
        </v-alert>
        <p v-if="notice" class="common-items__notice" role="status">
          {{ notice }}
        </p>

        <section v-for="aisle in aisles" :key="aisle.name" class="common-aisle">
          <h3 v-if="showAisles" class="common-aisle__title">
            {{ aisle.name || $t("groceries.general-aisle") }}
          </h3>
          <ul class="common-aisle__rows">
            <li v-for="row in aisle.rows" :key="row.item.food.id">
              <button
                type="button"
                class="common-row"
                :class="{ 'common-row--added': isAdded(row) }"
                :aria-pressed="isAdded(row)"
                @click="toggle(row)"
              >
                <span class="common-row__body">
                  <span class="common-row__name">{{ row.item.food.name }}</span>
                  <span class="common-row__product" :style="{ '--store-color': storeColor(row.product.store) }">
                    <i />{{ productLine(row) }}
                  </span>
                  <span v-if="statusLabel(row)" class="common-row__status">{{ statusLabel(row) }}</span>
                </span>
                <span class="common-row__mark" aria-hidden="true">
                  <v-icon :icon="isAdded(row) ? $globals.icons.check : $globals.icons.createAlt" size="20" />
                </span>
              </button>
            </li>
          </ul>
        </section>

        <div v-if="items.length && !aisles.length && query" class="common-items__none">
          <p>{{ $t("common-items.no-match", { search: query }) }}</p>
          <v-btn variant="outlined" :prepend-icon="$globals.icons.createAlt" @click="addTyped">
            {{ $t("common-items.add-typed", { name: query }) }}
          </v-btn>
        </div>

        <div v-if="common && !items.length" class="common-items__empty">
          <h3 class="common-items__empty-title">
            {{ $t("common-items.empty") }}
          </h3>
          <p class="common-items__empty-detail">
            {{ $t("common-items.empty-detail") }}
          </p>
          <v-btn color="primary" to="/household/groceries/products" @click="opened = false">
            {{ $t("groceries.catalog") }}
          </v-btn>
        </div>
      </v-card-text>

      <footer class="common-items__foot">
        <NuxtLink v-if="items.length" to="/household/groceries/products" class="paper-link common-items__manage" @click="opened = false">
          {{ $t("common-items.manage") }}
        </NuxtLink>
        <v-spacer />
        <v-btn color="primary" variant="flat" @click="opened = false">
          {{ $t("common-items.done") }}
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useGroceryCommonItems } from "~/composables/groceries/use-grocery-common-items";
import { useGroceryRestock } from "~/composables/groceries/use-grocery-restock";
import { commonItemAisles, commonItemStore, formatWeek, groceryStores, isoLocalDate, mondayFor, storeTitle } from "~/composables/groceries/grocery-utils";
import type { CommonItemRow } from "~/composables/groceries/grocery-utils";
import type { GroceryStore } from "~/lib/api/types/grocery";

const opened = defineModel<boolean>({ default: false });

const i18n = useI18n();
const { smAndDown } = useDisplay();
const { common, items, loading, error, load } = useGroceryCommonItems();
// Adding goes on the Out of list, which keeps it on the newest list until it's bought
const { list, items: outOf, error: restockError, load: loadRestock, add, remove } = useGroceryRestock();

const search = ref("");
const store = ref<GroceryStore | null>(null);
const notice = ref("");
/** A tapped row's state, until the Out of list catches up with the tap. Shallow, so a tap is still itself when it settles. */
const pending = shallowReactive(new Map<string, { added: boolean; store: GroceryStore | null }>());
let queue: Promise<unknown> = Promise.resolve();

const query = computed(() => (search.value ?? "").trim());
const aisles = computed(() => commonItemAisles(items.value, store.value, query.value));
const showAisles = computed(() => aisles.value.length > 1 || !!aisles.value[0]?.name);
const storeOptions = computed(() => [
  { value: null, title: i18n.t("groceries.all-stores"), color: "rgb(var(--v-theme-on-background))" },
  ...groceryStores.filter(option => items.value.some(item => item.products.some(product => product.store === option.value))),
]);

const currentWeek = mondayFor(isoLocalDate(new Date()));
const whereSentence = computed(() => {
  const next = list.value ? list.value.nextListWeek : common.value?.nextListWeek;
  if (!next) return i18n.t("common-items.goes-on-next-list");
  return next === currentWeek
    ? i18n.t("common-items.goes-on-this-week")
    : i18n.t("common-items.goes-on-week", { week: formatWeek(next, i18n.locale.value) });
});

function storeColor(value: string) {
  return groceryStores.find(option => option.value === value)?.color;
}

function openItem(foodId: string) {
  return outOf.value.find(item => item.foodId === foodId);
}

function isAdded(row: CommonItemRow) {
  const tapped = pending.get(row.item.food.id);
  return tapped ? tapped.added : !!openItem(row.item.food.id);
}

/** The store an added item is on the list at, when that's known */
function addedStore(row: CommonItemRow) {
  const tapped = pending.get(row.item.food.id);
  const pinned = tapped ? tapped.store : openItem(row.item.food.id)?.store;
  if (pinned) return pinned;
  // Otherwise the list buys the item's first product, if its store is on the trip
  const first = row.item.products[0]?.store;
  return first && common.value?.stores?.includes(first) ? first : null;
}

function statusLabel(row: CommonItemRow) {
  if (isAdded(row)) {
    const where = addedStore(row);
    return where && where !== row.product.store
      ? i18n.t("common-items.added-at", { store: storeTitle(where) })
      : i18n.t("common-items.added");
  }
  return row.item.listed ? i18n.t("common-items.on-list") : "";
}

// The store is enough when the product is just called what the ingredient is
function productLine(row: CommonItemRow) {
  const where = storeTitle(row.product.store);
  return row.product.name.trim().toLowerCase() === row.item.food.name.trim().toLowerCase() ? where : `${where} · ${row.product.name}`;
}

/** Changes run one at a time, in the order they were tapped, so each answer includes the ones before it */
function enqueue(change: () => Promise<unknown>, settled?: () => void) {
  queue = queue.then(change).catch(() => undefined).finally(settled);
}

function toggle(row: CommonItemRow) {
  const food = row.item.food;
  const adding = !isAdded(row);
  const pinned = commonItemStore(row, store.value, common.value?.stores ?? []);
  const tapped = { added: adding, store: adding ? pinned : null };
  notice.value = "";
  pending.set(food.id, tapped);
  enqueue(async () => {
    const open = openItem(food.id);
    if (adding && !open) await add({ name: food.name, foodId: food.id, store: pinned });
    else if (!adding && open) await remove(open.id);
  }, () => {
    if (pending.get(food.id) === tapped) pending.delete(food.id);
  });
}

function addTyped() {
  const name = query.value;
  if (!name) return;
  const pinned = store.value;
  notice.value = "";
  enqueue(async () => {
    if (!await add({ name, store: pinned })) return;
    notice.value = i18n.t("common-items.typed-added", { name });
    if (query.value === name) search.value = "";
  });
}

watch(opened, (open) => {
  if (!open) return;
  search.value = "";
  store.value = null;
  notice.value = "";
  restockError.value = "";
  void Promise.all([load(), loadRestock()]);
}, { immediate: true });
</script>

<style scoped>
.common-items__head {
  display: flex;
  flex: none;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 16px 14px 24px;
}

.common-items__title {
  margin: 4px 0 6px;
  font-family: var(--paper-serif);
  font-size: 1.875rem;
  font-weight: 420;
  line-height: 1.1;
  letter-spacing: -0.015em;
}

.common-items__where {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
}

.common-items__tools {
  flex: none;
  padding: 0 24px 14px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.common-items__stores {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  overflow-x: auto;
  scrollbar-width: none;
}

.common-store {
  appearance: none;
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 13px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 999px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-ink-muted));
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}

.common-store i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--store-color);
}

.common-store--on {
  border-color: rgb(var(--v-theme-on-background));
  color: rgb(var(--v-theme-on-background));
}

.common-items__body.v-card-text {
  padding: 0 24px 16px;
}

.common-items__notice {
  margin: 14px 0 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-sage));
}

.common-aisle__title {
  margin: 18px 0 2px;
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  font-style: italic;
  font-weight: 400;
  color: rgb(var(--v-theme-ink-muted));
}

.common-aisle__rows {
  margin: 0;
  padding: 0;
  list-style: none;
}

.common-row {
  appearance: none;
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 11px 0;
  border: 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.common-row__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.common-row__name {
  font-size: 1.0625rem;
  font-weight: 500;
  line-height: 1.3;
}

.common-row__name::first-letter {
  text-transform: uppercase;
}

.common-row__product {
  font-size: 0.8125rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.common-row__product i {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--store-color);
  vertical-align: 1px;
}

.common-row__status {
  font-size: 0.75rem;
  font-style: italic;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.common-row--added .common-row__status {
  font-style: normal;
  font-weight: 600;
  color: rgb(var(--v-theme-sage));
}

.common-row__mark {
  display: grid;
  flex: none;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 50%;
  color: rgb(var(--v-theme-on-background));
  transition:
    background-color 0.15s,
    border-color 0.15s;
}

/* Only where hovering is real; a phone keeps :hover on whatever was tapped last */
@media (hover: hover) {
  .common-row:hover .common-row__mark {
    border-color: rgb(var(--v-theme-on-background));
  }
}

.common-row--added .common-row__mark,
.common-row--added:hover .common-row__mark {
  border-color: transparent;
  background: rgb(var(--v-theme-sage));
  color: rgb(var(--v-theme-on-sage));
}

.common-store:focus-visible,
.common-row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.common-items__none,
.common-items__empty {
  padding: 28px 0 8px;
  text-align: center;
}

.common-items__none p {
  margin: 0 0 14px;
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  font-style: italic;
  color: rgb(var(--v-theme-ink-muted));
}

.common-items__empty {
  padding-top: 64px;
}

.common-items__empty-title {
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 420;
}

.common-items__empty-detail {
  max-width: 42ch;
  margin: 10px auto 24px;
  font-size: 0.9375rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

.common-items__foot {
  display: flex;
  flex: none;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.common-items__manage {
  font-size: 0.875rem;
}

/* On phones the list gets the room */
@media (max-width: 959px) {
  .common-items__head {
    padding: 14px 8px 10px 20px;
  }

  .common-items__title {
    margin-bottom: 4px;
    font-size: 1.5rem;
  }

  .common-items__where {
    font-size: 0.8125rem;
  }

  .common-items__tools {
    padding: 0 20px 12px;
  }

  .common-items__stores {
    margin-top: 10px;
  }

  .common-items__body.v-card-text {
    padding: 0 20px 12px;
  }

  .common-items__foot {
    padding: 10px 20px;
  }
}
</style>
