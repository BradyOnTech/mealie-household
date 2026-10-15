<template>
  <BaseDialog
    v-model="dialog"
    :title="isEdit ? $t('group.ai-provider-settings.edit-provider') : $t('group.ai-provider-settings.create-provider')"
    :icon="$globals.icons.robot"
    :loading="loading"
    can-submit
    :submit-icon="isEdit ? $globals.icons.save : $globals.icons.createAlt"
    :submit-text="isEdit ? $t('general.update') : $t('general.create')"
    :submit-disabled="submitDisabled"
    @submit="handleSubmit"
    @close="resetForm"
  >
    <v-card-text v-if="init" style="max-height: 70vh; overflow-y: auto;">
      <v-form ref="form" v-no-autofill>
        <v-select
          v-model="formData.providerType"
          :label="$t('group.ai-provider-settings.provider-type')"
          :items="providerTypes"
          :disabled="isEdit"
          :hint="isChatGPT ? $t('group.ai-provider-settings.chatgpt-description') : undefined"
          :persistent-hint="isChatGPT"
          density="compact"
          variant="outlined"
          class="mb-4"
        />
        <v-text-field
          v-model="formData.name"
          :label="$t('group.ai-provider-settings.provider-name')"
          :rules="[validators.required]"
          density="compact"
          variant="outlined"
          class="mb-4"
        />
        <v-text-field
          v-model="formData.model"
          :label="$t('group.ai-provider-settings.model')"
          :hint="$t(isChatGPT ? 'group.ai-provider-settings.chatgpt-model-description' : 'group.ai-provider-settings.model-description')"
          :rules="isChatGPT ? [] : [validators.required]"
          density="compact"
          variant="outlined"
          class="mb-4"
        />
        <template v-if="!isChatGPT">
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
        <v-number-input
          v-model.number="formData.timeout"
          :label="$t('group.ai-provider-settings.request-timeout-seconds')"
          type="number"
          :min="0"
          hide-details
          density="compact"
          variant="outlined"
          class="mb-4"
        />

        <div v-if="isChatGPT">
          <v-alert
            v-if="login?.state === 'waiting'"
            type="info"
            density="compact"
            variant="tonal"
            class="mb-3"
          >
            <div>{{ $t('group.ai-provider-settings.chatgpt-sign-in-instructions') }}</div>
            <a :href="login.verificationUrl ?? undefined" target="_blank" rel="noopener noreferrer">
              {{ login.verificationUrl }}
            </a>
            <div class="d-flex align-center my-2">
              <code class="text-h6 font-weight-bold" style="letter-spacing: 0.1em;">{{ login.userCode }}</code>
              <AppButtonCopy :copy-text="login.userCode ?? ''" icon class="ms-2" />
            </div>
            <div class="text-caption">
              {{ $t('group.ai-provider-settings.chatgpt-waiting') }}
            </div>
          </v-alert>
          <v-alert
            v-else-if="login?.state === 'failed' || login?.state === 'expired'"
            type="error"
            density="compact"
            variant="tonal"
            class="mb-3"
          >
            {{ login.error || $t('group.ai-provider-settings.chatgpt-sign-in-failed') }}
          </v-alert>
          <v-alert
            v-else-if="signedInAccount !== undefined"
            type="success"
            density="compact"
            variant="tonal"
            class="mb-3"
          >
            {{ signedInAccount
              ? $t('group.ai-provider-settings.chatgpt-signed-in-as', [signedInAccount])
              : $t('group.ai-provider-settings.chatgpt-signed-in') }}
          </v-alert>

          <div class="d-flex align-center flex-wrap ga-2 mb-2">
            <BaseButton
              v-if="login?.state !== 'waiting'"
              :loading="startingLogin"
              :icon="$globals.icons.user"
              :text="signedInAccount !== undefined
                ? $t('group.ai-provider-settings.chatgpt-use-different-account')
                : $t('group.ai-provider-settings.chatgpt-sign-in')"
              @click="startLogin"
            />
            <BaseButton v-else cancel @click="cancelLogin" />
          </div>
          <div class="text-caption text-medium-emphasis">
            {{ $t('group.ai-provider-settings.chatgpt-device-code-help') }}
          </div>
        </div>

        <v-expansion-panels v-else v-model="advancedPanel" variant="accordion">
          <v-expansion-panel>
            <v-expansion-panel-title class="text-subtitle-2" expand-icon="$expand" collapse-icon="$expand">
              {{ $t('search.advanced') }}
            </v-expansion-panel-title>
            <v-expansion-panel-text class="px-0">
              <div class="mb-2 text-subtitle-2">
                {{ $t('group.ai-provider-settings.request-headers') }}
              </div>
              <BaseKeyValueEditor
                v-model="formData.requestHeaders"
                class="mb-4"
              />
              <v-divider class="mb-4" />
              <div class="mb-2 text-subtitle-2">
                {{ $t('group.ai-provider-settings.request-params') }}
              </div>
              <BaseKeyValueEditor
                v-model="formData.requestParams"
              />
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

        <v-alert
          v-if="testResult"
          :type="testResult.success ? 'success' : 'error'"
          density="compact"
          variant="tonal"
          class="mt-4"
        >
          {{ connectionMessage }}{{ imageSupportMessage }}
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
import { useIntervalFn } from "@vueuse/core";
import { useAIProviders } from "~/composables/use-ai-providers";
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
}>(), {
  providerId: undefined,
});

