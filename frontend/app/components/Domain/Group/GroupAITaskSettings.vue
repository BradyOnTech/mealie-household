<template>
  <section class="ai-tasks" aria-labelledby="ai-tasks-title">
    <h3 id="ai-tasks-title" class="ai-tasks__heading">
      {{ $t('group.ai-provider-settings.tasks-title') }}
    </h3>
    <p class="ai-tasks__intro">
      {{ $t('group.ai-provider-settings.tasks-detail') }}
    </p>
    <ul class="ai-tasks__notes">
      <li>{{ $t('group.ai-provider-settings.tasks-group-scope') }}</li>
      <li>{{ $t('group.ai-provider-settings.tasks-usage-note') }}</li>
    </ul>

    <ul class="ai-tasks__list">
      <li v-for="row in rows" :key="row.task" class="ai-task" :data-task="row.task">
        <div class="ai-task__head">
          <div class="ai-task__summary">
            <h4 class="ai-task__name">
              {{ taskName(row.task) }}
              <span v-if="row.customized" class="ai-task__badge">{{ $t('group.ai-provider-settings.customized') }}</span>
            </h4>
            <p class="ai-task__description">
              {{ $t(`group.ai-provider-settings.task-${row.task}-description`) }}
            </p>
            <p class="ai-task__uses" data-testid="uses-text">
              <span class="ai-task__uses-label">{{ row.readsImages ? $t('group.ai-provider-settings.uses-text') : $t('group.ai-provider-settings.uses') }}</span>
              <span v-if="row.text">{{ describe(row.text) }}</span>
              <span v-else class="ai-task__missing">{{ $t('group.ai-provider-settings.no-provider-for-task') }}</span>
            </p>
            <p v-if="row.readsImages" class="ai-task__uses" data-testid="uses-images">
              <span class="ai-task__uses-label">{{ $t('group.ai-provider-settings.uses-images') }}</span>
              <span v-if="row.images">{{ describe(row.images) }}</span>
              <span v-else class="ai-task__missing">{{ $t('group.ai-provider-settings.no-image-provider-for-task') }}</span>
            </p>
          </div>
          <v-btn
            variant="text"
            size="small"
            class="ai-task__toggle"
            :aria-expanded="open === row.task ? 'true' : 'false'"
            :aria-controls="`ai-task-${row.task}`"
            @click="toggle(row.task)"
          >
            {{ open === row.task ? $t('general.done') : $t('group.ai-provider-settings.customize') }}
          </v-btn>
        </div>

        <div
          v-if="open === row.task"
          :id="`ai-task-${row.task}`"
          class="ai-task__fields"
          role="group"
          :aria-label="taskName(row.task)"
        >
          <v-select
            :model-value="row.setting?.providerId ?? INHERIT"
            :items="providerItems(defaultProviderName)"
            :label="$t('group.ai-provider-settings.task-provider')"
            density="compact"
            variant="outlined"
            hide-details
            @update:model-value="(value: string) => change(row.task, { providerId: fromItem(value) })"
          />
          <GroupAIModelFields
            v-if="row.setting?.providerId && providerById(row.setting.providerId)"
            :model="row.setting.model"
            :effort="row.setting.reasoningEffort"
            :provider-type="providerById(row.setting.providerId)!.providerType ?? 'openai'"
            :catalog="catalogs[row.setting.providerId] ?? null"
            :catalog-loading="!!catalogLoading[row.setting.providerId]"
            :inherited-model="providerById(row.setting.providerId)!.model || null"
            :inherited-effort="providerById(row.setting.providerId)!.reasoningEffort ?? null"
            inheriting
            @update:model="(value) => change(row.task, { model: value ?? null })"
            @update:effort="(value) => change(row.task, { reasoningEffort: value ?? null })"
          />

          <template v-if="row.readsImages">
            <h5 class="ai-task__subheading">
              {{ $t('group.ai-provider-settings.task-images-title') }}
            </h5>
            <p class="ai-task__description">
              {{ $t('group.ai-provider-settings.task-images-detail') }}
            </p>
            <v-select
              :model-value="row.setting?.imageProviderId ?? INHERIT"
              :items="providerItems(imageProviderName, true)"
              :label="$t('group.ai-provider-settings.task-image-provider')"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="(value: string) => change(row.task, { imageProviderId: fromItem(value) })"
            />
            <GroupAIModelFields
              v-if="row.setting?.imageProviderId && providerById(row.setting.imageProviderId)"
              :model="row.setting.imageModel"
              :effort="row.setting.imageReasoningEffort"
              :provider-type="providerById(row.setting.imageProviderId)!.providerType ?? 'openai'"
              :catalog="catalogs[row.setting.imageProviderId] ?? null"
              :catalog-loading="!!catalogLoading[row.setting.imageProviderId]"
              :inherited-model="providerById(row.setting.imageProviderId)!.model || null"
              :inherited-effort="providerById(row.setting.imageProviderId)!.reasoningEffort ?? null"
              inheriting
              @update:model="(value) => change(row.task, { imageModel: value ?? null })"
              @update:effort="(value) => change(row.task, { imageReasoningEffort: value ?? null })"
            />
          </template>

          <div v-if="row.customized" class="ai-task__actions">
            <v-btn variant="text" size="small" @click="reset(row.task)">
              {{ $t('group.ai-provider-settings.reset-task') }}
            </v-btn>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import GroupAIModelFields from "~/components/Domain/Group/GroupAIModelFields.vue";
import { useAIProviders } from "~/composables/use-ai-providers";
import {
  AI_TASKS,
  CHATGPT_DEFAULT_EFFORT,
  effectiveChoice,
  taskSetting,
  updateTaskSetting,
  useAIModelCatalogs,
  type AIEffectiveChoice,
  type TaskChoicePatch,
} from "~/composables/use-ai-task-settings";
import type { AIProviderSummary, AITask } from "~/lib/api/types/group";
import type { AIProviderSettingsOut } from "~/lib/api/types/user";

