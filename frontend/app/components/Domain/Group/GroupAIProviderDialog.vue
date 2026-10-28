<template>
  <BaseDialog
    v-model="dialog"
    :title="isEdit ? $t('group.ai-provider-settings.edit-provider') : $t('group.ai-provider-settings.add-provider')"
    :icon="$globals.icons.robot"
    :loading="loading"
    width="560"
    can-submit
    :submit-icon="isEdit ? $globals.icons.save : $globals.icons.createAlt"
    :submit-text="isEdit ? $t('general.update') : $t('group.ai-provider-settings.add')"
    :submit-disabled="submitDisabled"
    disable-submit-on-enter
    @submit="handleSubmit"
    @close="resetForm"
  >
    <v-card-text v-if="init" class="ai-provider-dialog">
      <v-form ref="form" v-no-autofill @submit.prevent>
        <!-- How to connect: a choice when adding, a label when editing -->
        <fieldset v-if="!isEdit" class="ai-provider-types">
          <legend class="ai-provider-dialog__label">
            {{ $t('group.ai-provider-settings.how-to-connect') }}
          </legend>
          <button
            v-for="option in providerOptions"
            :key="option.value"
            type="button"
            class="ai-provider-type"
            :class="{ 'ai-provider-type--active': formData.providerType === option.value }"
            :aria-pressed="formData.providerType === option.value"
            @click="chooseType(option.value)"
          >
            <span class="ai-provider-type__title">
              {{ option.title }}
              <span v-if="option.recommended" class="ai-provider-type__badge">{{ $t('group.ai-provider-settings.recommended') }}</span>
            </span>
            <span class="ai-provider-type__text">{{ option.description }}</span>
          </button>
        </fieldset>
        <p v-else class="ai-provider-dialog__label">
          {{ isChatGPT ? $t('group.ai-provider-settings.provider-type-chatgpt') : $t('group.ai-provider-settings.provider-type-api-key') }}
        </p>

        <template v-if="isChatGPT">
          <p v-if="!isEdit" class="ai-provider-dialog__intro">
            {{ $t('group.ai-provider-settings.chatgpt-description') }}
          </p>
          <GroupChatGPTSignIn
            ref="signIn"
            v-model:login="login"
            :saved-account="savedAccount"
            class="mb-6"
            @connected="onConnected"
          />
          <v-text-field
            v-model="formData.name"
            :label="$t('group.ai-provider-settings.provider-name')"
            :hint="$t('group.ai-provider-settings.provider-name-description')"
            :rules="[validators.required]"
            density="compact"
            variant="outlined"
            class="mb-4"
          />
        </template>

        <template v-else>
          <p v-if="!isEdit" class="ai-provider-dialog__intro">
            {{ $t('group.ai-provider-settings.api-key-intro') }}
          </p>
          <v-text-field
            v-model="formData.name"
            :label="$t('group.ai-provider-settings.provider-name')"
            :hint="$t('group.ai-provider-settings.provider-name-description')"
            :rules="[validators.required]"
            density="compact"
            variant="outlined"
            class="mb-4"
          />
          <v-text-field
            v-model="formData.apiKey"
            :label="$t('group.ai-provider-settings.api-key')"
            :hint="$t(
              isEdit
                ? 'group.ai-provider-settings.api-key-description-edit'
                : 'group.ai-provider-settings.api-key-description-create',
            )"
            :persistent-hint="isEdit"
            :rules="isEdit ? [] : [validators.required]"
            density="compact"
            variant="outlined"
            type="password"
            autocomplete="off"
            class="mb-4"
          />
          <v-text-field
            v-model="formData.model"
            :label="$t('group.ai-provider-settings.model')"
            :hint="$t('group.ai-provider-settings.model-description')"
            :rules="[validators.required]"
            density="compact"
            variant="outlined"
            class="mb-4"
          />
          <v-text-field
            v-model="formData.baseUrl"
            :label="$t('group.ai-provider-settings.base-url')"
            :hint="$t('group.ai-provider-settings.base-url-description')"
            density="compact"
            variant="outlined"
            class="mb-4"
          />
        </template>

        <v-expansion-panels v-model="advancedPanel" variant="accordion" class="ai-provider-dialog__advanced">
          <v-expansion-panel value="advanced" elevation="0">
            <v-expansion-panel-title class="text-subtitle-2">
              {{ $t('search.advanced') }}
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <GroupAIModelFields
                v-model:model="chatgptModel"
                v-model:effort="formData.reasoningEffort"
                :provider-type="formData.providerType"
                :show-model="isChatGPT"
                :catalog="catalogKey ? catalogs[catalogKey] ?? null : null"
                :catalog-loading="!!(catalogKey && catalogLoading[catalogKey])"
                class="mb-4"
              />
              <v-number-input
                v-model.number="formData.timeout"
                :label="$t('group.ai-provider-settings.request-timeout-seconds')"
                :hint="$t('group.ai-provider-settings.request-timeout-description')"
                persistent-hint
                :min="0"
                density="compact"
                variant="outlined"
                class="mb-4"
              />
              <template v-if="!isChatGPT">
                <div class="mb-2 text-subtitle-2">
                  {{ $t('group.ai-provider-settings.request-headers') }}
                </div>
                <BaseKeyValueEditor v-model="formData.requestHeaders" class="mb-4" />
                <v-divider class="mb-4" />
                <div class="mb-2 text-subtitle-2">
                  {{ $t('group.ai-provider-settings.request-params') }}
                </div>
                <BaseKeyValueEditor v-model="formData.requestParams" />
              </template>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

        <div v-if="testing" class="ai-provider-dialog__testing" role="status">
          <v-progress-circular indeterminate size="16" width="2" color="primary" />
          {{ $t('group.ai-provider-settings.testing-connection') }}
        </div>
        <v-alert
          v-else-if="testResult"
          :type="testResult.success ? 'success' : 'error'"
          density="compact"
          variant="tonal"
          class="mt-4"
        >
          {{ connectionMessage }}
        </v-alert>
      </v-form>
    </v-card-text>
    <AppLoader v-else />

    <template #custom-card-action>
      <v-btn
        variant="text"
        :loading="testing"
        :disabled="testDisabled || testing"
        @click="handleTest"
      >
        {{ $t('group.ai-provider-settings.test-connection') }}
      </v-btn>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import GroupAIModelFields from "~/components/Domain/Group/GroupAIModelFields.vue";
