<template>
  <div class="messages-page paper-container">
    <header class="messages-head">
      <span class="paper-kicker">{{ $t("messages.kicker") }}</span>
      <h1 class="messages-head__title paper-headline">
        {{ $t("messages.title") }}
      </h1>
      <p class="messages-head__dek">
        {{ $t("messages.dek") }}
      </p>
    </header>

    <div class="messages-grid">
      <section class="messages-chat" :aria-label="$t('messages.conversation')">
        <HouseholdMessageNotifications v-if="pushNeedsAttention" class="messages-inline-notice" />

        <p v-if="loading" class="messages-muted">
          {{ $t("messages.loading") }}
        </p>
        <div v-else-if="!messages.length" class="messages-empty">
          <p class="messages-empty__lead">
            {{ $t("messages.empty") }}
          </p>
          <p class="messages-muted">
            {{ $t("messages.empty-detail") }}
          </p>
        </div>

        <div v-if="hasOlder" class="messages-older">
          <v-btn variant="text" size="small" :loading="loadingOlder" @click="showOlder">
            {{ $t("messages.load-older") }}
          </v-btn>
        </div>

        <ol class="messages-list" aria-live="polite">
          <template v-for="row in rows" :key="row.key">
            <li v-if="row.kind === 'day'" class="messages-day">
              <span>{{ row.label }}</span>
            </li>
            <li
              v-else
              class="message"
              :class="{ 'message--mine': row.mine, 'message--first': row.first }"
            >
              <span v-if="row.first && !row.mine" class="message__sender">{{ row.sender }}</span>
              <button
                v-if="row.mine"
                type="button"
                class="message__bubble"
                :aria-expanded="selected === row.message.id"
                @click="toggle(row.message.id)"
              >
                <span class="d-sr-only">{{ $t("messages.you") }}:</span>
                <span class="message__text">{{ row.message.text }}</span>
              </button>
              <div v-else class="message__bubble">
                <span class="d-sr-only">{{ row.sender }}:</span>
                <span class="message__text">{{ row.message.text }}</span>
              </div>
              <div v-if="row.last || selected === row.message.id" class="message__meta">
                <time :datetime="row.message.createdAt">{{ row.time }}</time>
                <button
                  v-if="row.mine && selected === row.message.id"
                  type="button"
                  class="message__delete"
                  @click="remove(row.message.id)"
                >
                  {{ $t("messages.delete") }}
                </button>
              </div>
            </li>
          </template>
        </ol>

        <p v-if="error" class="messages-error" role="alert">
          {{ error }}
        </p>

        <form class="messages-composer" @submit.prevent="submit">
          <v-textarea
            v-model="draft"
            :placeholder="$t('messages.placeholder')"
            :aria-label="$t('messages.placeholder')"
            rows="1"
            max-rows="5"
            auto-grow
            hide-details
            density="comfortable"
            enterkeyhint="send"
            maxlength="2000"
            class="messages-composer__input"
            @keydown.enter.exact.prevent="submit"
          />
          <!-- mousedown.prevent keeps the keyboard up on phones, so a reply can follow -->
          <v-btn
            type="submit"
            icon
            color="primary"
            variant="flat"
            :disabled="!draft.trim() || sending"
            :loading="sending"
            :aria-label="$t('messages.send')"
            @mousedown.prevent
          >
            <v-icon :icon="$globals.icons.send" />
          </v-btn>
        </form>
      </section>

      <aside class="messages-aside">
        <HouseholdMessageNotifications />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import HouseholdMessageNotifications from "~/components/Domain/Household/HouseholdMessageNotifications.vue";
import { useHouseholdConversation } from "~/composables/use-household-messages";
import { useWebPush } from "~/composables/use-web-push";
import type { HouseholdMessageOut } from "~/lib/api/types/messages";

definePageMeta({ middleware: ["household-only"] });

const i18n = useI18n();
const auth = useMealieAuth();
useSeoMeta({ title: i18n.t("messages.title") });

const { messages, hasOlder, loading, loadingOlder, sending, error, loadOlder, send, remove: removeMessage } = useHouseholdConversation();
const { state: pushState } = useWebPush();

/** On phones the side panel is hidden, so the conversation asks about notifications itself */
const pushNeedsAttention = computed(() => ["off", "needs-install", "denied"].includes(pushState.value));

/** A new sender, or a pause this long, starts a new run of messages */
const RUN_GAP = 10 * 60 * 1000;

type Row
  = | { kind: "day"; key: string; label: string }
    | {
      kind: "message";
      key: string;
      message: HouseholdMessageOut;
      mine: boolean;
      sender: string;
      time: string;
      first: boolean;
      last: boolean;
    };

const timeFormat = computed(() => new Intl.DateTimeFormat(i18n.locale.value, { hour: "numeric", minute: "2-digit" }));

function dayKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function dayLabel(date: Date) {
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  if (dayKey(date) === dayKey(today)) return i18n.t("messages.today");
  if (dayKey(date) === dayKey(yesterday)) return i18n.t("messages.yesterday");
  return new Intl.DateTimeFormat(i18n.locale.value, {
    weekday: "long",
    month: "long",
    day: "numeric",
    ...(date.getFullYear() === today.getFullYear() ? {} : { year: "numeric" }),
  }).format(date);
}

