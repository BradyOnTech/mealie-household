<template>
  <div class="assistant-page paper-container">
    <header class="assistant-head">
      <div>
        <span class="paper-kicker">{{ $t("assistant.kicker") }}</span>
        <h1 class="assistant-head__title paper-headline">
          {{ $t("assistant.title") }}
        </h1>
        <p class="assistant-head__dek">
          {{ $t("assistant.dek") }}
        </p>
      </div>
      <v-btn
        v-if="messages.length"
        variant="text"
        :prepend-icon="$globals.icons.refresh"
        :disabled="thinking"
        @click="reset"
      >
        {{ $t("assistant.new-chat") }}
      </v-btn>
    </header>

    <div class="assistant-grid">
      <section class="assistant-chat" :aria-label="$t('assistant.conversation')">
        <div v-if="!aiEnabled" class="assistant-setup paper-box">
          <h2 class="assistant-setup__title">
            {{ $t("assistant.needs-ai") }}
          </h2>
          <p class="assistant-muted">
            {{ $t(canManage ? "assistant.needs-ai-manager" : "assistant.needs-ai-member") }}
          </p>
          <v-btn v-if="canManage" variant="outlined" to="/group" class="mt-3">
            {{ $t("assistant.set-up-ai") }}
          </v-btn>
        </div>

        <template v-else>
          <p v-if="restock.items.value.length" class="assistant-summary">
            {{ $t("assistant.out-of-summary", { items: outOfNames }) }}
            <NuxtLink to="/household/groceries" class="paper-link">
              {{ $t("assistant.open-groceries") }}
            </NuxtLink>
          </p>
          <div v-if="!messages.length" class="assistant-empty">
            <p class="assistant-empty__lead">
              {{ $t("assistant.empty") }}
            </p>
            <div class="assistant-starters">
              <button
                v-for="starter in starters"
                :key="starter"
                type="button"
                class="assistant-starter"
                :disabled="thinking"
                @click="send(starter)"
              >
                {{ starter }}
              </button>
            </div>
          </div>

          <ol class="assistant-messages" aria-live="polite">
            <li
              v-for="(message, index) in messages"
              :key="index"
              class="assistant-message"
              :class="`assistant-message--${message.role}`"
            >
              <span class="d-sr-only">{{ message.role === "user" ? $t("assistant.you-said") : $t("assistant.it-said") }}</span>
              <p v-if="message.role === 'user'" class="assistant-message__text">
                {{ message.content }}
              </p>
              <SafeMarkdown v-else class="assistant-message__text" :source="message.content" />
              <ul v-if="message.actions?.length" class="assistant-actions">
                <li v-for="(action, actionIndex) in message.actions" :key="actionIndex">
                  <v-icon size="15" :icon="$globals.icons.check" />
                  {{ action.summary }}
                </li>
              </ul>
            </li>
            <li v-if="thinking" class="assistant-message assistant-message--assistant assistant-thinking">
              <span /><span /><span />
              <span class="d-sr-only">{{ $t("assistant.thinking") }}</span>
            </li>
          </ol>

          <div v-if="error" class="assistant-error" role="alert">
            <span>{{ error }}</span>
            <button type="button" class="paper-link" :disabled="thinking" @click="retry">
              {{ $t("assistant.try-again") }}
            </button>
          </div>

          <form class="assistant-composer" @submit.prevent="submit">
            <v-textarea
              v-model="draft"
              :placeholder="$t('assistant.placeholder')"
              :aria-label="$t('assistant.placeholder')"
              rows="1"
              max-rows="5"
              auto-grow
              hide-details
              density="comfortable"
              enterkeyhint="send"
              class="assistant-composer__input"
              @keydown.enter.exact.prevent="submit"
            />
            <v-btn
              type="submit"
              icon
              color="primary"
              variant="flat"
              :disabled="!draft.trim() || thinking"
              :aria-label="$t('assistant.send')"
            >
              <v-icon :icon="$globals.icons.send" />
            </v-btn>
          </form>
        </template>
      </section>

      <aside class="assistant-aside">
        <GroceryRestockPanel />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import GroceryRestockPanel from "~/components/Domain/Grocery/GroceryRestockPanel.vue";
import { useGroceryRestock } from "~/composables/groceries/use-grocery-restock";
import { useAssistantChat } from "~/composables/use-assistant-chat";
import { useGroupSelf } from "~/composables/use-groups";

definePageMeta({ middleware: ["household-only"] });

const i18n = useI18n();
const auth = useMealieAuth();
const { group } = useGroupSelf();
useSeoMeta({ title: i18n.t("assistant.title") });