import GroupChatGPTSignIn from "~/components/Domain/Group/GroupChatGPTSignIn.vue";
import { useAIProviders } from "~/composables/use-ai-providers";
import { useAIModelCatalogs } from "~/composables/use-ai-task-settings";
import { validators } from "~/composables/use-validators";
import type {
  AIProviderCreate,
  AIProviderTestResult,
  AIProviderType,
  AIProviderUpdate,
  ChatGPTLoginOut,
} from "~/lib/api/types/group";
import type { AIProviderPayload } from "~/lib/api/user/group-ai-providers";

const props = withDefaults(defineProps<{
  providerId?: string;
  /** Which kind a new provider starts as */
  initialType?: AIProviderType;
}>(), {
  providerId: undefined,
  initialType: "chatgpt",
});

const emit = defineEmits<{
  (e: "create", data: AIProviderCreate): void;
  (e: "update", id: string, data: AIProviderUpdate): void;
}>();

const dialog = defineModel<boolean>({ default: false });

const i18n = useI18n();
const { loading, getOne, testOne, testSavedOne, listModels, listChatGPTLoginModels } = useAIProviders();
const init = ref(false);

const form = ref();
const signIn = ref<InstanceType<typeof GroupChatGPTSignIn> | null>(null);
const advancedPanel = ref<string | undefined>(undefined);

const isEdit = computed(() => !!props.providerId);

const providerOptions = computed(() => [
  {
    value: "chatgpt" as AIProviderType,
    title: i18n.t("group.ai-provider-settings.provider-type-chatgpt"),
    description: i18n.t("group.ai-provider-settings.provider-type-chatgpt-description"),
    recommended: true,
  },
  {
    value: "openai" as AIProviderType,
    title: i18n.t("group.ai-provider-settings.provider-type-api-key"),
    description: i18n.t("group.ai-provider-settings.provider-type-api-key-description"),
    recommended: false,
  },
]);

/** What a new provider is called until someone renames it */
const DEFAULT_NAMES: Record<AIProviderType, string> = { chatgpt: "ChatGPT", openai: "OpenAI" };

