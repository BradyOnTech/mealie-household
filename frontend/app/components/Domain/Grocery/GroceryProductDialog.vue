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

        <div class="product-dialog__scan">
          <span v-if="!product" class="product-dialog__or">{{ $t('grocery-scan.or') }}</span>
          <v-btn
            variant="tonal"
            block
            :prepend-icon="$globals.icons.barcodeScan"
            :loading="identifying"
            @click="openScanner()"
          >
            {{ product ? $t('grocery-scan.scan-its-barcode') : canReadPhotos ? $t('grocery-scan.scan-package-photos') : $t('grocery-scan.scan-package') }}
          </v-btn>
        </div>
        <div
          v-if="scanNotice"
          class="product-dialog__notice"
          :class="`product-dialog__notice--${scanNotice.tone}`"
          role="status"
        >
          <p class="product-dialog__notice-text">
            {{ scanNotice.text }}
          </p>
          <div v-if="scanNotice.actions.length" class="product-dialog__notice-actions">
            <v-btn
              v-for="(action, index) in scanNotice.actions"
              :key="action.label"
              size="small"
              :variant="index === 0 ? 'flat' : 'text'"
              :color="index === 0 ? 'primary' : undefined"
              :href="action.href"
              :target="action.href ? '_blank' : undefined"
              :rel="action.href ? 'noopener noreferrer' : undefined"
              :append-icon="action.href ? $globals.icons.externalLink : undefined"
              :loading="action.loading"
              @click="action.run?.()"
            >
              {{ action.label }}
            </v-btn>
          </div>
        </div>

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
            <div class="product-dialog__barcode">
              <span class="product-dialog__barcode-label">{{ $t('grocery-scan.barcode') }}</span>
              <span v-if="form.barcode" class="product-dialog__barcode-value">{{ form.barcode }}</span>
              <span v-else class="product-dialog__barcode-none">{{ $t('grocery-scan.no-barcode') }}</span>
              <v-btn v-if="form.barcode" variant="text" size="small" @click="form.barcode = null">
                {{ $t('grocery-scan.remove-barcode') }}
              </v-btn>
            </div>
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
    <GroceryScanner
      v-model="scannerOpen"
      :photos="canReadPhotos && !product"
      :title="product ? $t('grocery-scan.scan-its-barcode') : $t('grocery-scan.scan-a-product')"
      :prompt="scannerPrompt"
      :photo-only="!!scannerPrompt"
      @result="onScanned"
    />
  </v-dialog>
</template>

<script setup lang="ts">
import { useDebounceFn } from "@vueuse/core";
import { useDisplay } from "vuetify";
import GroceryScanner, { type ScannerResult } from "~/components/Domain/Grocery/GroceryScanner.vue";
import type { GroceryProductCreate, GroceryProductLookup, GroceryProductOut } from "~/lib/api/types/grocery";
import type { IngredientFood } from "~/lib/api/types/recipe";
import { useUserApi } from "~/composables/api";
import { detectGroceryStore, groceryError, groceryStores, groceryUnits, storeSearchUrl, storeTitle } from "~/composables/groceries/grocery-utils";
import { foodIdFor, scanOutcome, useGroceryScan } from "~/composables/groceries/use-grocery-scan";
import { alert } from "~/composables/use-toast";

const props = defineProps<{
  foods: IngredientFood[];
  product?: GroceryProductOut | null;
  initialFoodId?: string;
  /** Opens straight onto the scanner */
  scanOnOpen?: boolean;
}>();
const opened = defineModel<boolean>({ default: false });
const emit = defineEmits<{
  saved: [];
  /** A scan found a product the household already has, to edit instead */
  edit: [GroceryProductOut];
}>();
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
const emptyForm = (): GroceryProductCreate => ({ foodId: "", name: "", store: "walmart", url: null, priority: 0, enabled: true, packageQuantity: null, packageUnit: null, notes: "", barcode: null });
const form = reactive<GroceryProductCreate>(emptyForm());
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
  if (data) {
    fillFrom(data);
  }
}

/** Fills in what a link or a scan read, leaving alone whatever someone has set by hand */
function fillFrom(data: GroceryProductLookup) {
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
  if (data.barcode) {
    form.barcode = data.barcode;
  }
}

// =========================================================
// Scanning the package

const { identifying, scan, canReadPhotos, identify, reset: resetScan } = useGroceryScan();
const scannerOpen = ref(false);
const scannerPrompt = ref("");
/** Whether the last scan came with a photo, so there's no point asking for one */
const scanHadPhoto = ref(false);
/** The household's product the scan looked like, turned down as being a different one */
const notTheLikelyOne = ref(false);
const remembering = ref(false);
const scanMessage = ref("");

function openScanner(prompt = "") {
  scannerPrompt.value = prompt;
  scannerOpen.value = true;
}

async function onScanned(result: ScannerResult) {
  scanMessage.value = "";
  notTheLikelyOne.value = false;
  scanHadPhoto.value = !!result.photo;
  const found = await identify(result);
  if (!found) {
    scanMessage.value = i18n.t("grocery-scan.lookup-failed");
    return;
  }

  if (props.product) {
    // an existing product only takes the barcode, unless it's already another product's
    if (found.saved && found.saved.id !== props.product.id) {
      scanMessage.value = i18n.t("grocery-scan.barcode-taken", { name: found.saved.name });
    }
    else if (found.barcode) {
      form.barcode = found.barcode;
      scanMessage.value = i18n.t("grocery-scan.barcode-added");
    }
    return;
  }

  const outcome = scanOutcome(found);
  if (outcome === "new" || outcome === "unknown") {
    fillFrom(found.draft);
  }
}

