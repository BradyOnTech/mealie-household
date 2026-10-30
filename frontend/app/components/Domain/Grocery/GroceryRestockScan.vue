<template>
  <div>
    <GroceryScanner
      v-model="scannerOpen"
      :photos="canReadPhotos"
      :title="$t('grocery-scan.scan-what-ran-out')"
      :prompt="scannerPrompt"
      :photo-only="!!scannerPrompt"
      @result="onResult"
    />

    <v-bottom-sheet v-model="sheetOpen" inset max-width="520" :persistent="adding">
      <v-card class="restock-scan">
        <div v-if="identifying" class="restock-scan__looking" role="status">
          <v-progress-circular indeterminate color="primary" size="22" width="2" />
          <span>{{ scanHadPhoto ? $t('grocery-scan.reading-photo') : $t('grocery-scan.looking-up') }}</span>
        </div>

        <template v-else-if="scan && outcome === 'likely'">
          <div class="restock-scan__head">
            <div class="restock-scan__title">
              <span class="paper-kicker">{{ $t('grocery-scan.ran-out-of', { food: scan.likelySaved!.food.name }) }}</span>
              <h2 class="restock-scan__name">
                {{ scan.likelySaved!.name }}
              </h2>
              <p class="restock-scan__meta">
                {{ storeTitle(scan.likelySaved!.store) }}
              </p>
            </div>
            <GroceryProductPhoto :src="sheetPhoto" :large="sheetPhotoLarge" :name="scan.likelySaved!.name" :size="64" zoomable />
          </div>
          <v-checkbox
            v-model="rememberBarcode"
            color="primary"
            density="compact"
            hide-details
            :label="$t('grocery-scan.remember-barcode-for', { name: scan.likelySaved!.name })"
          />
        </template>

        <template v-else-if="scan && outcome === 'new'">
          <div class="restock-scan__head">
            <div class="restock-scan__title">
              <span class="paper-kicker">{{ ingredientName ? $t('grocery-scan.ran-out-of', { food: ingredientName }) : $t('grocery-scan.scanned') }}</span>
              <h2 class="restock-scan__name">
                {{ scan.draft.name }}
              </h2>
            </div>
            <GroceryProductPhoto :src="sheetPhoto" :large="sheetPhotoLarge" :name="scan.draft.name ?? ''" :size="64" zoomable />
          </div>
          <v-checkbox
            v-model="saveProduct"
            color="primary"
            density="compact"
            hide-details
            :disabled="!canSaveProduct"
            :label="$t('grocery-scan.save-as-product')"
          />
          <p class="restock-scan__hint">
            {{ canSaveProduct ? $t('grocery-scan.save-as-product-hint') : $t('grocery-scan.save-needs-permission', { food: ingredientName }) }}
          </p>
          <v-chip-group
            v-if="saveProduct && canSaveProduct"
            v-model="store"
            mandatory
            selected-class="restock-scan__store--selected"
            class="restock-scan__stores"
            :aria-label="$t('groceries.store')"
          >
            <v-chip v-for="option in groceryStores" :key="option.value" :value="option.value" variant="outlined" size="small">
              {{ option.title }}
            </v-chip>
          </v-chip-group>
        </template>

        <template v-else-if="scan && outcome === 'unknown'">
          <div class="restock-scan__head">
            <div class="restock-scan__title">
              <span class="paper-kicker">{{ $t('grocery-scan.scanned') }}</span>
              <h2 class="restock-scan__name">
                {{ $t('grocery-scan.unknown-title') }}
              </h2>
            </div>
            <GroceryProductPhoto :src="sheetPhoto" :large="sheetPhotoLarge" :name="typedName.trim() || $t('grocery-photos.this-product')" :size="64" zoomable />
          </div>
          <p v-if="canReadPhotos && !scanHadPhoto" class="restock-scan__hint">
            {{ $t('grocery-scan.unknown-restock-snap') }}
          </p>
          <template v-else>
            <p class="restock-scan__hint">
              {{ $t('grocery-scan.unknown-restock-name') }}
            </p>
            <v-text-field
              v-model="typedName"
              :label="$t('grocery-scan.what-is-it')"
              density="comfortable"
              variant="outlined"
              hide-details
              autofocus
              maxlength="255"
              class="mt-3"
              @keydown.enter.prevent="addToList"
            />
          </template>
        </template>

        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mt-3">
          {{ error }}
        </v-alert>

        <div v-if="!identifying && scan" class="restock-scan__actions">
          <v-btn variant="text" :disabled="adding" @click="close">
            {{ $t('groceries.cancel') }}
          </v-btn>
          <v-btn
            v-if="outcome === 'unknown' && canReadPhotos && !scanHadPhoto"
            color="primary"
            variant="flat"
            :prepend-icon="$globals.icons.camera"
            @click="snapFront"
          >
            {{ $t('grocery-scan.snap-front') }}
          </v-btn>
          <v-btn
            v-else
            color="primary"
            variant="flat"
            :loading="adding"
            :disabled="outcome === 'unknown' && !typedName.trim()"
            @click="addToList"
          >
            {{ $t('grocery-scan.add-to-list') }}
          </v-btn>
        </div>
      </v-card>
    </v-bottom-sheet>
  </div>