const settings = defineModel<AIProviderSettingsOut>({ required: true });

/** Stands in for "use the group's choice" in the provider menus, since a menu item can't hold null */
const INHERIT = "__inherit__";

const i18n = useI18n();
const { listModels } = useAIProviders();
const { catalogs, loading: catalogLoading, load } = useAIModelCatalogs(async (id) => {
  const { data } = await listModels(id);
  return data;
});

const open = ref<AITask | null>(null);
const providers = computed<AIProviderSummary[]>(() => settings.value.providers ?? []);

function providerById(id: string | null | undefined) {
  return id ? providers.value.find(provider => provider.id === id) : undefined;
}

const defaultProviderName = computed(() => providerById(settings.value.defaultProviderId)?.name ?? null);
const imageProviderName = computed(() => providerById(settings.value.imageProviderId)?.name ?? null);

const rows = computed(() => AI_TASKS.map(({ task, readsImages }) => {
  const setting = taskSetting(settings.value, task);
  return {
    task,
    readsImages,
    setting,
    customized: !!(setting?.providerId || setting?.imageProviderId),
    text: effectiveChoice(settings.value, providers.value, task, false),
    images: readsImages ? effectiveChoice(settings.value, providers.value, task, true) : null,
  };
}));

function taskName(task: AITask) {
  return i18n.t(`group.ai-provider-settings.task-${task}`);
}

function effortName(value: string) {
  const key = `group.ai-provider-settings.effort-${value}`;
  return i18n.te(key) ? i18n.t(key) : value;
}

/** "ChatGPT · gpt-x · Low reasoning (group default)", in words */
function describe(choice: AIEffectiveChoice) {
  const isChatGPT = choice.provider.providerType === "chatgpt";
  const model = choice.model || i18n.t("group.ai-provider-settings.model-plan-default");
  const effort = choice.reasoningEffort
    ? i18n.t("group.ai-provider-settings.reasoning-level", [effortName(choice.reasoningEffort)])
    : isChatGPT
      ? i18n.t("group.ai-provider-settings.reasoning-level", [effortName(CHATGPT_DEFAULT_EFFORT)])
      : i18n.t("group.ai-provider-settings.reasoning-model-decides");
  const source = i18n.t(`group.ai-provider-settings.source-${choice.source}`);
  return `${choice.provider.name} · ${model} · ${effort} (${source})`;
}

function providerItems(groupChoice: string | null, images = false) {
  const inherit = images
    ? groupChoice
      ? i18n.t("group.ai-provider-settings.use-group-image-provider", [groupChoice])
      : i18n.t("group.ai-provider-settings.use-group-image-provider-none")
    : groupChoice
      ? i18n.t("group.ai-provider-settings.use-group-default", [groupChoice])
      : i18n.t("group.ai-provider-settings.use-group-default-none");
  return [
    { title: inherit, value: INHERIT },
    ...providers.value.map(provider => ({ title: provider.name, value: provider.id })),
  ];
}

function fromItem(value: string | null) {
  return !value || value === INHERIT ? null : value;
}

/** Lists a ChatGPT provider's models the first time a task that uses it is opened */
function loadCatalogs(task: AITask) {
  const setting = taskSetting(settings.value, task);
  for (const id of [setting?.providerId, setting?.imageProviderId]) {
    if (providerById(id)?.providerType === "chatgpt") void load(id);
  }
}

function toggle(task: AITask) {
  open.value = open.value === task ? null : task;
  if (open.value) loadCatalogs(task);
}

function change(task: AITask, patch: TaskChoicePatch) {
  settings.value = { ...settings.value, taskSettings: updateTaskSetting(settings.value.taskSettings, task, patch) };
  loadCatalogs(task);
}

function reset(task: AITask) {
  settings.value = {
    ...settings.value,
    taskSettings: (settings.value.taskSettings ?? []).filter(setting => setting.task !== task),
  };
}
</script>

<style scoped>
.ai-tasks {
  margin-top: 28px;
}

.ai-tasks__heading {
  margin: 0 0 4px;
  font-family: var(--paper-serif);
  font-size: 1.25rem;
  font-weight: 420;
  text-wrap: balance;
}

.ai-tasks__intro,
.ai-tasks__notes {
  margin: 0 0 10px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
  text-wrap: pretty;
}

.ai-tasks__notes {
  margin-bottom: 14px;
  padding-left: 18px;
}

.ai-tasks__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.ai-task {
  padding: 12px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.ai-task__head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.ai-task__summary {
  flex: 1;
  min-width: 0;
}

.ai-task__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 2px;
  font-size: 0.9375rem;
  font-weight: 600;
}

.ai-task__badge {
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(var(--v-theme-sage), 0.15);
  color: rgb(var(--v-theme-sage));
  font-size: 0.6875rem;
  font-weight: 700;
}

.ai-task__description {
  margin: 0 0 4px;
  font-size: 0.8125rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
  text-wrap: pretty;
}

.ai-task__uses {
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.ai-task__uses-label {
  margin-right: 4px;
  font-weight: 600;
}

.ai-task__missing {
  color: rgb(var(--v-theme-tomato));
}

.ai-task__toggle {
  flex-shrink: 0;
  min-height: 40px;
}

.ai-task__fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 12px;
  padding: 14px;
  border-radius: 12px;
  background: rgb(var(--v-theme-wash));
}

.ai-task__subheading {
  margin: 6px 0 0;
  font-size: 0.8125rem;
  font-weight: 600;
}

.ai-task__subheading + .ai-task__description {
  margin-top: -10px;
}

.ai-task__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
