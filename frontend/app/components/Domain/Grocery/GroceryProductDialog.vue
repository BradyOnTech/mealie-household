<template>
  <v-dialog
    v-model="opened"
    max-width="600"
    scrollable
    :fullscreen="xs"
    :persistent="saving"
  >
    <v-card class="product-dialog">
      <v-card-title class="product-dialog__title">
        {{ $t(product ? 'groceries.edit-product' : 'groceries.add-product') }}
      </v-card-title>
      <v-card-text class="product-dialog__body">
        <v-alert v-if="error" type="error" variant="tonal" class="mb-4">
          {{ error }}
        </v-alert>

        <v-text-field
          v-model="form.url"
          :label="$t('groceries.product-url')"
          :placeholder="$t('groceries.url-placeholder')"
          :prepend-inner-icon="$globals.icons.link"
          :loading="lookingUp"
          :hint="linkHint"
          persistent-hint
          :autofocus="!product && !xs"
          type="url"
          inputmode="url"
          autocomplete="off"
          variant="outlined"
          class="mb-5"
          :class="{ 'product-dialog__link--filled': linkFilled }"
          @update:model-value="onUrlInput"
        />

        <v-text-field
          v-model="form.name"
          :label="$t('groceries.product-name')"
          variant="outlined"
          class="mb-2"
          @update:model-value="touched.name = true"
        />
        <v-combobox
          v-model="selectedFood"
          :items="foods"
          item-title="name"
          return-object
          clearable
          :label="$t('groceries.ingredient')"
          :hint="ingredientHint"
          persistent-hint
          variant="outlined"
          class="mb-5"
          @update:model-value="touched.food = true"
        />
        <v-alert v-if="requiresPermission" type="info" variant="tonal" class="mb-4">
          {{ $t('groceries.ingredient-permission') }}
        </v-alert>

        <div class="product-dialog__row">
          <v-select
            v-model="form.store"
            :items="groceryStores"
            :label="$t('groceries.store')"
            variant="outlined"
            hide-details
            @update:model-value="touched.store = true"
          />
          <v-select
            v-model="form.priority"
            :items="preferences"
            :label="$t('groceries.preference')"
            variant="outlined"
            hide-details
          />
        </div>

        <div class="product-dialog__row mt-5">
          <v-text-field
            v-model="packageAmount"
            type="number"
            min="0.001"
            step="any"
            :label="$t('groceries.package-size')"
            variant="outlined"
            hide-details
            @update:model-value="touched.package = true"
          />
          <v-select
            v-model="form.packageUnit"
            :items="groceryUnits"
            clearable
            :label="$t('groceries.package-unit')"
            variant="outlined"
            hide-details
            @update:model-value="touched.package = true"
          />
        </div>
        <p class="product-dialog__hint">
          {{ $t('groceries.package-hint') }}
        </p>

        <button
          type="button"
          class="product-dialog__more"
          :aria-expanded="showMore"
          @click="showMore = !showMore"
        >
          {{ $t('groceries.more-options') }}
          <v-icon size="18" :icon="$globals.icons.chevronDown" :class="{ 'product-dialog__more-icon--open': showMore }" />
        </button>
        <v-expand-transition>
          <div v-show="showMore">
            <v-textarea
              v-model="form.notes"
              :label="$t('groceries.notes')"
              rows="2"
              auto-grow
              variant="outlined"
              class="mt-3"
            />
            <v-switch
              v-model="form.enabled"
              color="primary"
              :label="$t('groceries.enabled')"
              hide-details
            />
          </div>
        </v-expand-transition>
      </v-card-text>
      <v-card-actions class="product-dialog__actions">
        <v-spacer />
        <v-btn :disabled="saving" @click="opened = false">
          {{ $t('groceries.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          :disabled="!selectedFood || !form.name.trim() || requiresPermission"
          @click="save"
        >
          {{ $t('groceries.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDebounceFn } from "@vueuse/core";
import { useDisplay } from "vuetify";
import type { GroceryProductCreate, GroceryProductLookup, GroceryProductOut } from "~/lib/api/types/grocery";
import type { IngredientFood } from "~/lib/api/types/recipe";
import { useUserApi } from "~/composables/api";
import { detectGroceryStore, groceryError, groceryStores, groceryUnits } from "~/composables/groceries/grocery-utils";

const props = defineProps<{ foods: IngredientFood[]; product?: GroceryProductOut | null; initialFoodId?: string }>();
const opened = defineModel<boolean>({ default: false });
const emit = defineEmits<{ saved: [] }>();
const api = useUserApi();
const auth = useMealieAuth();
const i18n = useI18n();
const { xs } = useDisplay();
const saving = ref(false);
const error = ref("");
const showMore = ref(false);
const selectedFood = ref<{ id: string; name: string } | string | null>(null);
const isNewFood = computed(() => typeof selectedFood.value === "string"
  && !!selectedFood.value.trim()
  && !props.foods.some(food => food.name.toLowerCase() === (selectedFood.value as string).trim().toLowerCase()));
const requiresPermission = computed(() => isNewFood.value && !auth.user.value?.canOrganize);
const packageAmount = ref<string | number | null>(null);
const form = reactive<GroceryProductCreate>({ foodId: "", name: "", store: "walmart", url: null, priority: 0, enabled: true, packageQuantity: null, packageUnit: null, notes: "" });
const preferences = computed(() => [
  { title: i18n.t("groceries.first-choice"), value: 0 },
  { title: i18n.t("groceries.backup-choice"), value: 10 },
  { title: i18n.t("groceries.other-choice"), value: 20 },
]);

// =========================================================
// Filling in from the product's link

/** Fields someone has set by hand, which a link's details don't overwrite */
const touched = reactive({ name: false, food: false, store: false, package: false });
const lookingUp = ref(false);
const lookup = ref<GroceryProductLookup | null>(null);
let lastUrl = "";
/** Counts lookups, so only the latest one's answer is used */
let lookups = 0;

const linkFilled = computed(() => !!lookup.value && !lookingUp.value);

const linkHint = computed(() => {
  if (lookingUp.value) {
    return i18n.t("groceries.url-reading");
  }
  if (lookup.value) {
    return lookup.value.name ? i18n.t("groceries.url-filled") : i18n.t("groceries.url-no-name");
  }
  return i18n.t("groceries.url-hint");
});

const ingredientHint = computed(() => {
  const value = selectedFood.value;
  const name = typeof value === "string" ? value.trim() : value?.name;
  if (isNewFood.value && !requiresPermission.value) {
    return i18n.t("groceries.ingredient-new", { food: name });
  }
  return name ? i18n.t("groceries.ingredient-hint-food", { food: name }) : i18n.t("groceries.ingredient-hint");
});

function isProductLink(value: string) {
  return /^https:\/\/[^\s/]+\.[^\s/]+\/\S+/.test(value);
}

const lookupSoon = useDebounceFn((url: string) => readLink(url), 350);

function onUrlInput(value: string | null) {
  // an existing product's details are the household's own, so changing its link doesn't replace them
  const url = (value ?? "").trim();
  if (props.product || url === lastUrl) {
    return;
  }
  if (!isProductLink(url)) {
    // whatever was being read isn't the link any more
    lookups++;
    lastUrl = "";
    lookingUp.value = false;
    lookup.value = null;
    return;
  }
  if (!touched.store) {
    form.store = detectGroceryStore(url) ?? form.store;
  }
  lookupSoon(url);
}

async function readLink(url: string) {
  // the link may have changed again while waiting to be read
  if ((form.url ?? "").trim() !== url) {
    return;
  }
  const current = ++lookups;
  lastUrl = url;
  lookingUp.value = true;
  const { data } = await api.groceries.lookupProduct(url);
  if (current !== lookups) {
    return;
  }
  lookingUp.value = false;
  lookup.value = data;
  if (!data) {
    return;
  }

  if (data.name && !touched.name) {
    form.name = data.name;
  }
  if (data.store && !touched.store) {
    form.store = data.store;
  }
  if (data.packageQuantity && data.packageUnit && !touched.package) {
    packageAmount.value = data.packageQuantity;
    form.packageUnit = data.packageUnit;
  }
  if (!touched.food) {
    const food = data.food ? props.foods.find(each => each.id === data.food!.id) ?? data.food : null;
    selectedFood.value = food ?? data.newFoodName ?? selectedFood.value;
  }
}

// =========================================================
// Opening and saving

watch(opened, (value) => {
  if (!value) return;
  error.value = "";
  lookup.value = null;
  lookingUp.value = false;
  lastUrl = "";
  lookups++;
  Object.assign(touched, { name: false, food: false, store: false, package: false });
  const product = props.product;
  Object.assign(form, product ? { ...product } : { foodId: "", name: "", store: "walmart", url: null, priority: 0, enabled: true, packageQuantity: null, packageUnit: null, notes: "" });
  selectedFood.value = product?.food ?? props.foods.find(food => food.id === props.initialFoodId) ?? null;
  packageAmount.value = product?.packageQuantity ?? null;
  showMore.value = !!product && (!!product.notes || !product.enabled);
});

watch(selectedFood, (value) => {
  // picking an ingredient first names the product after it, until the link or a person names it
  if (value && !form.name) form.name = typeof value === "string" ? value : value.name;
});

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

<style scoped>
.product-dialog__title {
  padding: 20px 24px 8px;
  font-size: 1.5rem;
}

.product-dialog__body {
  padding: 12px 24px 8px !important;
}

.product-dialog__link--filled :deep(.v-messages__message) {
  color: rgb(var(--v-theme-sage));
  opacity: 1;
}

.product-dialog__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.product-dialog__hint {
  margin: 6px 4px 0;
  font-size: 0.8125rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.product-dialog__more {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-top: 14px;
  padding: 4px 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-ink-muted));
  cursor: pointer;
}

.product-dialog__more-icon--open {
  transform: rotate(180deg);
}

.product-dialog__actions {
  padding: 12px 20px 16px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
</style>
