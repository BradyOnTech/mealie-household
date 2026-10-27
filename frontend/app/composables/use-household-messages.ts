import { createEventHook, createSharedComposable, useDocumentVisibility, useEventListener, useIntervalFn } from "@vueuse/core";
import { useUserApi } from "~/composables/api";
import { groceryError } from "~/composables/groceries/grocery-utils";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import type { HouseholdMessageOut } from "~/lib/api/types/messages";

/** How often the open conversation checks for new messages, and how often the rest of the app checks the count */
const CONVERSATION_POLL = 5_000;
const UNREAD_POLL = 60_000;
const PAGE_SIZE = 50;

/** What the service worker tells open windows; see service-worker/sw.ts */
type ServiceWorkerNotice
  = | { type: "household-message" }
    | { type: "open"; url: string };

const messageArrived = createEventHook();

type BadgingNavigator = Navigator & {
  setAppBadge?: (count?: number) => Promise<void>;
  clearAppBadge?: () => Promise<void>;
};

/** The number on the installed app's icon */
function setAppBadge(count: number) {
  if (!import.meta.client) return;
  const nav = navigator as BadgingNavigator;
  const result = count > 0 ? nav.setAppBadge?.(count) : nav.clearAppBadge?.();
  result?.catch(() => { /* not allowed here, e.g. in a browser tab */ });
}

/** How many messages from others the user hasn't read, shared by the navigation and the Messages page */
export const useHouseholdUnread = createSharedComposable(() => {
  const api = useUserApi();
  const unread = ref(0);

  function set(count: number) {
    unread.value = count;
    setAppBadge(count);
  }

  async function refresh() {
    const { data } = await api.messages.unread();
    if (data) set(data.unread ?? 0);
  }

  return { unread, set, refresh };
});

/**
 * Keeps the unread count current while the app is open, and acts on what the service worker relays:
 * a push arriving (check now rather than on the next poll) and a notification tapped (go to its page).
 * The layout calls this once.
 */
export function useHouseholdMessageWatcher() {
  const router = useRouter();
  const { isOwnGroup } = useLoggedInState();
  const visibility = useDocumentVisibility();
  const { refresh } = useHouseholdUnread();

  const check = () => {
    if (isOwnGroup.value && visibility.value === "visible") void refresh();
  };

  if (import.meta.client && "serviceWorker" in navigator) {
    useEventListener(navigator.serviceWorker, "message", (event: MessageEvent) => {
      const notice = event.data as ServiceWorkerNotice | undefined;
      if (notice?.type === "household-message") {
        void messageArrived.trigger();
        check();
      }
      else if (notice?.type === "open" && notice.url.startsWith("/")) {
        void router.push(notice.url);
      }
    });
  }

  useIntervalFn(check, UNREAD_POLL);
  watch([isOwnGroup, visibility], check, { immediate: true });
}

/** The household's conversation, as the Messages page shows it */
export function useHouseholdConversation() {
  const api = useUserApi();
  const unread = useHouseholdUnread();
  const visibility = useDocumentVisibility();

  const messages = ref<HouseholdMessageOut[]>([]);
  const hasOlder = ref(false);
  const loading = ref(true);
  const loadingOlder = ref(false);
  const sending = ref(false);
  const error = ref("");

  const newest = computed(() => messages.value.at(-1));

  function merge(incoming: HouseholdMessageOut[]) {
    const known = new Set(messages.value.map(message => message.id));
    const added = incoming.filter(message => !known.has(message.id));
    if (!added.length) return false;
    messages.value = [...messages.value, ...added].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    return true;
  }

  async function markRead() {
    if (visibility.value !== "visible" || !newest.value) return;
    const { data } = await api.messages.markRead({ readAt: newest.value.createdAt });
    if (data) unread.set(data.unread ?? 0);
  }

  /** The latest page, replacing what's shown (which also drops messages deleted elsewhere) */
  async function load() {
    const { data, error: failure } = await api.messages.list({ limit: PAGE_SIZE });
    loading.value = false;
    if (!data) {
      error.value = groceryError(failure);
      return;
    }
    error.value = "";
    // Keep older pages the user already scrolled back through
    const first = data.items[0];
    const older = first ? messages.value.filter(message => message.createdAt < first.createdAt) : [];
    messages.value = [...older, ...data.items];
    if (!older.length) hasOlder.value = !!data.hasOlder;
    await markRead();
  }

  async function poll() {
    if (!newest.value) return await load();
    const { data } = await api.messages.list({ after: newest.value.createdAt, limit: PAGE_SIZE });
    if (data && merge(data.items)) await markRead();
  }

  async function loadOlder() {
    const oldest = messages.value[0];
    if (!oldest || loadingOlder.value) return;
    loadingOlder.value = true;
    const { data } = await api.messages.list({ before: oldest.createdAt, limit: PAGE_SIZE });
    loadingOlder.value = false;
    if (!data) return;
    messages.value = [...data.items, ...messages.value];
    hasOlder.value = !!data.hasOlder;
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending.value) return false;
    sending.value = true;
    error.value = "";
    const { data, error: failure } = await api.messages.send({ text: trimmed });
    sending.value = false;
    if (!data) {
      error.value = groceryError(failure);
      return false;
    }
    merge([data]);
    return true;
  }

  async function remove(id: string) {
    const { response, error: failure } = await api.messages.remove(id);
    if (!response) {
      error.value = groceryError(failure);
      return;
    }
    messages.value = messages.value.filter(message => message.id !== id);
  }

  useIntervalFn(() => {
    if (visibility.value === "visible" && !sending.value) void poll();
  }, CONVERSATION_POLL);
  messageArrived.on(() => void poll());
  watch(visibility, (value) => {
    if (value === "visible") void load();
  });
  onMounted(load);

  return { messages, hasOlder, loading, loadingOlder, sending, error, load, poll, loadOlder, send, remove };
}