const restock = useGroceryRestock();
const { messages, thinking, error, send, retry, reset } = useAssistantChat((actions) => {
  if (actions.some(action => action.kind === "restock")) void restock.refresh();
});

const aiEnabled = computed(() => !!group.value?.aiProviderSettings?.aiEnabled);
const outOfNames = computed(() =>
  new Intl.ListFormat(i18n.locale.value, { style: "long", type: "conjunction" }).format(restock.items.value.map(item => item.name)),
);
const canManage = computed(() => !!auth.user.value?.canManage);
const starters = computed(() => [
  i18n.t("assistant.starter-out-of"),
  i18n.t("assistant.starter-list"),
  i18n.t("assistant.starter-week"),
  i18n.t("assistant.starter-idea"),
]);

const draft = ref("");

async function submit() {
  const text = draft.value;
  if (!text.trim() || thinking.value) return;
  draft.value = "";
  await send(text);
}

// Keep the newest message in view
watch(() => [messages.value.length, thinking.value], async () => {
  await nextTick();
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
});
</script>

<style scoped>
.assistant-page {
  padding-top: 32px;
  padding-bottom: 40px;
}

.assistant-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px 24px;
  margin-bottom: 22px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
}

.assistant-head__title {
  margin: 6px 0 6px;
  font-size: 3rem;
}

.assistant-head__dek {
  margin: 0;
  max-width: 34em;
  font-size: 0.9375rem;
  color: rgb(var(--v-theme-ink-muted));
}

.assistant-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 48px;
  align-items: start;
}

.assistant-aside {
  position: sticky;
  top: 88px;
}

.assistant-muted {
  margin: 0;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
}

.assistant-setup {
  padding: 22px 24px;
}

.assistant-setup__title {
  margin: 0 0 6px;
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 420;
}

.assistant-empty__lead {
  margin: 4px 0 14px;
  font-family: var(--paper-serif);
  font-size: 1.25rem;
  font-style: italic;
  color: rgb(var(--v-theme-ink-muted));
}

.assistant-starters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.assistant-starter {
  appearance: none;
  padding: 7px 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 999px;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.assistant-starter:hover:not(:disabled) {
  border-color: rgb(var(--v-theme-on-background));
}

.assistant-starter:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.assistant-messages {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.assistant-message {
  max-width: 85%;
}

.assistant-message--user {
  align-self: flex-end;
  padding: 9px 14px;
  border-radius: 14px 14px 4px 14px;
  background: rgb(var(--v-theme-wash));
}

.assistant-message--assistant {
  align-self: flex-start;
  padding: 2px 0;
}

.assistant-message__text {
  margin: 0;
  font-size: 1rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.assistant-message--assistant .assistant-message__text {
  white-space: normal;
}

.assistant-message__text :deep(p) {
  margin: 0 0 8px;
}

.assistant-message__text :deep(p:last-child) {
  margin-bottom: 0;
}

.assistant-actions {
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-sage));
}

.assistant-actions li {
  display: flex;
  align-items: center;
  gap: 5px;
}

.assistant-thinking {
  display: flex;
  gap: 5px;
  padding: 10px 0;
}

.assistant-thinking span:not(.d-sr-only) {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgb(var(--v-theme-ink-muted));
  animation: assistant-pulse 1.2s infinite ease-in-out;
}

.assistant-thinking span:nth-child(2) {
  animation-delay: 0.15s;
}

.assistant-thinking span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes assistant-pulse {
  0%,
  80%,
  100% {
    opacity: 0.25;
  }
  40% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .assistant-thinking span:not(.d-sr-only) {
    animation: none;
    opacity: 0.6;
  }
}

.assistant-error {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  margin-top: 14px;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-error));
}

.assistant-error button {
  appearance: none;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 600;
}

.assistant-summary {
  display: none;
  margin: 0 0 16px;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
}

.assistant-composer {
  position: sticky;
  /* Above the phone tab bar, which v-main reports as its bottom inset */
  bottom: calc(var(--v-layout-bottom, 0px) + env(safe-area-inset-bottom));
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin-top: 22px;
  padding: 12px 0 calc(12px + env(safe-area-inset-bottom));
  border-top: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-background));
}

.assistant-composer__input {
  flex: 1;
}

@media (max-width: 959px) {
  .assistant-page {
    padding-top: 22px;
    padding-bottom: 0;
  }

  .assistant-head__title {
    font-size: 2.25rem;
  }

  .assistant-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 28px;
  }

  .assistant-aside {
    display: none;
  }

  .assistant-summary {
    display: block;
  }

  .assistant-message {
    max-width: 92%;
  }

  .assistant-composer {
    padding-bottom: 12px;
  }
}
</style>
