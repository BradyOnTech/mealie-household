<template>
  <div class="chatgpt-sign-in">
    <!-- Signed in, by this dialog or already on the saved provider -->
    <div v-if="signedIn" class="chatgpt-sign-in__done" role="status">
      <v-icon :icon="$globals.icons.checkboxMarkedCircle" color="sage" size="22" />
      <div class="chatgpt-sign-in__done-text">
        <strong>{{ signedInAccount
          ? $t('group.ai-provider-settings.chatgpt-signed-in-as', [signedInAccount])
          : $t('group.ai-provider-settings.chatgpt-signed-in') }}</strong>
        <span v-if="loginConnected">{{ $t('group.ai-provider-settings.chatgpt-signed-in-detail') }}</span>
      </div>
      <v-btn variant="text" size="small" :loading="starting" @click="start">
        {{ $t('group.ai-provider-settings.chatgpt-use-different-account') }}
      </v-btn>
    </div>

    <template v-else>
      <ol class="chatgpt-steps">
        <!-- 1. The account setting OpenAI checks before it accepts a code -->
        <li class="chatgpt-step">
          <span class="chatgpt-step__number" aria-hidden="true">1</span>
          <div class="chatgpt-step__body">
            <h3 class="chatgpt-step__title">
              {{ $t('group.ai-provider-settings.chatgpt-step-allow') }}
            </h3>
            <p class="chatgpt-step__text">
              {{ $t('group.ai-provider-settings.chatgpt-step-allow-detail') }}
            </p>
            <a :href="CHATGPT_SECURITY_URL" target="_blank" rel="noopener noreferrer" class="chatgpt-step__link">
              {{ $t('group.ai-provider-settings.chatgpt-open-security-settings') }}
              <v-icon :icon="$globals.icons.openInNew" size="14" />
            </a>
          </div>
        </li>

        <!-- 2. A code from Codex, and OpenAI's page to enter it on -->
        <li class="chatgpt-step" :class="{ 'chatgpt-step--active': !loginConnected, 'chatgpt-step--done': loginConnected }">
          <span class="chatgpt-step__number" aria-hidden="true">2</span>
          <div class="chatgpt-step__body">
            <h3 class="chatgpt-step__title">
              {{ $t('group.ai-provider-settings.chatgpt-step-code') }}
            </h3>

            <template v-if="waiting && login">
              <p class="chatgpt-step__text">
                {{ $t('group.ai-provider-settings.chatgpt-step-code-detail') }}
              </p>
              <div class="chatgpt-code">
                <span class="chatgpt-code__value" :aria-label="$t('group.ai-provider-settings.chatgpt-code')">{{ login.userCode }}</span>
                <v-btn
                  variant="text"
                  size="small"
                  :prepend-icon="copied ? $globals.icons.check : $globals.icons.contentCopy"
                  @click="copyCode"
                >
                  {{ copied ? $t('group.ai-provider-settings.chatgpt-copied') : $t('general.copy') }}
                </v-btn>
              </div>
              <!-- A real link, so a phone opens it from the tap; the click copies the code on the way -->
              <v-btn
                :href="login.verificationUrl ?? undefined"
                target="_blank"
                rel="noopener noreferrer"
                color="primary"
                variant="flat"
                block
                :append-icon="$globals.icons.openInNew"
                @click="copyCode"
              >
                {{ $t('group.ai-provider-settings.chatgpt-copy-and-open') }}
              </v-btn>
              <p class="chatgpt-step__hint">
                {{ $t('group.ai-provider-settings.chatgpt-step-approve-detail') }}
              </p>
            </template>

            <template v-else>
              <p class="chatgpt-step__text">
                {{ $t('group.ai-provider-settings.chatgpt-step-code-start') }}
              </p>
              <v-btn
                color="primary"
                variant="flat"
                :loading="starting"
                :prepend-icon="$globals.icons.user"
                @click="start"
              >
                {{ login ? $t('group.ai-provider-settings.chatgpt-new-code') : $t('group.ai-provider-settings.chatgpt-get-code') }}
              </v-btn>
            </template>
          </div>
        </li>
      </ol>

      <div v-if="waiting" class="chatgpt-sign-in__status" role="status">
        <v-progress-circular indeterminate size="16" width="2" color="primary" />
        <span>{{ $t('group.ai-provider-settings.chatgpt-waiting') }}</span>
        <span v-if="remaining" class="chatgpt-sign-in__expires">{{ $t('group.ai-provider-settings.chatgpt-code-expires', [remaining]) }}</span>
        <v-btn variant="text" size="small" class="ms-auto" @click="cancel">
          {{ $t('group.ai-provider-settings.chatgpt-cancel') }}
        </v-btn>
      </div>

      <div v-if="failed" class="chatgpt-sign-in__error" role="alert">
        <v-icon :icon="$globals.icons.alertCircle" color="error" size="20" />
        <div>
          <strong>{{ $t('group.ai-provider-settings.chatgpt-sign-in-failed') }}</strong>
          <span>{{ failureMessage }}</span>
        </div>
      </div>
      <p v-if="startError" class="chatgpt-sign-in__error" role="alert">
        {{ startError }}
      </p>

      <v-expansion-panels v-model="helpPanel" variant="accordion" class="chatgpt-help">
        <v-expansion-panel value="help" elevation="0">
          <v-expansion-panel-title class="chatgpt-help__title">
            {{ $t('group.ai-provider-settings.chatgpt-help-title') }}
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <dl class="chatgpt-help__list">
              <dt>{{ $t('group.ai-provider-settings.chatgpt-help-went-wrong') }}</dt>
              <dd>{{ $t('group.ai-provider-settings.chatgpt-help-went-wrong-detail') }}</dd>
              <dt>{{ $t('group.ai-provider-settings.chatgpt-help-workspace') }}</dt>
              <dd>{{ $t('group.ai-provider-settings.chatgpt-help-workspace-detail') }}</dd>
              <dt>{{ $t('group.ai-provider-settings.chatgpt-help-expired') }}</dt>
              <dd>{{ $t('group.ai-provider-settings.chatgpt-help-expired-detail') }}</dd>
              <dt>{{ $t('group.ai-provider-settings.chatgpt-help-stuck') }}</dt>
              <dd>{{ $t('group.ai-provider-settings.chatgpt-help-stuck-detail') }}</dd>
            </dl>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useClipboard, useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { useAIProviders } from "~/composables/use-ai-providers";
