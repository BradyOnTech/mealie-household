<template>
  <section class="import-settings">
    <button
      type="button"
      class="import-settings__toggle"
      :aria-expanded="open"
      aria-controls="import-settings-panel"
      @click="open = !open"
    >
      <v-icon size="18" :icon="$globals.icons.tune" />
      <span class="import-settings__label">{{ $t("recipe-import.settings") }}</span>
      <span class="import-settings__summary">{{ summary }}</span>
      <v-icon
        size="18"
        class="import-settings__chevron"
        :class="{ 'import-settings__chevron--open': open }"
        :icon="$globals.icons.chevronDown"
      />
    </button>
    <v-expand-transition>
      <div v-show="open" id="import-settings-panel" class="import-settings__panel">
        <div
          v-for="setting in settings"
          :key="setting.key"
          class="import-settings__row"
        >
          <label :for="`import-setting-${setting.key}`" class="import-settings__text">
            <span class="import-settings__name">{{ setting.label }}</span>
            <span class="import-settings__hint">{{ setting.hint }}</span>
          </label>
          <v-switch
            :id="`import-setting-${setting.key}`"
            v-model="setting.model.value"
            :disabled="setting.disabled"
            color="primary"
            density="compact"
            inset
            hide-details
            class="import-settings__switch"
          />
        </div>
        <p class="import-settings__footnote">
          {{ $t("recipe-import.settings-are-remembered") }}
        </p>
      </div>
    </v-expand-transition>
  </section>
</template>

<script setup lang="ts">
import type { WritableComputedRef } from "vue";
import { useNewRecipeOptions } from "~/composables/use-new-recipe-options";

const props = defineProps<{
  /** The group has an AI provider, which organizing, new labels and translating need */
  aiEnabled: boolean;
}>();

interface Setting {
  key: string;
  label: string;
  short: string;
  hint: string;
  model: WritableComputedRef<boolean>;
  disabled?: boolean;
}

const i18n = useI18n();
const open = ref(false);
const options = useNewRecipeOptions();

const language = computed(() => {
  const locale = i18n.locale.value;
  try {
    return new Intl.DisplayNames([locale], { type: "language" }).of(locale.split("-")[0]!) ?? locale;
  }
  catch {
    return locale;
  }
});

const settings = computed<Setting[]>(() => {
  const all: (Setting & { needsAI?: boolean })[] = [
    {
      key: "organize",
      label: i18n.t("recipe-import.organize"),
      short: i18n.t("recipe-import.organize-short"),
      hint: i18n.t("recipe-import.organize-hint"),
      model: options.organize,
      needsAI: true,
    },
    {
      key: "new-labels",
      label: i18n.t("recipe-import.new-labels"),
      short: i18n.t("recipe-import.new-labels-short"),
      hint: i18n.t("recipe-import.new-labels-hint"),
      model: options.createNewOrganizers,
      disabled: !options.organize.value,
      needsAI: true,
    },
    {
      key: "site-labels",
      label: i18n.t("recipe-import.site-labels"),
      short: i18n.t("recipe-import.site-labels-short"),
      hint: i18n.t("recipe-import.site-labels-hint"),
      model: options.keepSourceLabels,
    },
    {
      key: "translate",
      label: i18n.t("recipe-import.translate", { language: language.value }),
      short: i18n.t("recipe-import.translate-short"),
      hint: i18n.t("recipe-import.translate-hint"),
      model: options.translateRecipe,
      needsAI: true,
    },
    {
      key: "review",
      label: i18n.t("recipe-import.review-ingredients"),
      short: i18n.t("recipe-import.review-ingredients-short"),
      hint: i18n.t("recipe-import.review-ingredients-hint"),
      model: options.parseRecipe,
    },
    {
      key: "edit",
      label: i18n.t("recipe-import.open-for-editing"),
      short: i18n.t("recipe-import.open-for-editing-short"),
      hint: i18n.t("recipe-import.open-for-editing-hint"),
      model: options.stayInEditMode,
    },
  ];
  return all.filter(setting => props.aiEnabled || !setting.needsAI);
});

const summary = computed(() => {
  const on = settings.value.filter(setting => setting.model.value && !setting.disabled).map(setting => setting.short);
  return on.length ? on.join(" · ") : i18n.t("recipe-import.settings-all-off");
});
</script>

<style scoped>
.import-settings__toggle {
  appearance: none;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 2px;
  color: rgb(var(--v-theme-on-background));
  text-align: left;
}

.import-settings__label {
  flex: none;
  font-weight: 600;
}

.import-settings__summary {
  min-width: 0;
  overflow: hidden;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.import-settings__chevron {
  flex: none;
  margin-left: auto;
  color: rgb(var(--v-theme-ink-muted));
  transition: transform 0.2s ease;
}

.import-settings__chevron--open {
  transform: rotate(180deg);
}

.import-settings__panel {
  padding: 4px 18px 10px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
}

.import-settings__row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.import-settings__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  cursor: pointer;
}

.import-settings__name {
  font-weight: 600;
}

.import-settings__hint {
  font-size: 0.875rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.import-settings__switch {
  flex: none;
  margin-left: auto;
}

/* The theme's switch tracks look alike on and off, so these are made plainly different */
.import-settings__switch :deep(.v-switch__track) {
  opacity: 1;
  background-color: rgb(var(--v-theme-rule));
}

.import-settings__switch :deep(.v-selection-control--dirty .v-switch__track) {
  background-color: rgb(var(--v-theme-on-surface));
}

.import-settings__switch :deep(.v-switch__thumb) {
  background-color: rgb(var(--v-theme-surface-bright));
  color: rgb(var(--v-theme-surface-bright));
}

.import-settings__footnote {
  margin: 10px 0 0;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
}
</style>