</template>

<script setup lang="ts">
import GroceryProductPhoto from "~/components/Domain/Grocery/GroceryProductPhoto.vue";
import GroceryScanner, { type ScannerResult } from "~/components/Domain/Grocery/GroceryScanner.vue";
import { useStaticRoutes, useUserApi } from "~/composables/api";
import type { GroceryPhotoSize } from "~/composables/api/static-routes";
import { groceryError, groceryStores, storeTitle } from "~/composables/groceries/grocery-utils";
import { useGroceryRestock } from "~/composables/groceries/use-grocery-restock";
import { foodIdFor, scanOutcome, useGroceryScan } from "~/composables/groceries/use-grocery-scan";
import { alert } from "~/composables/use-toast";
import type { GroceryProductOut, GroceryRestockCreate, GroceryStore } from "~/lib/api/types/grocery";

/** Opens the scanner; what it scans goes on the Out of list */
const scannerOpen = defineModel<boolean>({ default: false });

/** A lookup quicker than this shows nothing, so a product the household saved goes on the list without the sheet flashing up */
const SHOW_LOOKUP_AFTER = 400;

const i18n = useI18n();
const api = useUserApi();
const auth = useMealieAuth();
const { identifying, scan, canReadPhotos, identify, reset } = useGroceryScan();
const { items, add, remove } = useGroceryRestock();

const sheetOpen = ref(false);
const scannerPrompt = ref("");
const scanHadPhoto = ref(false);
const adding = ref(false);
const error = ref("");
const rememberBarcode = ref(true);
const saveProduct = ref(true);
const store = ref<GroceryStore>("walmart");
const typedName = ref("");

const outcome = computed(() => (scan.value ? scanOutcome(scan.value) : null));

const { groceryProductPhoto, groceryDraftPhoto } = useStaticRoutes();
/** The photo the sheet shows: the household's own product's, or the one that came with the scan */
function sheetPhotoUrl(size: GroceryPhotoSize) {
  const found = scan.value;
  if (!found) return null;
  if (outcome.value === "likely" && found.likelySaved?.photo) return groceryProductPhoto(found.likelySaved, size);
  return found.draft.photo ? groceryDraftPhoto(found.draft.photo.token, size) : null;
}
const sheetPhoto = computed(() => sheetPhotoUrl("thumb"));
const sheetPhotoLarge = computed(() => sheetPhotoUrl("photo"));
const ingredientName = computed(() => scan.value?.draft.food?.name ?? scan.value?.draft.newFoodName ?? "");
const canSaveProduct = computed(() => {
  const draft = scan.value?.draft;
  if (!draft?.name || !ingredientName.value) return false;
  // a new ingredient needs permission to add
  return !!draft.food || !!auth.user.value?.canOrganize;
});

watch(scannerOpen, (open) => {
  // a scan starts fresh, unless it's the photo asked for to identify the last one
  if (open && !scannerPrompt.value) {
    reset();
    error.value = "";
  }
});

async function onResult(result: ScannerResult) {
  scannerPrompt.value = "";
  scanHadPhoto.value = !!result.photo;
  error.value = "";
  let shown = false;
  const waiting = setTimeout(() => {
    shown = true;
    sheetOpen.value = true;
  }, SHOW_LOOKUP_AFTER);
  const found = await identify(result).finally(() => clearTimeout(waiting));
  // closing the sheet while it was looking drops the scan
  if (shown && !sheetOpen.value) return;
  if (!found) {
    sheetOpen.value = false;
    alert.error(i18n.t("grocery-scan.lookup-failed"));
    return;
  }

  rememberBarcode.value = true;
  saveProduct.value = canSaveProduct.value;
  store.value = found.draft.store ?? "walmart";
  typedName.value = "";
  if (found.saved) {
    sheetOpen.value = false;
    await addRestock(found.saved);
    return;
  }
  sheetOpen.value = true;
}

