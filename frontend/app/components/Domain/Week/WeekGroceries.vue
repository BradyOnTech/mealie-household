<template>
  <section class="week-groceries paper-box">
    <span class="paper-kicker">{{ $t("groceries.title") }}</span>
    <template v-if="view?.week">
      <h3 class="week-groceries__title">
        {{ $t("this-week.groceries-left", pending.length) }}
      </h3>
      <p class="week-groceries__sub">
        {{ pending.length ? $t("this-week.groceries-across", { stores: storeSentence }) : $t("this-week.groceries-done") }}
      </p>
      <div
        v-for="row in storeRows"
        :key="row.key"
        class="week-groceries__store"
        :style="{ '--store-color': row.color }"
      >
        <i />
        <span>{{ row.title }}</span>
        <u><s :style="{ width: `${row.progress}%` }" /></u>
        <small>{{ $t("this-week.store-left", { count: row.left }) }}</small>
      </div>
      <NuxtLink to="/household/groceries" class="paper-link week-groceries__open">
        {{ $t("this-week.open-list") }} →
      </NuxtLink>
    </template>
    <template v-else>
      <h3 class="week-groceries__title">
        {{ $t("this-week.no-list") }}
      </h3>
      <p class="week-groceries__sub">
        {{ $t("this-week.no-list-detail") }}
      </p>
      <v-btn variant="outlined" to="/household/groceries" class="mt-1">
        {{ $t("this-week.make-list") }}
      </v-btn>
    </template>
  </section>
</template>

<script setup lang="ts">
import { groceryStores } from "~/composables/groceries/grocery-utils";
import type { GroceryWeekView } from "~/lib/api/types/grocery";

const props = defineProps<{
  view: GroceryWeekView | null;
}>();

const i18n = useI18n();

const purchases = computed(() => props.view?.purchases ?? []);
const pending = computed(() => purchases.value.filter(purchase => !purchase.items.every(item => item.checked)));

const storeRows = computed(() => {
  const chosen = props.view?.week?.stores ?? [];
  const rows = groceryStores
    .filter(store => chosen.includes(store.value) || purchases.value.some(purchase => purchase.store === store.value))
    .map(store => ({ key: store.value as string, title: store.title, color: store.color, store: store.value as string | null }));
  if (purchases.value.some(purchase => !purchase.store)) {
    rows.push({ key: "unassigned", title: i18n.t("groceries.unassigned"), color: "rgb(var(--v-theme-ink-muted))", store: null });
  }
  return rows.map((row) => {
    const inStore = purchases.value.filter(purchase => (purchase.store ?? null) === row.store);
    const left = inStore.filter(purchase => !purchase.items.every(item => item.checked)).length;
    return { ...row, left, progress: inStore.length ? ((inStore.length - left) / inStore.length) * 100 : 0 };
  });
});

const storeSentence = computed(() => {
  const names = storeRows.value.filter(row => row.store && row.left).map(row => row.title);
  return new Intl.ListFormat(i18n.locale.value, { style: "long", type: "conjunction" }).format(names.length ? names : storeRows.value.map(row => row.title));
});
</script>

<style scoped>
.week-groceries {
  margin-top: 22px;
  padding: 18px 20px 16px;
}

.week-groceries__title {
  margin: 6px 0 4px;
  font-family: var(--paper-serif);
  font-size: 1.5625rem;
  font-weight: 420;
  line-height: 1.1;
  letter-spacing: -0.01em;
}

.week-groceries__sub {
  margin: 0 0 12px;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
}

.week-groceries__store {
  display: grid;
  grid-template-columns: 10px 1fr 64px 48px;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
  font-size: 0.8125rem;
}

.week-groceries__store i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--store-color);
}

.week-groceries__store u {
  height: 3px;
  overflow: hidden;
  border-radius: 2px;
  background: rgb(var(--v-theme-rule));
  text-decoration: none;
}

.week-groceries__store s {
  display: block;
  height: 100%;
  background: rgb(var(--v-theme-ink-muted));
}

.week-groceries__store small {
  text-align: right;
  font-size: 0.78125rem;
  color: rgb(var(--v-theme-ink-muted));
}

.week-groceries__open {
  display: inline-block;
  margin-top: 12px;
  font-size: 0.875rem;
}
</style>