import { groceryError } from "~/composables/groceries/grocery-utils";
import type { ChatGPTLoginOut } from "~/lib/api/types/group";

/**
 * Signing in to a ChatGPT account with a device code, as numbered steps. OpenAI only accepts codes once the
 * account allows it, and its page doesn't tell Mealie when it refuses one, so the steps lead with that setting
 * and the help covers what OpenAI's page might say.
 */
const props = withDefaults(defineProps<{
  /** The account a saved provider is already signed in to: undefined if none, null if its email is unknown */
  savedAccount?: string | null;
}>(), {
  savedAccount: undefined,
});

const emit = defineEmits<{
  (e: "connected", login: ChatGPTLoginOut): void;
}>();

/** The sign-in started here; it replaces the saved one when the provider is saved */
const login = defineModel<ChatGPTLoginOut | null>("login", { default: null });

const CHATGPT_SECURITY_URL = "https://chatgpt.com/#settings/Security";
/** How long Codex keeps a code (LOGIN_TIMEOUT on the server) */
const CODE_LIFETIME = 15 * 60 * 1000;

const i18n = useI18n();
const { startChatGPTLogin, getChatGPTLogin, cancelChatGPTLogin } = useAIProviders();
const { copy, copied } = useClipboard({ copiedDuring: 2000, legacy: true });
const visibility = useDocumentVisibility();

const starting = ref(false);
const startError = ref("");
const helpPanel = ref<string | undefined>(undefined);
const expiresAt = ref(0);
const now = ref(Date.now());

const waiting = computed(() => login.value?.state === "waiting");
const loginConnected = computed(() => login.value?.state === "connected");
const failed = computed(() => login.value?.state === "failed" || login.value?.state === "expired");
const signedIn = computed(() => loginConnected.value || (!login.value && props.savedAccount !== undefined));
const signedInAccount = computed(() => (loginConnected.value ? login.value?.account : props.savedAccount) ?? null);

const failureMessage = computed(() => {
  if (login.value?.state === "expired") return i18n.t("group.ai-provider-settings.chatgpt-code-expired");
  // The server's errors come from Codex; whatever it says, the likeliest fix is the account setting
  return i18n.t("group.ai-provider-settings.chatgpt-sign-in-failed-detail");
});

const remaining = computed(() => {
  const left = Math.max(0, expiresAt.value - now.value);
  if (!expiresAt.value || !left) return "";
  const minutes = Math.floor(left / 60000);
  const seconds = Math.floor((left % 60000) / 1000);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
});

