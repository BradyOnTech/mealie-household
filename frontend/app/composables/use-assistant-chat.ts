import { useLocalStorage } from "@vueuse/core";
import { useUserApi } from "~/composables/api";
import { groceryError } from "~/composables/groceries/grocery-utils";
import type { AssistantAction, AssistantMessage } from "~/lib/api/types/assistant";

export interface AssistantChatEntry {
  role: AssistantMessage["role"];
  content: string;
  actions?: AssistantAction[];
}

/** How many messages are kept on this device, and how many go with each request */
const KEPT = 40;
const SENT = 24;

/**
 * A conversation with the household assistant. It's kept on this device per user, so it survives
 * a reload of the installed app, and the whole recent conversation goes with every message.
 */
export function useAssistantChat(onActions?: (actions: AssistantAction[]) => void) {
  const api = useUserApi();
  const auth = useMealieAuth();
  const storageKey = computed(() => `household-assistant-chat:${auth.user.value?.id ?? "anonymous"}`);
  const messages = useLocalStorage<AssistantChatEntry[]>(storageKey, []);
  const thinking = ref(false);
  const error = ref("");

  async function ask() {
    thinking.value = true;
    error.value = "";
    try {
      const history = messages.value.slice(-SENT).map(({ role, content }) => ({ role, content }));
      // The server wants the conversation to start with the user, and trimming can leave a reply first
      while (history[0]?.role === "assistant") history.shift();
      const [first, ...rest] = history;
      if (!first) return;
      const result = await api.assistant.chat({ messages: [first, ...rest] });
      if (!result.data) throw result.error;
      const actions = result.data.actions ?? [];
      messages.value = [...messages.value, { role: "assistant" as const, content: result.data.reply, actions }].slice(-KEPT);
      if (actions.length) onActions?.(actions);
    }
    catch (cause) {
      error.value = groceryError(cause);
    }
    finally {
      thinking.value = false;
    }
  }

  async function send(text: string) {
    const content = text.trim();
    if (!content || thinking.value) return false;
    messages.value = [...messages.value, { role: "user" as const, content }].slice(-KEPT);
    await ask();
    return true;
  }

  /** Ask again after a failure: the user's message is still the last one */
  async function retry() {
    if (messages.value.at(-1)?.role === "user") await ask();
  }

  function reset() {
    messages.value = [];
    error.value = "";
  }

  return { messages, thinking, error, send, retry, reset };
}
