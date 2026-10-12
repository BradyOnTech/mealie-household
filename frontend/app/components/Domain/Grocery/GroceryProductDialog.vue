<template>
  <v-dialog v-model="opened" max-width="640" :persistent="saving">
    <v-card>
      <v-card-title>{{ $t(product ? 'groceries.edit-product' : 'groceries.add-product') }}</v-card-title>
      <v-card-text>
        <v-alert v-if="error" type="error" class="mb-4">
          {{ error }}
        </v-alert>
        <v-alert v-if="requiresPermission" type="info" variant="tonal" class="mb-4">
          {{ $t('groceries.ingredient-permission') }}
        </v-alert>
        <v-combobox
          v-model="selectedFood"
          :items="foods"
          item-title="name"
          return-object
          clearable
          :label="$t('groceries.ingredient')"
          :hint="$t('groceries.ingredient-hint')"
          persistent-hint
          class="mb-4"
        />
        <v-text-field
          v-model="form.url"
          :label="$t('groceries.product-url')"
          :hint="$t('groceries.url-hint')"
          persistent-hint
          type="url"
          class="mb-4"
          @blur="suggestStore"
        />
        <v-text-field v-model="form.name" :label="$t('groceries.product-name')" />
        <v-row>
          <v-col cols="12" sm="6">
            <v-select v-model="form.store" :items="groceryStores" :label="$t('groceries.store')" />
          </v-col>
          <v-col cols="12" sm="6">
            <v-select v-model="form.priority" :items="preferences" :label="$t('groceries.preference')" />
          </v-col>
        </v-row>
        <v-row>
          <v-col cols="6">
            <v-text-field v-model="packageAmount" type="number" min="0.001" step="any" :label="$t('groceries.package-size')" />
          </v-col>
          <v-col cols="6">
            <v-select v-model="form.packageUnit" :items="groceryUnits" clearable :label="$t('groceries.package-unit')" />
          </v-col>
        </v-row>
        <p class="text-caption mb-4">
          {{ $t('groceries.package-hint') }}
        </p>
        <v-textarea v-model="form.notes" :label="$t('groceries.notes')" rows="2" />
        <v-switch v-model="form.enabled" color="primary" :label="$t('groceries.enabled')" hide-details />
      </v-card-text>
      <v-card-actions>
        <v-spacer /><v-btn :disabled="saving" @click="opened = false">
          {{ $t('groceries.cancel') }}
        </v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!selectedFood || !form.name.trim() || requiresPermission" @click="save">
          {{ $t('groceries.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { GroceryProductCreate, GroceryProductOut } from "~/lib/api/types/grocery";
import type { IngredientFood } from "~/lib/api/types/recipe";
import { useUserApi } from "~/composables/api";
import { detectGroceryStore, groceryError, groceryStores, groceryUnits } from "~/composables/groceries/grocery-utils";

const props = defineProps<{ foods: IngredientFood[]; product?: GroceryProductOut | null; initialFoodId?: string }>();
const opened = defineModel<boolean>({ default: false });
const emit = defineEmits<{ saved: [] }>();
const api = useUserApi();
const auth = useMealieAuth();
const i18n = useI18n();
const saving = ref(false);
const error = ref("");
const selectedFood = ref<{ id: string; name: string } | string | null>(null);
const requiresPermission = computed(() => typeof selectedFood.value === "string"
  && !auth.user.value?.canOrganize
  && !props.foods.some(food => food.name.toLowerCase() === (selectedFood.value as string).trim().toLowerCase()));
const packageAmount = ref<string | number | null>(null);
const form = reactive<GroceryProductCreate>({ foodId: "", name: "", store: "walmart", url: null, priority: 0, enabled: true, packageQuantity: null, packageUnit: null, notes: "" });
const preferences = computed(() => [
  { title: i18n.t("groceries.first-choice"), value: 0 },
  { title: i18n.t("groceries.backup-choice"), value: 10 },
  { title: i18n.t("groceries.other-choice"), value: 20 },
]);

watch(opened, (value) => {
  if (!value) return;
  error.value = "";
  const product = props.product;
  Object.assign(form, product ? { ...product } : { foodId: "", name: "", store: "walmart", url: null, priority: 0, enabled: true, packageQuantity: null, packageUnit: null, notes: "" });
  selectedFood.value = product?.food ?? props.foods.find(food => food.id === props.initialFoodId) ?? null;
  packageAmount.value = product?.packageQuantity ?? null;
});

watch(selectedFood, (value) => {
  if (value && !form.name) form.name = typeof value === "string" ? value : value.name;
});

function suggestStore() {
  if (!props.product && form.url) form.store = detectGroceryStore(form.url) ?? form.store;
}

async function save() {
  if (!selectedFood.value || requiresPermission.value) return;
  saving.value = true;
  error.value = "";
  try {
    let foodId: string;
    if (typeof selectedFood.value === "string") {
      const exactFood = props.foods.find(food => food.name.toLowerCase() === (selectedFood.value as string).trim().toLowerCase());
      if (exactFood) foodId = exactFood.id;
      else {
        const result = await api.groceries.createFood(selectedFood.value.trim());
        if (!result.data) throw result.error;
        foodId = result.data.id;
        selectedFood.value = result.data;
      }
    }
    else foodId = selectedFood.value.id;
    const quantity = packageAmount.value === "" || packageAmount.value == null ? null : Number(packageAmount.value);
    const payload: GroceryProductCreate = { foodId, name: form.name.trim(), store: form.store, url: form.url || null, priority: form.priority, enabled: form.enabled, packageQuantity: quantity, packageUnit: quantity == null ? null : form.packageUnit, notes: form.notes };
    const result = props.product ? await api.groceries.updateProduct(props.product.id, payload) : await api.groceries.createProduct(payload);
    if (!result.data) throw result.error;
    emit("saved");
    opened.value = false;
  }
  catch (cause) { error.value = groceryError(cause); }
  finally { saving.value = false; }
}
</script>
