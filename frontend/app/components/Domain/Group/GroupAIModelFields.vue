<template>
  <div class="ai-model-fields">
    <v-combobox
      v-if="showModel && isChatGPT"
      :model-value="model ?? ''"
      :items="modelItems"
      :return-object="false"
      :label="$t('group.ai-provider-settings.model')"
      :placeholder="modelPlaceholder"
      persistent-placeholder
      :loading="catalogLoading"
      :hint="modelHint"
      persistent-hint
      clearable
      density="compact"
      variant="outlined"
      @update:model-value="setModel"
    >
      <template #item="{ props: itemProps, item }">
        <v-list-item v-bind="itemProps" :subtitle="item.subtitle ?? undefined" />
      </template>
    </v-combobox>
    <v-text-field
      v-else-if="showModel"
      :model-value="model ?? ''"
      :label="$t('group.ai-provider-settings.model')"
      :placeholder="modelPlaceholder"
      persistent-placeholder
      :hint="modelHint"
      persistent-hint
      clearable
      density="compact"
      variant="outlined"
      @update:model-value="setModel"
    />

    <v-select
      :model-value="effort ?? INHERIT"
      :items="effortItems"
      :label="$t('group.ai-provider-settings.reasoning')"
      :hint="effortHint"
      persistent-hint
      density="compact"
      variant="outlined"
      @update:model-value="setEffort"
    >
      <template #item="{ props: itemProps, item }">
        <v-list-item v-bind="itemProps" :subtitle="item.subtitle ?? undefined" />
      </template>
    </v-select>
  </div>
</template>

<script setup lang="ts">
import { CHATGPT_DEFAULT_EFFORT, effortOptions } from "~/composables/use-ai-task-settings";
import type { AIModelCatalog, AIProviderType } from "~/lib/api/types/group";

const props = withDefaults(defineProps<{
  providerType: AIProviderType;
  /** The models the provider lists, or null while they haven't been asked for */
  catalog?: AIModelCatalog | null;
  catalogLoading?: boolean;
  /** What an empty model falls back to: the provider's own model, when this is a task's override */
  inheritedModel?: string | null;
  /** What an empty reasoning effort falls back to, when this is a task's override */
  inheritedEffort?: string | null;
  /** True for a task's override, which falls back to its provider rather than to Mealie's defaults */
  inheriting?: boolean;
  /** False when the model has a field of its own elsewhere, as an API-key provider's does */
  showModel?: boolean;
}>(), {
  catalog: null,
  catalogLoading: false,
  inheritedModel: null,
  inheritedEffort: null,
  inheriting: false,
  showModel: true,
});

const model = defineModel<string | null | undefined>("model");
const effort = defineModel<string | null | undefined>("effort");

/** Stands in for "no choice" in the reasoning menu, since a menu item can't hold null */
const INHERIT = "__inherit__";

const i18n = useI18n();
const isChatGPT = computed(() => props.providerType === "chatgpt");
const discovered = computed(() => !!props.catalog?.discovered);

function effortName(value: string) {
  const key = `group.ai-provider-settings.effort-${value}`;
  return i18n.te(key) ? i18n.t(key) : value;
}

const modelItems = computed(() => (props.catalog?.models ?? []).map(option => ({
  title: option.displayName,
  value: option.model,
  subtitle: [option.model !== option.displayName ? option.model : null, option.isDefault ? i18n.t("group.ai-provider-settings.model-plan-default-tag") : null]
    .filter(Boolean)
    .join(" · "),
})));

const modelPlaceholder = computed(() => {
  if (props.inheriting && props.inheritedModel) {
    return i18n.t("group.ai-provider-settings.model-provider-default", [props.inheritedModel]);
  }
  return isChatGPT.value ? i18n.t("group.ai-provider-settings.model-plan-default") : "";
});

const modelHint = computed(() => {
  if (!isChatGPT.value) return i18n.t("group.ai-provider-settings.model-custom-hint");
  if (props.catalogLoading) return i18n.t("group.ai-provider-settings.model-catalog-loading");
  if (props.catalog && !discovered.value) {
    return props.catalog.message
      ? i18n.t("group.ai-provider-settings.model-catalog-unavailable-reason", [props.catalog.message])
      : i18n.t("group.ai-provider-settings.model-catalog-unavailable");
  }
  return i18n.t("group.ai-provider-settings.model-catalog-hint");
});

/** The model whose reasoning levels apply: the one chosen here, or else the one it falls back to */
const effectiveModel = computed(() => model.value || (props.inheriting ? props.inheritedModel : null) || "");

const effortItems = computed(() => {
  const defaultTitle = props.inheriting
    ? i18n.t("group.ai-provider-settings.reasoning-inherit", [
        props.inheritedEffort
          ? effortName(props.inheritedEffort)
          : isChatGPT.value
            ? effortName(CHATGPT_DEFAULT_EFFORT)
            : i18n.t("group.ai-provider-settings.reasoning-not-sent"),
      ])
    : isChatGPT.value
      ? i18n.t("group.ai-provider-settings.reasoning-default-chatgpt")
      : i18n.t("group.ai-provider-settings.reasoning-default-api");

  const entry = props.catalog?.models?.find(option => option.model === effectiveModel.value)
    ?? (effectiveModel.value ? undefined : props.catalog?.models?.find(option => option.isDefault));
  const descriptions = new Map((entry?.supportedReasoningEfforts ?? []).map(option => [option.effort, option.description]));

  return [
    { title: defaultTitle, value: INHERIT, subtitle: undefined as string | null | undefined },
    ...effortOptions(props.catalog, effectiveModel.value, effort.value).map(value => ({
      title: effortName(value),
      value,
      subtitle: descriptions.get(value)
        ?? (entry?.defaultReasoningEffort === value ? i18n.t("group.ai-provider-settings.effort-model-default") : undefined),
    })),
  ];
});

const effortHint = computed(() => isChatGPT.value
  ? i18n.t("group.ai-provider-settings.reasoning-hint-chatgpt")
  : i18n.t("group.ai-provider-settings.reasoning-hint-api"),
);

function setModel(value: string | null) {
  const trimmed = typeof value === "string" ? value.trim() : "";
  model.value = trimmed || null;
}

function setEffort(value: string | null) {
  effort.value = !value || value === INHERIT ? null : value;
}
</script>

<style scoped>
.ai-model-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
</style>