const defaultForm = (providerType: AIProviderType = props.initialType) => ({
  providerType,
  name: DEFAULT_NAMES[providerType],
  model: "",
  apiKey: "",
  baseUrl: "",
  timeout: 300,
  reasoningEffort: null as string | null,
  requestHeaders: {} as Record<string, string>,
  requestParams: {} as Record<string, string>,
});

const formData = reactive(defaultForm());
const isChatGPT = computed(() => formData.providerType === "chatgpt");

const testing = ref(false);
const testResult = ref<AIProviderTestResult | null>(null);

// ChatGPT sign-in. `savedAccount` is the account an existing provider is already signed in to
// (undefined if it has none); `login` is a sign-in started in this dialog, which replaces it on save.
const savedAccount = ref<string | null | undefined>(undefined);
const login = ref<ChatGPTLoginOut | null>(null);
const loginConnected = computed(() => login.value?.state === "connected");

// The models a ChatGPT provider can pick from: its new sign-in's, or else the saved provider's. Listed only once
// Advanced is opened, since listing them starts Codex on the server.
const { catalogs, loading: catalogLoading, load: loadCatalog } = useAIModelCatalogs(async (key) => {
  const [kind, id] = key.split(":", 2) as [string, string];
  const { data } = kind === "login" ? await listChatGPTLoginModels(id) : await listModels(id);
  return data;
});
const catalogKey = computed(() => {
  if (!isChatGPT.value) return null;
  if (loginConnected.value && login.value) return `login:${login.value.id}`;
  return isEdit.value && props.providerId && savedAccount.value !== undefined ? `provider:${props.providerId}` : null;
});
watch([advancedPanel, catalogKey], ([panel, key]) => {
  if (panel === "advanced" && key) void loadCatalog(key);
});

/** The model field holds "" for "the plan's default"; the picker uses null for it */
const chatgptModel = computed({
  get: () => formData.model || null,
  set: (value: string | null | undefined) => { formData.model = value ?? ""; },
});

function chooseType(providerType: AIProviderType) {
  if (formData.providerType === providerType) return;
  // Keep a name someone typed; swap one that's still the other kind's default
  if (!formData.name.trim() || formData.name === DEFAULT_NAMES[formData.providerType]) {
    formData.name = DEFAULT_NAMES[providerType];
  }
  formData.providerType = providerType;
  formData.model = "";
  // Levels differ between the two kinds, so one chosen for the other doesn't carry over
  formData.reasoningEffort = null;
}

async function onConnected() {
  if (!formData.name.trim()) formData.name = DEFAULT_NAMES.chatgpt;
  // Check the new sign-in works now, rather than leaving it to the button
  await handleTest();
}

const submitDisabled = computed(() => {
  if (!formData.name?.trim()) return true;
  if (isChatGPT.value) return login.value?.state === "waiting" || (!isEdit.value && !loginConnected.value);
  return !formData.model?.trim() || (!isEdit.value && !formData.apiKey?.trim());
});

const testDisabled = computed(() => {
  if (isChatGPT.value) return !formData.name?.trim() || !(loginConnected.value || (isEdit.value && savedAccount.value !== undefined));
  return submitDisabled.value;
});

const connectionMessage = computed(() => {
  const result = testResult.value;
  if (!result) return "";
  if (!result.success) return result.message || i18n.t("group.ai-provider-settings.test-connection-failed");
  // Capability info rather than a second pass/fail check: a text-only provider is a valid setup,
  // it just can't be the image provider
  return result.supportsImages
    ? i18n.t("group.ai-provider-settings.test-connection-succeeded-images")
    : i18n.t("group.ai-provider-settings.test-connection-succeeded-text-only");
});

