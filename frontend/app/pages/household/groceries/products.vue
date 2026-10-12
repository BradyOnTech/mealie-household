<template>
  <v-container class="grocery-catalog" max-width="1200">
    <div class="d-flex flex-wrap align-center justify-space-between ga-4 mb-6">
      <div>
        <NuxtLink to="/household/groceries" class="text-body-2">← {{ $t('groceries.title') }}</NuxtLink>
        <h1 class="text-h4 mt-2">
          {{ $t('groceries.catalog') }}
        </h1>
        <p class="text-body-1 text-medium-emphasis mt-2">
          {{ $t('groceries.catalog-subtitle') }}
        </p>
      </div>
      <v-btn color="primary" variant="flat" @click="openProduct()">
        {{ $t('groceries.add-product') }}
      </v-btn>
    </div>
    <v-alert v-if="error" type="error" closable class="mb-4" @click:close="error = ''">
      {{ error }}
    </v-alert>
    <v-tabs v-model="tab" color="primary" class="mb-5">
      <v-tab value="products">
        {{ $t('groceries.catalog') }}
      </v-tab>
      <v-tab value="rules">
        {{ $t('groceries.pantry') }} &amp; {{ $t('groceries.staples') }}
      </v-tab>
    </v-tabs>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />
    <template v-if="tab === 'products'">
      <v-text-field
        v-model="search"
        :label="$t('groceries.search')"
        clearable
        variant="outlined"
        density="compact"
        class="mb-5"
      />
      <v-card v-if="!products.length && !loading" variant="tonal" class="pa-8 text-center">
        <h2 class="text-h6">
          {{ $t('groceries.no-products') }}
        </h2><p class="mt-3 mb-5">
          {{ $t('groceries.no-products-detail') }}
        </p>
        <v-btn color="primary" @click="openProduct()">
          {{ $t('groceries.add-product') }}
        </v-btn>
      </v-card>
      <v-row>
        <v-col v-for="product in visibleProducts" :key="product.id" cols="12" sm="6" lg="4">
          <v-card variant="outlined" height="100%" class="product-card" :class="{ 'opacity-60': !product.enabled }">
            <v-card-text>
              <div class="d-flex justify-space-between align-center ga-2 mb-3">
                <v-chip size="small" :color="storeColor(product.store)">
                  {{ storeTitle(product.store) }}
                </v-chip>
                <span class="text-caption text-medium-emphasis">{{ $t((product.priority ?? 0) === 0 ? 'groceries.first-choice' : 'groceries.backup-choice') }}</span>
              </div>
              <div class="text-overline text-medium-emphasis">
                {{ product.food.name }}
              </div>
              <h2 class="text-h6">
                {{ product.name }}
              </h2>
              <p v-if="product.packageQuantity" class="mt-2">
                {{ product.packageQuantity }} {{ unitTitle(product.packageUnit) }} / {{ $t('groceries.packages') }}
              </p>
              <p v-if="product.notes" class="text-body-2 text-medium-emphasis mt-3">
                {{ product.notes }}
              </p>
            </v-card-text>
            <v-card-actions>
              <v-btn v-if="product.url" :href="product.url" target="_blank" rel="noopener noreferrer" color="primary">
                {{ $t('groceries.open-product') }}
              </v-btn>
              <v-spacer /><v-btn @click="openProduct(product)">
                {{ $t('groceries.edit') }}
              </v-btn>
              <v-btn :aria-label="$t('groceries.remove')" @click="deleteTarget = { id: product.id, kind: 'product' }">
                ×
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
    </template>
    <template v-else>
      <div class="d-flex justify-end mb-4">
        <v-btn color="primary" variant="flat" @click="openRule()">
          {{ $t('groceries.add-rule') }}
        </v-btn>
      </div>
      <v-row>
        <v-col v-for="kind in ruleKinds" :key="kind.value" cols="12" md="6">
          <h2 class="text-h6 mb-3">
            {{ $t(kind.label) }}
          </h2>
          <p class="text-body-2 text-medium-emphasis mb-4">
            {{ $t(kind.hint) }}
          </p>
          <v-card v-for="rule in rules.filter(item => item.kind === kind.value)" :key="rule.id" variant="outlined" class="mb-3 pa-4" :class="{ 'opacity-60': !rule.enabled }">
            <div class="d-flex align-center justify-space-between ga-3">
              <div>
                <strong>{{ rule.food.name }}</strong><p>{{ rule.quantity }} {{ unitTitle(rule.unit) }}</p>
                <p v-if="rule.kind === 'recurring'" class="text-caption text-medium-emphasis">
                  {{ $t(rule.mode === 'extra' ? 'groceries.extra' : 'groceries.minimum') }}
                </p>
              </div>
              <div>
                <v-btn size="small" @click="openRule(rule)">
                  {{ $t('groceries.edit') }}
                </v-btn>
                <v-btn size="small" :aria-label="$t('groceries.remove')" @click="deleteTarget = { id: rule.id, kind: 'rule' }">
                  ×
                </v-btn>
              </div>
            </div>
          </v-card>
          <p v-if="!rules.some(item => item.kind === kind.value)" class="text-medium-emphasis pa-4">
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
  </v-container>
</template>

<script setup lang="ts">
import GroceryProductDialog from "~/components/Domain/Grocery/GroceryProductDialog.vue";
import GroceryRuleDialog from "~/components/Domain/Grocery/GroceryRuleDialog.vue";
import { useGroceryCatalog } from "~/composables/groceries/use-grocery-catalog";
import { groceryError, groceryStores, storeTitle, unitTitle } from "~/composables/groceries/grocery-utils";
import type { GroceryFoodRuleOut, GroceryProductOut } from "~/lib/api/types/grocery";

definePageMeta({ middleware: ["household-only"] });
const route = useRoute();
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
  padding-top: 28px;
  padding-bottom: 60px;
}
.product-card {
  border-radius: 14px;
}
</style>