function differentProduct() {
  notTheLikelyOne.value = true;
  if (scan.value) fillFrom(scan.value.draft);
}

function productFields(product: GroceryProductOut): GroceryProductCreate {
  const { foodId, name, store, url, priority, enabled, packageQuantity, packageUnit, notes, barcode } = product;
  return { foodId, name, store, url, priority, enabled, packageQuantity, packageUnit, notes, barcode };
}

/** Saves the scanned barcode to the product it looked like, so scanning it next time finds it */
async function rememberBarcode() {
  const likely = scan.value?.likelySaved;
  if (!likely || !scan.value?.barcode) return;
  remembering.value = true;
  try {
    const result = await api.groceries.updateProduct(likely.id, { ...productFields(likely), barcode: scan.value.barcode });
    if (!result.data) throw result.error;
    alert.success(i18n.t("grocery-scan.barcode-remembered", { name: likely.name }));
    emit("saved");
    opened.value = false;
  }
  catch (cause) { error.value = groceryError(cause); }
  finally { remembering.value = false; }
}

interface ScanNotice {
  tone: "info" | "filled" | "warning";
  text: string;
  actions: { label: string; run?: () => void; href?: string; loading?: boolean }[];
}

/** What the last scan found, and what can be done about it */
const scanNotice = computed<ScanNotice | null>(() => {
  if (identifying.value) {
    return { tone: "info", text: scanHadPhoto.value ? i18n.t("grocery-scan.reading-photo") : i18n.t("grocery-scan.looking-up"), actions: [] };
  }
  if (scanMessage.value) {
    return { tone: "info", text: scanMessage.value, actions: [] };
  }
  const found = scan.value;
  if (!found || props.product) return null;

  switch (scanOutcome(found)) {
    case "saved":
      return {
        tone: "info",
        text: i18n.t("grocery-scan.already-saved", { name: found.saved!.name, store: storeTitle(found.saved!.store) }),
        actions: [{ label: i18n.t("grocery-scan.edit-it"), run: () => emit("edit", found.saved!) }],
      };
    case "likely":
      if (!notTheLikelyOne.value) {
        return {
          tone: "info",
          text: i18n.t("grocery-scan.looks-like-yours", { name: found.likelySaved!.name, store: storeTitle(found.likelySaved!.store) }),
          actions: [
            { label: i18n.t("grocery-scan.remember-barcode"), run: rememberBarcode, loading: remembering.value },
            { label: i18n.t("grocery-scan.different-product"), run: differentProduct },
          ],
        };
      }
      return filledNotice();
    case "new":
      return filledNotice();
    case "unknown":
      return canReadPhotos.value && !scanHadPhoto.value
        ? {
            tone: "warning",
            text: i18n.t("grocery-scan.unknown-snap"),
            actions: [{ label: i18n.t("grocery-scan.snap-front"), run: () => openScanner(i18n.t("grocery-scan.snap-front-prompt")) }],
          }
        : { tone: "warning", text: i18n.t("grocery-scan.unknown-fill-in"), actions: [] };
  }
  return null;
});

function filledNotice(): ScanNotice {
  const actions: ScanNotice["actions"] = [];
  if (!form.url && form.name.trim()) {
    actions.push({ label: i18n.t("grocery-scan.find-at-store", { store: storeTitle(form.store) }), href: storeSearchUrl(form.store, form.name) });
  }
  return {
    tone: "filled",
    text: scanHadPhoto.value ? i18n.t("grocery-scan.filled-from-photo") : i18n.t("grocery-scan.filled-from-barcode"),
    actions,
  };
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
  resetScan();
  scanMessage.value = "";
  scanHadPhoto.value = false;
  notTheLikelyOne.value = false;
  const product = props.product;
  Object.assign(form, product ? productFields(product) : emptyForm());
  selectedFood.value = product?.food ?? props.foods.find(food => food.id === props.initialFoodId) ?? null;
  packageAmount.value = product?.packageQuantity ?? null;
  showMore.value = !!product && (!!product.notes || !product.enabled);
  if (props.scanOnOpen && !product) {
    nextTick(() => openScanner());
  }
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
    const foodId = await foodIdFor(api, props.foods, selectedFood.value);
    // a new ingredient exists now, so trying again doesn't add it twice
    if (typeof selectedFood.value === "string") selectedFood.value = { id: foodId, name: selectedFood.value.trim() };
    const quantity = packageAmount.value === "" || packageAmount.value == null ? null : Number(packageAmount.value);
    const payload: GroceryProductCreate = { foodId, name: form.name.trim(), store: form.store, url: form.url || null, priority: form.priority, enabled: form.enabled, packageQuantity: quantity, packageUnit: quantity == null ? null : form.packageUnit, notes: form.notes, barcode: form.barcode || null };
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

.product-dialog__scan {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  margin: -4px 0 14px;
}

.product-dialog__or {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.product-dialog__or::before,
.product-dialog__or::after {
  content: "";
  flex: 1;
  height: 1px;
  background: rgb(var(--v-theme-rule));
}

.product-dialog__notice {
  margin: 0 0 16px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgb(var(--v-theme-surface-light));
}

.product-dialog__notice--filled {
  background: rgba(var(--v-theme-sage), 0.12);
}

.product-dialog__notice--warning {
  background: rgba(var(--v-theme-warning), 0.12);
}

.product-dialog__notice-text {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.45;
}

.product-dialog__notice-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.product-dialog__barcode {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 0.875rem;
}

.product-dialog__barcode-label {
  font-weight: 600;
}

.product-dialog__barcode-value {
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
}

.product-dialog__barcode-none {
  color: rgb(var(--v-theme-ink-muted));
}

.product-dialog__actions {
  padding: 12px 20px 16px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
</style>
