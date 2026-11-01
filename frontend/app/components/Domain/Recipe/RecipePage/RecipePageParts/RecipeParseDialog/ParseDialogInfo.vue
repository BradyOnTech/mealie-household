<template>
  <v-card variant="tonal" color="info" class="pa-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon>{{ $globals.icons.informationOutline }}</v-icon>
      <div class="text-subtitle-1 font-weight-bold">
        {{ $t("recipe.parser.explainer-title") }}
      </div>
    </div>
    <p class="text-body-2 mb-3 text-high-emphasis">
      {{ $t("recipe.parser.explainer-intro") }}
    </p>
    <dl class="parse-explainer text-body-2 text-high-emphasis">
      <template v-for="field in fields" :key="field.label">
        <dt>{{ field.label }}</dt>
        <dd>{{ field.help }}</dd>
      </template>
    </dl>
    <div class="d-flex justify-end mt-2">
      <v-btn variant="flat" color="info" size="small" @click="$emit('dismiss')">
        {{ $t("recipe.parser.explainer-dismiss") }}
      </v-btn>
    </div>
  </v-card>
</template>

<script setup lang="ts">
defineEmits<{ dismiss: [] }>();

const { t } = useI18n();
const fields = computed(() => [
  { label: t("recipe.parser.field-quantity"), help: t("recipe.parser.field-quantity-help") },
  { label: t("recipe.parser.field-unit"), help: t("recipe.parser.field-unit-help") },
  { label: t("recipe.parser.field-food"), help: t("recipe.parser.field-food-help") },
  { label: t("recipe.parser.field-note"), help: t("recipe.parser.field-note-help") },
]);
</script>

<style scoped>
.parse-explainer {
  display: grid;
  grid-template-columns: max-content 1fr;
  column-gap: 16px;
  row-gap: 6px;
  margin: 12px 0 0;
}
.parse-explainer dt {
  font-weight: 700;
}
.parse-explainer dd {
  margin: 0;
}
</style>