// Fetch existing provider when editing; reset form for create mode
watch(
  () => [dialog.value, props.providerId] as const,
  async ([open, id]) => {
    if (!open) return;
    testResult.value = null;
    if (!id) {
      resetForm();
      init.value = true;
      return;
    }
    init.value = false;
    const { data } = await getOne(id);
    init.value = true;
    if (data) {
      formData.providerType = data.providerType ?? "openai";
      formData.name = data.name;
      formData.model = data.model ?? "";
      formData.apiKey = "";
      formData.baseUrl = data.baseUrl ?? "";
      formData.timeout = data.timeout ?? 300;
      formData.reasoningEffort = data.reasoningEffort ?? null;
      formData.requestHeaders = { ...(data.requestHeaders ?? {}) };
      formData.requestParams = { ...(data.requestParams ?? {}) };
      savedAccount.value = formData.providerType === "chatgpt" ? data.chatgptAccount : undefined;
      // Open Advanced when something in it has been set, so it isn't hidden
      const customized = (isChatGPT.value && formData.model) || formData.reasoningEffort || formData.timeout !== 300
        || Object.keys(formData.requestHeaders).length || Object.keys(formData.requestParams).length;
      advancedPanel.value = customized ? "advanced" : undefined;
    }
  },
  { immediate: true },
);

watch(() => formData.providerType, () => {
  testResult.value = null;
});

/** The form's current values, as sent to create, update, and test */
function buildPayload(): AIProviderPayload {
  if (isChatGPT.value) {
    return {
      providerType: "chatgpt",
      name: formData.name.trim(),
      model: formData.model.trim(),
      timeout: formData.timeout,
      reasoningEffort: formData.reasoningEffort,
      ...(loginConnected.value && login.value ? { chatgptLoginId: login.value.id } : {}),
    };
  }

  return {
    providerType: "openai",
    name: formData.name.trim(),
    model: formData.model.trim(),
    baseUrl: formData.baseUrl.trim() || null,
    timeout: formData.timeout,
    reasoningEffort: formData.reasoningEffort,
    requestHeaders: Object.keys(formData.requestHeaders).length ? formData.requestHeaders : undefined,
    requestParams: Object.keys(formData.requestParams).length ? formData.requestParams : undefined,
    // Left out when blank, which on edit means "keep the existing key"
    ...(formData.apiKey ? { apiKey: formData.apiKey } : {}),
  };
}

function handleSubmit() {
  if (submitDisabled.value) return;

  const payload = buildPayload();
  if (isEdit.value && props.providerId) {
    emit("update", props.providerId, payload);
  }
  else {
    emit("create", payload);
  }

  // The sign-in now belongs to the provider being saved, so don't cancel it on close
  signIn.value?.release();
}

function resetForm() {
  void signIn.value?.cancel();
  login.value = null;
  Object.assign(formData, defaultForm());
  // resetValidation rather than reset: reset() would clear every field, provider type included
  form.value?.resetValidation();
  advancedPanel.value = undefined;
  testResult.value = null;
  savedAccount.value = undefined;
}

async function handleTest() {
  testing.value = true;
  testResult.value = null;
  try {
    let data: AIProviderTestResult | null;
    if (isEdit.value && props.providerId) {
      // Test the form's current values, not what's saved: the user may have just changed the
      // model or base URL. A blank API key keeps the saved one, and a ChatGPT provider is tested
      // with its saved sign-in unless there's a new one.
      ({ data } = await testSavedOne(props.providerId, buildPayload()));
    }
    else {
      ({ data } = await testOne(buildPayload()));
    }
    testResult.value = data;
  }
  finally {
    testing.value = false;
  }
}
</script>

<style scoped>
.ai-provider-dialog {
  padding-top: 8px;
}

.ai-provider-dialog__label {
  margin: 0 0 10px;
  padding: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.ai-provider-dialog__intro {
  margin: 0 0 18px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

.ai-provider-types {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 0 0 18px;
  padding: 0;
  border: 0;
}

.ai-provider-type {
  appearance: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.ai-provider-type--active {
  border-color: rgb(var(--v-theme-on-background));
  box-shadow: inset 0 0 0 1px rgb(var(--v-theme-on-background));
}

.ai-provider-type:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.ai-provider-type__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 0.9375rem;
  font-weight: 600;
  line-height: 1.3;
}

.ai-provider-type__badge {
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(var(--v-theme-sage), 0.15);
  color: rgb(var(--v-theme-sage));
  font-size: 0.6875rem;
  font-weight: 700;
}

.ai-provider-type__text {
  font-size: 0.8125rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.ai-provider-dialog__advanced {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
}

.ai-provider-dialog__advanced :deep(.v-expansion-panel) {
  background: transparent;
}

.ai-provider-dialog__testing {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
  font-size: 0.875rem;
}

@media (max-width: 599px) {
  .ai-provider-types {
    grid-template-columns: 1fr;
  }
}
</style>
