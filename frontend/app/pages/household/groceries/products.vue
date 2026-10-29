<template>
  <div class="grocery-catalog paper-container">
    <header class="catalog-head">
      <div>
        <NuxtLink to="/household/groceries" class="paper-kicker catalog-head__back">← {{ $t('groceries.title') }}</NuxtLink>
        <h1 class="catalog-head__title paper-headline">
          {{ $t('groceries.catalog') }}
        </h1>
        <p class="catalog-head__dek paper-dek">
          {{ $t('groceries.catalog-subtitle') }}
        </p>
      </div>
      <v-btn color="primary" :prepend-icon="$globals.icons.createAlt" @click="openProduct()">
        {{ $t('groceries.add-product') }}
      </v-btn>
    </header>
    <v-alert v-if="error" type="error" closable class="mb-4" @click:close="error = ''">
      {{ error }}
    </v-alert>
    <v-tabs v-model="tab" color="primary" :grow="xs" class="catalog-tabs mb-6">
      <v-tab value="products">
        {{ $t('groceries.catalog') }}
      </v-tab>
      <v-tab value="rules">
        {{ $t('groceries.rules-tab') }}
      </v-tab>
    </v-tabs>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />
    <template v-if="tab === 'products'">
      <v-text-field
        v-model="search"
        :label="$t('groceries.search')"
        :prepend-inner-icon="$globals.icons.search"
        clearable
        rounded="pill"
        density="compact"
        class="mb-6 catalog-search"
      />
      <section v-if="!products.length && !loading" class="catalog-empty paper-box">
        <h2 class="catalog-empty__title">
          {{ $t('groceries.no-products') }}
        </h2>
        <p class="paper-muted mt-2 mb-5">
          {{ $t('groceries.no-products-detail') }}
        </p>
        <v-btn color="primary" @click="openProduct()">
          {{ $t('groceries.add-product') }}
        </v-btn>
      </section>
      <v-row>
        <v-col v-for="product in visibleProducts" :key="product.id" cols="12" sm="6" lg="4">
          <article class="product-tile paper-box" :class="{ 'opacity-60': !product.enabled }">
            <div class="product-tile__top">
              <span class="product-tile__store" :style="{ '--store-color': storeColor(product.store) }"><i />{{ storeTitle(product.store) }}</span>
              <span class="product-tile__rank">{{ $t((product.priority ?? 0) === 0 ? 'groceries.first-choice' : 'groceries.backup-choice') }}</span>
            </div>
            <span class="paper-kicker">{{ product.food.name }}</span>
            <h2 class="product-tile__name">
              {{ product.name }}
            </h2>
            <p v-if="product.packageQuantity" class="product-tile__size">
              {{ $t('groceries.per-package', { amount: `${product.packageQuantity} ${unitTitle(product.packageUnit)}` }) }}
            </p>
            <p v-if="product.notes" class="product-tile__notes">
              {{ product.notes }}
            </p>
            <div class="product-tile__actions">
              <v-btn
                v-if="product.url"
                :href="product.url"
                target="_blank"
                rel="noopener noreferrer"
                variant="text"
                size="small"
                color="tomato"
                :append-icon="$globals.icons.externalLink"
              >
                {{ $t('groceries.open-product') }}
              </v-btn>
              <v-spacer />
              <v-btn variant="text" size="small" @click="openProduct(product)">
                {{ $t('groceries.edit') }}
              </v-btn>
              <v-btn icon variant="text" size="small" :aria-label="$t('groceries.remove')" @click="deleteTarget = { id: product.id, kind: 'product' }">
                <v-icon :icon="$globals.icons.delete" size="18" />
              </v-btn>
            </div>
          </article>
        </v-col>
      </v-row>
    </template>
    <template v-else>
      <div class="d-flex justify-end mb-4">
        <v-btn color="primary" :prepend-icon="$globals.icons.createAlt" @click="openRule()">
          {{ $t('groceries.add-rule') }}
        </v-btn>
      </div>
      <v-row>
        <v-col v-for="kind in ruleKinds" :key="kind.value" cols="12" md="6">
          <h2 class="paper-section-title">
            {{ $t(kind.label) }}
          </h2>
          <p class="paper-muted text-body-2 mt-2 mb-2">
            {{ $t(kind.hint) }}
          </p>
          <div v-for="rule in rules.filter(item => item.kind === kind.value)" :key="rule.id" class="rule-row" :class="{ 'opacity-60': !rule.enabled }">
            <div>
              <div class="rule-row__food">
                {{ rule.food.name }}
              </div>
              <div class="rule-row__amount">
                {{ rule.quantity }} {{ unitTitle(rule.unit) }}
                <span v-if="rule.kind === 'recurring'" class="paper-muted"> · {{ $t(rule.mode === 'extra' ? 'groceries.extra' : 'groceries.minimum') }}</span>
              </div>
            </div>
            <div class="rule-row__actions">
              <v-btn variant="text" size="small" @click="openRule(rule)">
                {{ $t('groceries.edit') }}
              </v-btn>
              <v-btn icon variant="text" size="small" :aria-label="$t('groceries.remove')" @click="deleteTarget = { id: rule.id, kind: 'rule' }">
                <v-icon :icon="$globals.icons.delete" size="18" />
              </v-btn>
            </div>
          </div>
          <p v-if="!rules.some(item => item.kind === kind.value)" class="paper-muted py-4">
            {{ $t('groceries.no-rules') }}
          </p>
        </v-col>
      </v-row>
    </template>
    <GroceryProductDialog v-model="productDialog" :foods="foods" :product="editingProduct" :initial-food-id="initialFoodId" @saved="load" />
    <GroceryRuleDialog v-model="ruleDialog" :foods="foods" :rule="editingRule" @saved="load" />
    <v-dialog :model-value="!!deleteTarget" max-width="440" @update:model-value="deleteTarget = null">
      <v-card :title="$t(deleteTarget?.kind === 'product' ? 'groceries.delete-confirm' : 'groceries.delete-rule-confirm')">
        <v-card-actions>
          <v-spacer /><v-btn @click="deleteTarget = null">
            {{ $t('groceries.cancel') }}
          </v-btn>
          <v-btn color="error" @click="removeSaved">
            {{ $t('groceries.remove') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import GroceryProductDialog from "~/components/Domain/Grocery/GroceryProductDialog.vue";
import GroceryRuleDialog from "~/components/Domain/Grocery/GroceryRuleDialog.vue";
import { useGroceryCatalog } from "~/composables/groceries/use-grocery-catalog";
import { groceryError, groceryStores, storeTitle, unitTitle } from "~/composables/groceries/grocery-utils";
import type { GroceryFoodRuleOut, GroceryProductOut } from "~/lib/api/types/grocery";

definePageMeta({ middleware: ["household-only"] });
const route = useRoute();
// On phones the two tabs share the width, so neither label runs off the edge
const { xs } = useDisplay();
const { api, products, rules, foods, error, loading, load } = useGroceryCatalog();
const tab = ref("products");
const search = ref("");
const productDialog = ref(false);
const ruleDialog = ref(false);
const editingProduct = ref<GroceryProductOut | null>(null);
const editingRule = ref<GroceryFoodRuleOut | null>(null);
const initialFoodId = ref("");
const deleteTarget = ref<{ id: string; kind: "product" | "rule" } | null>(null);
const ruleKinds = [
  { value: "pantry", label: "groceries.pantry", hint: "groceries.pantry-hint" },
  { value: "recurring", label: "groceries.staples", hint: "groceries.staple-hint" },
];
const visibleProducts = computed(() => products.value.filter((product) => {
  const query = (search.value ?? "").toLowerCase();
  return `${product.food.name} ${product.name} ${storeTitle(product.store)}`.toLowerCase().includes(query);
}));
const storeColor = (store: string) => groceryStores.find(item => item.value === store)?.color;
function openProduct(product: GroceryProductOut | null = null) {
  editingProduct.value = product;
  productDialog.value = true;
}
function openRule(rule: GroceryFoodRuleOut | null = null) {
  editingRule.value = rule;
  ruleDialog.value = true;
}
async function removeSaved() {
  if (!deleteTarget.value) return;
  const result = deleteTarget.value.kind === "product" ? await api.groceries.deleteProduct(deleteTarget.value.id) : await api.groceries.deleteRule(deleteTarget.value.id);
  if (result.error) { error.value = groceryError(result.error); return; }
  deleteTarget.value = null;
  await load();
}
onMounted(async () => {
  await load();
  if (typeof route.query.food_id === "string") {
    initialFoodId.value = route.query.food_id;
    openProduct();
  }
});
</script>

<style scoped>
.grocery-catalog {
  padding-top: 32px;
  padding-bottom: 72px;
}

.catalog-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px 24px;
  margin-bottom: 24px;
}

.catalog-head__back {
  text-decoration: none;
}

.catalog-head__title {
  margin: 6px 0 8px;
  font-size: 3rem;
}

.catalog-head__dek {
  margin: 0;
  max-width: 52ch;
  font-size: 1.125rem;
}

.catalog-tabs {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.catalog-search {
  max-width: 520px;
}

.catalog-empty {
  padding: 32px;
  text-align: center;
}

.catalog-empty__title {
  font-family: var(--paper-serif);
  font-size: 1.5rem;
  font-weight: 420;
}

.product-tile {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 18px 8px;
}

.product-tile__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 0.8125rem;
}

.product-tile__store {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-weight: 600;
}

.product-tile__store i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--store-color);
}

.product-tile__rank {
  color: rgb(var(--v-theme-ink-muted));
}

.product-tile__name {
  margin: 2px 0 0;
  font-family: var(--paper-serif);
  font-size: 1.25rem;
  font-weight: 420;
  line-height: 1.25;
}

.product-tile__size {
  margin: 6px 0 0;
  font-family: var(--paper-serif);
  font-size: 0.9375rem;
}

.product-tile__notes {
  margin: 8px 0 0;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
}

.product-tile__actions {
  display: flex;
  align-items: center;
  margin: auto -8px 0;
  padding-top: 10px;
}

.rule-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.rule-row__food {
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
}

.rule-row__food::first-letter {
  text-transform: uppercase;
}

.rule-row__amount {
  font-size: 0.875rem;
}

.rule-row__actions {
  display: flex;
  align-items: center;
}

@media (max-width: 959px) {
  .grocery-catalog {
    padding-top: 22px;
  }

  .catalog-head__title {
    font-size: 2.25rem;
  }
}
</style>