function senderName(message: HouseholdMessageOut) {
  return message.user.fullName || message.user.username || i18n.t("messages.someone");
}

function startsRun(message: HouseholdMessageOut, previous: HouseholdMessageOut | undefined) {
  if (!previous || previous.userId !== message.userId) return true;
  const sameDay = dayKey(new Date(previous.createdAt)) === dayKey(new Date(message.createdAt));
  return !sameDay || Date.parse(message.createdAt) - Date.parse(previous.createdAt) > RUN_GAP;
}

const rows = computed<Row[]>(() => {
  const result: Row[] = [];
  const list = messages.value;
  list.forEach((message, index) => {
    const created = new Date(message.createdAt);
    const previous = list[index - 1];
    const next = list[index + 1];
    if (!previous || dayKey(new Date(previous.createdAt)) !== dayKey(created)) {
      result.push({ kind: "day", key: `day-${dayKey(created)}`, label: dayLabel(created) });
    }
    result.push({
      kind: "message",
      key: message.id,
      message,
      mine: message.userId === auth.user.value?.id,
      sender: senderName(message),
      time: timeFormat.value.format(created),
      first: startsRun(message, previous),
      last: !next || startsRun(next, message),
    });
  });
  return result;
});

const selected = ref<string | null>(null);
function toggle(id: string) {
  selected.value = selected.value === id ? null : id;
}

async function remove(id: string) {
  selected.value = null;
  await removeMessage(id);
}

const draft = ref("");
async function submit() {
  const text = draft.value;
  if (!text.trim() || sending.value) return;
  draft.value = "";
  // Put the text back if it didn't send, so nothing typed is lost
  if (!(await send(text))) draft.value = text;
}

function scrollHeight() {
  return document.documentElement.scrollHeight;
}

function nearBottom() {
  return window.innerHeight + window.scrollY >= scrollHeight() - 160;
}

async function showOlder() {
  // Keep the reader's place while earlier messages go in above
  const before = scrollHeight();
  await loadOlder();
  await nextTick();
  window.scrollBy({ top: scrollHeight() - before });
}

// Follow new messages, unless the reader has scrolled back through older ones
watch(() => messages.value.at(-1)?.id, async (id, previousId) => {
  if (!id) return;
  const newest = messages.value.at(-1);
  const follow = !previousId || nearBottom() || newest?.userId === auth.user.value?.id;
  await nextTick();
  if (follow) window.scrollTo({ top: scrollHeight(), behavior: previousId ? "smooth" : "auto" });
});
</script>

<style scoped>
.messages-page {
  padding-top: 32px;
  padding-bottom: 40px;
}

.messages-head {
  margin-bottom: 22px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
}

.messages-head__title {
  margin: 6px 0 6px;
  font-size: 3rem;
}

.messages-head__dek {
  margin: 0;
  max-width: 34em;
  font-size: 0.9375rem;
  color: rgb(var(--v-theme-ink-muted));
}

.messages-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 48px;
  align-items: start;
}

.messages-aside {
  position: sticky;
  top: 88px;
}

.messages-inline-notice {
  display: none;
  margin-bottom: 20px;
}

.messages-muted {
  margin: 0;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
}

.messages-empty {
  margin: 4px 0 18px;
}

.messages-empty__lead {
  margin: 0 0 4px;
  font-family: var(--paper-serif);
  font-size: 1.25rem;
  font-style: italic;
  color: rgb(var(--v-theme-ink-muted));
}

.messages-older {
  display: flex;
  justify-content: center;
  margin-bottom: 8px;
}

.messages-list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.messages-day {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 18px 0 10px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.messages-day::before,
.messages-day::after {
  content: "";
  flex: 1;
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.message {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  max-width: 80%;
  margin-top: 3px;
}

.message--first {
  margin-top: 12px;
}

.message--mine {
  align-self: flex-end;
  align-items: flex-end;
}

.message__sender {
  margin: 0 0 3px 4px;
  font-size: 0.8125rem;
  font-weight: 600;
  color: rgb(var(--v-theme-ink-muted));
}

.message__bubble {
  appearance: none;
  display: block;
  max-width: 100%;
  padding: 8px 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  text-align: left;
}

.message--mine .message__bubble {
  border-color: transparent;
  background: rgb(var(--v-theme-wash));
  cursor: pointer;
}

.message__bubble:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.message__text {
  display: block;
  font-size: 1rem;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.message__meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 3px 6px 0;
  font-size: 0.75rem;
  color: rgb(var(--v-theme-ink-muted));
}

.message__delete {
  appearance: none;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 600;
  color: rgb(var(--v-theme-error));
  cursor: pointer;
}

.messages-error {
  margin: 14px 0 0;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-error));
}

.messages-composer {
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

.messages-composer__input {
  flex: 1;
}

@media (max-width: 959px) {
  .messages-page {
    padding-top: 22px;
    padding-bottom: 0;
  }

  .messages-head__title {
    font-size: 2.25rem;
  }

  .messages-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 28px;
  }

  .messages-aside {
    display: none;
  }

  .messages-inline-notice {
    display: block;
  }

  .message {
    max-width: 88%;
  }

  .messages-composer {
    padding-bottom: 12px;
  }
}
</style>