function snapFront() {
  sheetOpen.value = false;
  scannerPrompt.value = i18n.t("grocery-scan.snap-front-prompt");
  scannerOpen.value = true;
}

function close() {
  sheetOpen.value = false;
  reset();
}

/** Puts something on the Out of list, with an undo when it wasn't on it already */
async function addRestock(product: GroceryProductOut | null, data?: GroceryRestockCreate) {
  const item: GroceryRestockCreate = data ?? { name: product!.food.name, foodId: product!.foodId, store: product!.store };
  const wasListed = items.value.some(existing => (item.foodId && existing.foodId === item.foodId) || existing.name.toLowerCase() === item.name.toLowerCase());
  if (!(await add(item))) {
    alert.error(i18n.t("grocery-scan.add-failed"));
    return false;
  }

  const added = items.value.find(existing => (item.foodId && existing.foodId === item.foodId) || existing.name.toLowerCase() === item.name.toLowerCase());
  const message = product
    ? i18n.t("grocery-scan.added-product", { food: item.name, name: product.name })
    : i18n.t("grocery-scan.added", { food: item.name });
  alert.success(message, null, {
    timeout: 6000,
    action: !wasListed && added ? { message: i18n.t("restock.undo"), onClick: () => { void remove(added.id); } } : undefined,
  });
  return true;
}

async function addToList() {
  const found = scan.value;
  if (!found || adding.value) return;
  adding.value = true;
  error.value = "";
  try {
    if (outcome.value === "likely" && found.likelySaved) {
      const likely = found.likelySaved;
      if (rememberBarcode.value && found.barcode) {
        const { foodId, name, store, url, priority, enabled, packageQuantity, packageUnit, notes } = likely;
        const result = await api.groceries.updateProduct(likely.id, { foodId, name, store, url, priority, enabled, packageQuantity, packageUnit, notes, barcode: found.barcode });
        if (!result.data) throw result.error;
        // and one without a photo gets the package's
        if (found.draft.photo && !likely.photo) await api.groceries.attachPhoto(likely.id, found.draft.photo.token);
      }
      if (await addRestock(likely)) close();
      return;
    }

    if (outcome.value === "new") {
      const draft = found.draft;
      if (saveProduct.value && canSaveProduct.value) {
        const foodId = await foodIdFor(api, [], draft.food ?? ingredientName.value);
        const result = await api.groceries.createProduct({
          foodId,
          name: draft.name ?? "",
          store: store.value,
          url: null,
          packageQuantity: draft.packageQuantity && draft.packageUnit ? draft.packageQuantity : null,
          packageUnit: draft.packageQuantity && draft.packageUnit ? draft.packageUnit : null,
          barcode: found.barcode ?? null,
        });
        if (!result.data) throw result.error;
        if (draft.photo) await api.groceries.attachPhoto(result.data.id, draft.photo.token);
        if (await addRestock(result.data)) close();
        return;
      }
      const name = ingredientName.value || draft.name || "";
      if (await addRestock(null, { name, foodId: draft.food?.id ?? null })) close();
      return;
    }

    if (outcome.value === "unknown" && typedName.value.trim()) {
      if (await addRestock(null, { name: typedName.value.trim() })) close();
    }
  }
  catch (cause) {
    error.value = groceryError(cause);
  }
  finally {
    adding.value = false;
  }
}
</script>

<style scoped>
.restock-scan {
  padding: 22px 22px calc(env(safe-area-inset-bottom) + 18px);
}

.restock-scan__looking {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  font-weight: 600;
}

.restock-scan__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.restock-scan__title {
  min-width: 0;
}

.restock-scan__name {
  margin: 4px 0 2px;
  font-size: 1.375rem;
  line-height: 1.25;
}

.restock-scan__meta {
  margin: 0 0 8px;
  color: rgb(var(--v-theme-ink-muted));
}

.restock-scan__hint {
  margin: 2px 0 0 4px;
  font-size: 0.875rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.restock-scan__stores {
  margin-top: 8px;
}

.restock-scan__store--selected {
  border-color: rgb(var(--v-theme-on-surface)) !important;
  background: rgb(var(--v-theme-on-surface));
  color: rgb(var(--v-theme-surface)) !important;
}

.restock-scan__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}
</style>
