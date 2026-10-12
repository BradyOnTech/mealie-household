<template>
  <v-dialog v-model="opened" max-width="560" :persistent="saving">
    <v-card>
      <v-card-title>{{ $t(rule ? 'groceries.edit-rule' : 'groceries.add-rule') }}</v-card-title>
      <v-card-text>
        <v-alert v-if="error" type="error" class="mb-4">
          {{ error }}
        </v-alert>
        <v-autocomplete v-model="form.foodId" :items="foods" item-title="name" item-value="id" :label="$t('groceries.ingredient')" />
        <v-select v-model="form.kind" :items="kinds" :label="$t('groceries.rule-kind')" />
        <v-row>
          <v-col cols="6">
            <v-text-field v-model="amount" type="number" min="0" step="any" :label="$t('groceries.amount')" />
          </v-col>
          <v-col cols="6">
            <v-select v-model="form.unit" :items="groceryUnits" :label="$t('groceries.unit')" />
          </v-col>
        </v-row>
        <v-select v-if="form.kind === 'recurring'" v-model="form.mode" :items="modes" :label="$t('groceries.recurring-mode')" />
        <v-alert type="info" variant="tonal" class="mb-4">
          {{ $t(form.kind === 'pantry' ? 'groceries.pantry-hint' : 'groceries.staple-hint') }}
        </v-alert>
        <v-switch v-model="form.enabled" color="primary" :label="$t('groceries.rule-enabled')" hide-details />
      </v-card-text>
      <v-card-actions>
        <v-spacer /><v-btn :disabled="saving" @click="opened = false">
          {{ $t('groceries.cancel') }}
        </v-btn>
        <v-btn color="primary" variant="flat" :disabled="!form.foodId || amount === ''" :loading="saving" @click="save">
          {{ $t('groceries.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { GroceryFoodRuleCreate, GroceryFoodRuleOut, GroceryRuleKind } from "~/lib/api/types/grocery";
import type { IngredientFood } from "~/lib/api/types/recipe";
import { useUserApi } from "~/composables/api";
import { groceryError, groceryUnits } from "~/composables/groceries/grocery-utils";

const props = defineProps<{ foods: IngredientFood[]; rule?: GroceryFoodRuleOut | null; initialKind?: GroceryRuleKind }>();
const opened = defineModel<boolean>({ default: false });
const emit = defineEmits<{ saved: [] }>();
const api = useUserApi();
const i18n = useI18n();
const saving = ref(false);
const error = ref("");
const amount = ref<string | number>(1);
const form = reactive<GroceryFoodRuleCreate>({ foodId: "", kind: "recurring", quantity: 1, unit: "count", mode: "minimum", enabled: true });
const kinds = computed(() => [{ title: i18n.t("groceries.pantry"), value: "pantry" }, { title: i18n.t("groceries.staples"), value: "recurring" }]);
const modes = computed(() => [{ title: i18n.t("groceries.minimum"), value: "minimum" }, { title: i18n.t("groceries.extra"), value: "extra" }]);

watch(opened, (value) => {
  if (!value) return;
  error.value = "";
  Object.assign(form, props.rule ? { ...props.rule } : { foodId: "", kind: props.initialKind ?? "recurring", quantity: 1, unit: "count", mode: "minimum", enabled: true });
  amount.value = props.rule?.quantity ?? 1;
});

async function save() {
  saving.value = true;
  error.value = "";
  try {
    const payload: GroceryFoodRuleCreate = { foodId: form.foodId, kind: form.kind, quantity: Number(amount.value), unit: form.unit, mode: form.mode, enabled: form.enabled };
    const result = props.rule ? await api.groceries.updateRule(props.rule.id, payload) : await api.groceries.createRule(payload);
    if (!result.data) throw result.error;
    emit("saved");
    opened.value = false;
  }
  catch (cause) { error.value = groceryError(cause); }
  finally { saving.value = false; }
}
</script>
