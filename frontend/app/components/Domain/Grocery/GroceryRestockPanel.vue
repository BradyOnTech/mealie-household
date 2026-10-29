<template>
  <section class="restock" :class="compact ? 'restock--compact' : 'paper-box'">
    <template v-if="!compact">
      <span class="paper-kicker">{{ $t("restock.kicker") }}</span>
      <h3 class="restock__title">
        {{ $t("restock.title", items.length) }}
      </h3>
    </template>

    <form class="restock__add" @submit.prevent="add">
      <v-text-field
        v-model="name"
        :placeholder="$t('restock.placeholder')"
        :aria-label="$t('restock.placeholder')"
        :disabled="busy"
        density="compact"
        hide-details
        autocomplete="off"
        maxlength="255"
        class="restock__input"
      />
      <v-btn
        icon
        variant="text"
        :disabled="busy"
        :aria-label="$t('grocery-scan.scan-what-ran-out')"
        :title="$t('grocery-scan.scan-what-ran-out')"
        @click="scanOpen = true"
      >
        <v-icon :icon="$globals.icons.barcodeScan" />
      </v-btn>
      <v-btn type="submit" variant="outlined" :loading="busy" :disabled="!name.trim()">
        {{ $t("restock.add") }}
      </v-btn>
    </form>
    <GroceryRestockScan v-model="scanOpen" />
    <div class="restock__where-row">
      <p class="restock__where">
        {{ whereSentence }}
      </p>
      <button type="button" class="restock__common" @click="commonOpen = true">
        <v-icon size="16" :icon="$globals.icons.playlistPlus" />{{ $t("common-items.open") }}
      </button>
    </div>
    <v-alert
      v-if="error"
      type="error"
      density="compact"
      class="mt-2"
      closable
      @click:close="error = ''"
    >
      {{ error }}
    </v-alert>

    <template v-if="!compact">
      <ul v-if="items.length" class="restock__items">
        <li v-for="item in items" :key="item.id" class="restock-item">
          <v-checkbox-btn
            class="restock-item__check"
            :model-value="false"
            color="secondary"
            :false-icon="$globals.icons.checkboxBlankCircleOutline"
            :true-icon="$globals.icons.checkboxMarkedCircle"
            :disabled="busy"
            :aria-label="$t('restock.mark-bought', { name: item.name })"
            @update:model-value="markBought(item)"
          />
          <div class="restock-item__body">
            <div class="restock-item__name">
              {{ item.name }}
            </div>
            <div v-if="details(item)" class="restock-item__meta">
              {{ details(item) }}
            </div>
            <div class="restock-item__status">
              {{ statusLabel(item) }}
            </div>
          </div>
          <v-menu location="bottom end" :offset="4">
            <template #activator="{ props: menuProps }">
              <v-btn
                icon
                variant="text"
                size="small"
                class="restock-item__more"
                :aria-label="$t('groceries.item-actions', { name: item.name })"
                v-bind="menuProps"
              >
                <v-icon :icon="$globals.icons.dotsVertical" />
              </v-btn>
            </template>
            <v-list density="compact" min-width="200">
              <v-list-item :prepend-icon="$globals.icons.edit" :title="$t('groceries.edit')" @click="openEdit(item)" />
              <v-list-item
                :prepend-icon="$globals.icons.delete"
                :title="$t('restock.remove')"
                :disabled="busy"
                @click="remove(item)"
              />
            </v-list>
          </v-menu>
        </li>
      </ul>
      <p v-else-if="!loading" class="restock__empty">
        {{ $t("restock.empty") }}
      </p>

      <div v-if="recentlyBought.length" class="restock__bought">
        <span class="restock__bought-label">{{ $t("restock.bought-lately") }}</span>
        <button
          v-for="item in recentlyBought.slice(0, 8)"
          :key="item.id"
          type="button"
          class="restock__again"
          :disabled="busy"
          :title="$t('restock.out-again', { name: item.name })"
          @click="outAgain(item)"
        >
          + {{ item.name }}
        </button>
      </div>
    </template>

    <v-dialog :model-value="!!editing" max-width="480" :persistent="busy" @update:model-value="editing = null">
      <v-card :title="$t('restock.edit-title')">
        <v-card-text>
          <v-text-field v-model="form.name" :label="$t('restock.what')" maxlength="255" />
          <v-row>
            <v-col cols="6">
              <v-text-field
                v-model="form.quantity"
                type="number"
                min="0.001"
                step="any"
                :label="$t('groceries.amount')"
                :hint="$t('restock.amount-hint')"
                persistent-hint
              />
            </v-col>
            <v-col cols="6">
              <v-select v-model="form.unit" :items="groceryUnits" :label="$t('groceries.unit')" />
            </v-col>
          </v-row>
          <v-select v-model="form.store" :items="groceryStores" clearable :label="$t('groceries.store')" class="mt-2" />
          <v-text-field v-model="form.note" :label="$t('restock.note')" maxlength="2000" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn :disabled="busy" @click="editing = null">
            {{ $t("groceries.cancel") }}
          </v-btn>
          <v-btn color="primary" variant="flat" :loading="busy" :disabled="!form.name.trim()" @click="saveEdit">
            {{ $t("groceries.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <GroceryCommonItemsDialog v-model="commonOpen" />
  </section>
</template>

<script setup lang="ts">
import GroceryCommonItemsDialog from "./GroceryCommonItemsDialog.vue";
import { formatWeek, groceryStores, groceryUnits, isoLocalDate, mondayFor, storeTitle, unitTitle } from "~/composables/groceries/grocery-utils";
import GroceryRestockScan from "~/components/Domain/Grocery/GroceryRestockScan.vue";
import { useGroceryRestock } from "~/composables/groceries/use-grocery-restock";
import { alert } from "~/composables/use-toast";
import type { GroceryRestockOut, GroceryStore, GroceryUnit } from "~/lib/api/types/grocery";

const props = defineProps<{
  /** Just the quick add and where things go, for the top of the grocery list */
  compact?: boolean;
}>();

const i18n = useI18n();
const auth = useMealieAuth();
const { list, items, recentlyBought, busy, loading, error, load, add: addItem, update, remove: removeItem, setBought } = useGroceryRestock();

const name = ref("");
const commonOpen = ref(false);
const scanOpen = ref(false);
const editing = ref<GroceryRestockOut | null>(null);
const form = reactive<{ name: string; quantity: number | string; unit: GroceryUnit; store: GroceryStore | null; note: string }>({
  name: "", quantity: "", unit: "count", store: null, note: "",
});

const currentWeek = mondayFor(isoLocalDate(new Date()));

function weekLabel(week: string) {
  return formatWeek(week, i18n.locale.value);
}

const whereSentence = computed(() => {
  const next = list.value?.nextListWeek;
  if (!list.value) return "";
  if (!next) {
    const waiting = items.value.map(item => item.name);
    return waiting.length && props.compact
      ? i18n.t("restock.waiting-for-list", { items: new Intl.ListFormat(i18n.locale.value, { style: "long", type: "conjunction" }).format(waiting) })
      : i18n.t("restock.goes-on-next-list");
  }
  return next === currentWeek
    ? i18n.t("restock.goes-on-this-week")
    : i18n.t("restock.goes-on-week", { week: weekLabel(next) });
});

function statusLabel(item: GroceryRestockOut) {
  if (item.status === "listed" && item.weekStart) {
    return item.weekStart === currentWeek
      ? i18n.t("restock.on-this-week")
      : i18n.t("restock.on-week", { week: weekLabel(item.weekStart) });
  }
  return i18n.t("restock.waiting");
}

function details(item: GroceryRestockOut) {
  const parts: string[] = [];
  if (item.quantity) parts.push(`${item.quantity} ${item.unit && item.unit !== "count" ? unitTitle(item.unit) : ""}`.trim());
  if (item.store) parts.push(storeTitle(item.store));
  if (item.note) parts.push(item.note);
  if (item.addedBy && item.addedBy !== auth.user.value?.fullName) parts.push(i18n.t("restock.added-by", { name: item.addedBy }));
  return parts.join(" · ");
}

async function add() {
  const value = name.value.trim();
  if (!value) return;
  if (await addItem({ name: value })) name.value = "";
}

async function outAgain(item: GroceryRestockOut) {
  await addItem({ name: item.name, foodId: item.foodId, quantity: item.quantity, unit: item.unit, store: item.store, note: item.note ?? "" });
}

async function markBought(item: GroceryRestockOut) {
  if (await setBought(item.id, true)) {
    alert.success(i18n.t("restock.bought", { name: item.name }), null, {
      timeout: 6000,
      action: { message: i18n.t("restock.undo"), onClick: () => { void setBought(item.id, false); } },
    });
  }
}

async function remove(item: GroceryRestockOut) {
  await removeItem(item.id);
}

function openEdit(item: GroceryRestockOut) {
  Object.assign(form, { name: item.name, quantity: item.quantity ?? "", unit: item.unit ?? "count", store: item.store ?? null, note: item.note ?? "" });
  editing.value = item;
}

async function saveEdit() {
  if (!editing.value) return;
  const quantity = Number(form.quantity);
  const hasAmount = form.quantity !== "" && Number.isFinite(quantity) && quantity > 0;
  const ok = await update(editing.value.id, {
    name: form.name.trim(),
    quantity: hasAmount ? quantity : null,
    unit: hasAmount ? form.unit : null,
    store: form.store,
    note: form.note.trim(),
  });
  if (ok) editing.value = null;
}

onMounted(load);
</script>

<style scoped>
.restock {
  padding: 18px 20px 16px;
}

.restock--compact {
  padding: 0;
  margin-bottom: 26px;
}

.restock__title {
  margin: 6px 0 12px;
  font-family: var(--paper-serif);
  font-size: 1.5625rem;
  font-weight: 420;
  line-height: 1.1;
  letter-spacing: -0.01em;
}

.restock__add {
  display: flex;
  align-items: center;
  gap: 8px;
}

.restock__input {
  flex: 1;
  min-width: 0;
}

.restock__where-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 16px;
  margin-top: 8px;
}

.restock__where {
  flex: 1 1 220px;
  margin: 0;
  font-size: 0.78125rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
}

.restock__common {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 0;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-tomato));
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.restock__common:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.restock__common:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.restock__items {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.restock-item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: start;
  gap: 4px;
  padding: 7px 0;
  border-top: 1px solid rgb(var(--v-theme-rule));
}

/* Vuetify gives the checkbox a named grid area, so every cell is placed explicitly */
.restock-item__check {
  grid-area: auto;
  grid-column: 1;
  grid-row: 1;
  margin-top: -7px;
}

.restock-item__body {
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
}

.restock-item__name {
  font-size: 1rem;
  font-weight: 500;
  line-height: 1.3;
}

.restock-item__name::first-letter {
  text-transform: uppercase;
}

.restock-item__meta,
.restock-item__status {
  font-size: 0.78125rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.restock-item__status {
  font-style: italic;
}

.restock-item__more {
  grid-column: 3;
  grid-row: 1;
  margin-top: -6px;
  color: rgb(var(--v-theme-ink-muted));
}

.restock__empty {
  margin: 12px 0 0;
  font-family: var(--paper-serif);
  font-size: 1rem;
  font-style: italic;
  color: rgb(var(--v-theme-ink-muted));
}

.restock__bought {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.restock__bought-label {
  margin-right: 2px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.restock__again {
  appearance: none;
  padding: 2px 10px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 999px;
  background: none;
  color: inherit;
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}

.restock__again:hover:not(:disabled) {
  border-color: rgb(var(--v-theme-on-background));
}

.restock__again:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}
</style>