const { pause: stopPolling, resume: startPolling } = useIntervalFn(poll, 3000, { immediate: false });
const { pause: stopClock, resume: startClock } = useIntervalFn(() => { now.value = Date.now(); }, 1000, { immediate: false });

async function start() {
  starting.value = true;
  startError.value = "";
  try {
    await cancel();
    const { data, error } = await startChatGPTLogin();
    if (!data) {
      startError.value = groceryError(error);
      return;
    }
    login.value = data;
    if (data.state === "waiting") {
      expiresAt.value = Date.now() + CODE_LIFETIME;
      now.value = Date.now();
      startPolling();
      startClock();
    }
  }
  finally {
    starting.value = false;
  }
}

async function poll() {
  if (!login.value) return finish();
  const { data } = await getChatGPTLogin(login.value.id);
  // A new sign-in may have started, or this one been cancelled, while that was in flight
  if (!data || data.id !== login.value?.id) return;
  login.value = data;
  if (data.state === "waiting") return;
  finish();
  if (data.state === "connected") emit("connected", data);
  // A failure usually means OpenAI turned the code down, so open the help
  else helpPanel.value = "help";
}

function finish() {
  stopPolling();
  stopClock();
}

async function cancel() {
  finish();
  const current = login.value;
  login.value = null;
  if (current?.state === "waiting") await cancelChatGPTLogin(current.id);
}

/** Stop watching a sign-in that's been saved to a provider, without cancelling it */
function release() {
  finish();
  login.value = null;
}

function copyCode() {
  // Not awaited: the copy has to start within the tap, and the link opens either way
  if (login.value?.userCode) void copy(login.value.userCode);
}

// Coming back from OpenAI's page, check right away rather than on the next tick
watch(visibility, (state) => {
  if (state === "visible" && waiting.value) void poll();
});

onBeforeUnmount(() => {
  void cancel();
});

defineExpose({ cancel, release });
</script>

<style scoped>
.chatgpt-sign-in {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chatgpt-steps {
  display: flex;
  flex-direction: column;
  gap: 18px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.chatgpt-step {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 12px;
}

.chatgpt-step__number {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 50%;
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-ink-muted));
}

.chatgpt-step--active .chatgpt-step__number {
  border-color: rgb(var(--v-theme-on-background));
  background: rgb(var(--v-theme-on-background));
  color: rgb(var(--v-theme-background));
}

.chatgpt-step--done .chatgpt-step__number {
  border-color: rgb(var(--v-theme-sage));
  background: rgb(var(--v-theme-sage));
  color: rgb(var(--v-theme-on-primary));
}

.chatgpt-step__title {
  margin: 3px 0 4px;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.3;
}

.chatgpt-step__text,
.chatgpt-step__hint {
  margin: 0 0 10px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

.chatgpt-step__hint {
  margin: 10px 0 0;
}

.chatgpt-step__link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-tomato));
  text-underline-offset: 3px;
}

.chatgpt-code {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding: 10px 6px 10px 16px;
  border: 1px dashed rgb(var(--v-theme-rule));
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
}

.chatgpt-code__value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  user-select: all;
}

.chatgpt-sign-in__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  font-size: 0.875rem;
}

.chatgpt-sign-in__expires {
  color: rgb(var(--v-theme-ink-muted));
}

.chatgpt-sign-in__done,
.chatgpt-sign-in__error {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 0;
  padding: 12px 14px;
  border-radius: 10px;
  font-size: 0.875rem;
  line-height: 1.45;
}

.chatgpt-sign-in__done {
  align-items: center;
  flex-wrap: wrap;
  background: rgba(var(--v-theme-sage), 0.12);
}

.chatgpt-sign-in__done-text {
  display: flex;
  flex: 1 1 180px;
  flex-direction: column;
}

.chatgpt-sign-in__error {
  background: rgba(var(--v-theme-error), 0.08);
  color: rgb(var(--v-theme-on-background));
}

.chatgpt-sign-in__error strong {
  display: block;
}

.chatgpt-help {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
}

.chatgpt-help :deep(.v-expansion-panel) {
  background: transparent;
}

.chatgpt-help__title {
  min-height: 44px !important;
  font-size: 0.875rem;
  font-weight: 600;
}

.chatgpt-help__list {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.5;
}

.chatgpt-help__list dt {
  font-weight: 600;
}

.chatgpt-help__list dd {
  margin: 0 0 10px;
  color: rgb(var(--v-theme-ink-muted));
}

.chatgpt-help__list dd:last-child {
  margin-bottom: 0;
}
</style>