const emit = defineEmits<{
  (e: "create", data: AIProviderCreate): void;
  (e: "update", id: string, data: AIProviderUpdate): void;
}>();

const dialog = defineModel<boolean>({ default: false });

const { $globals } = useNuxtApp();
const i18n = useI18n();
const {
  loading,
  getOne,
  testOne,
  testSavedOne,
  startChatGPTLogin,
  getChatGPTLogin,
  cancelChatGPTLogin,
} = useAIProviders();
const init = ref(false);

const form = ref();
const advancedPanel = ref<number | undefined>(undefined);

const isEdit = computed(() => !!props.providerId);

const providerTypes = computed(() => [
  { title: i18n.t("group.ai-provider-settings.provider-type-api-key"), value: "openai" },
  { title: i18n.t("group.ai-provider-settings.provider-type-chatgpt"), value: "chatgpt" },
]);

const defaultForm = () => ({
  providerType: "openai" as AIProviderType,
  name: "",
  model: "",
  apiKey: "",
  baseUrl: "",
  timeout: 300,
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
const startingLogin = ref(false);
const loginConnected = computed(() => login.value?.state === "connected");

/** The account this provider will be signed in to once saved: undefined if none, null if the email is unknown */
const signedInAccount = computed<string | null | undefined>(() => {
  if (loginConnected.value) return login.value?.account ?? null;
  return savedAccount.value;
});

const { pause: stopPolling, resume: startPolling } = useIntervalFn(pollLogin, 3000, { immediate: false });

async function startLogin() {
  startingLogin.value = true;
  testResult.value = null;
  try {
    const { data } = await startChatGPTLogin();
    login.value = data;
    if (data?.state === "waiting") startPolling();
  }
  finally {
    startingLogin.value = false;
  }
}

async function pollLogin() {
  if (!login.value) return stopPolling();
  const { data } = await getChatGPTLogin(login.value.id);
  // The dialog may have been closed or a new sign-in started while this was in flight
  if (!data || data.id !== login.value?.id) return;
  login.value = data;
  if (data.state !== "waiting") stopPolling();
}

async function cancelLogin() {
  stopPolling();
  const current = login.value;
  login.value = null;
  if (current?.state === "waiting") await cancelChatGPTLogin(current.id);
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
  if (result.success) return i18n.t("group.ai-provider-settings.test-connection-succeeded");
  return result.message || i18n.t("group.ai-provider-settings.test-connection-failed");
});

// Capability info rather than a second pass/fail check - a text-only provider is a valid setup,
// it just can't be used as the image provider. Appended to the connection message above.
const imageSupportMessage = computed(() => {
  const result = testResult.value;
  if (!result?.success) return "";
  return result.supportsImages
    ? ` — ${i18n.t("group.ai-provider-settings.supports-images")}`
    : ` — ${i18n.t("group.ai-provider-settings.text-only-provider")}`;
});

// Fetch existing provider when editing; reset form for create mode
watch(
  () => [dialog.value, props.providerId] as const,
  async ([open, id]) => {
    if (!open) return;
    testResult.value = null;
    if (!id) {
      // Create mode — just show the empty form
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
      formData.requestHeaders = { ...(data.requestHeaders ?? {}) };
      formData.requestParams = { ...(data.requestParams ?? {}) };
      savedAccount.value = formData.providerType === "chatgpt" ? data.chatgptAccount : undefined;
    }
  },
  { immediate: true },
);

watch(() => formData.providerType, () => {
  testResult.value = null;
});

// Closing the dialog any way other than submitting goes through resetForm, which cancels a
// sign-in still in progress. This covers the dialog being torn down while one is running.
onBeforeUnmount(() => {
  void cancelLogin();
});

/** The form's current values, as sent to create, update, and test */
function buildPayload(): AIProviderPayload {
  if (isChatGPT.value) {
    return {
      providerType: "chatgpt",
      name: formData.name,
      model: formData.model.trim(),
      timeout: formData.timeout,
      ...(loginConnected.value && login.value ? { chatgptLoginId: login.value.id } : {}),
    };
  }

  return {
    providerType: "openai",
    name: formData.name,
    model: formData.model,
    baseUrl: formData.baseUrl || null,
    timeout: formData.timeout,
    requestHeaders: Object.keys(formData.requestHeaders).length ? formData.requestHeaders : undefined,
    requestParams: Object.keys(formData.requestParams).length ? formData.requestParams : undefined,
    // Left out when blank, which on edit means "keep the existing key"
    ...(formData.apiKey ? { apiKey: formData.apiKey } : {}),
  };
}

function handleSubmit() {
  // Required field guard (button is also disabled, but keep as a safeguard)
  if (submitDisabled.value) return;

  const payload = buildPayload();
  if (isEdit.value && props.providerId) {
    emit("update", props.providerId, payload);
  }
  else {
    emit("create", payload);
  }

  // The sign-in now belongs to the provider being saved, so don't cancel it on close
  stopPolling();
  login.value = null;
}

function resetForm() {
  void cancelLogin();
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
      // Test the form's CURRENT values, not what's saved in the DB — the user may have just
      // changed the model/base_url. If they left the API key blank (meaning "keep the existing
      // one"), the backend falls back to the saved key since we don't have that value here.
      // Likewise a ChatGPT provider is tested with its saved sign-in unless there's a new one.
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
