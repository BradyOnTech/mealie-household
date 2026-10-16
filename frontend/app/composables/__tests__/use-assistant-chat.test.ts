import { beforeEach, describe, expect, test, vi } from "vitest";
import { useAssistantChat } from "../use-assistant-chat";

const mockChat = vi.fn();
vi.mock("~/composables/api", () => ({
  useUserApi: () => ({ assistant: { chat: mockChat } }),
}));
vi.stubGlobal("useMealieAuth", () => ({ user: ref({ id: "user-1" }) }));

function reply(text: string, actions: { kind: string; summary: string }[] = []) {
  return { data: { reply: text, actions }, error: null };
}

describe("useAssistantChat", () => {
  beforeEach(() => {
    localStorage.clear();
    mockChat.mockReset();
  });

  test("sends the conversation and keeps the reply and its actions", async () => {
    const onActions = vi.fn();
    const actions = [{ kind: "restock", summary: "Added rice to Out of" }];
    mockChat.mockResolvedValueOnce(reply("Added rice.", actions));
    const chat = useAssistantChat(onActions);

    expect(await chat.send("  We're out of rice  ")).toBe(true);

    expect(mockChat).toHaveBeenCalledWith({ messages: [{ role: "user", content: "We're out of rice" }] });
    expect(chat.messages.value).toEqual([
      { role: "user", content: "We're out of rice" },
      { role: "assistant", content: "Added rice.", actions },
    ]);
    expect(onActions).toHaveBeenCalledWith(actions);
    expect(chat.thinking.value).toBe(false);
  });

  test("ignores blank messages", async () => {
    const chat = useAssistantChat();
    expect(await chat.send("   ")).toBe(false);
    expect(mockChat).not.toHaveBeenCalled();
  });

  test("sends the recent conversation, starting with the user", async () => {
    const chat = useAssistantChat();
    chat.messages.value = Array.from({ length: 30 }, (_, i) => ({
      role: i % 2 ? "assistant" as const : "user" as const,
      content: `message ${i}`,
    }));
    mockChat.mockResolvedValueOnce(reply("Sure."));

    await chat.send("And milk");

    const sent = mockChat.mock.calls[0]![0].messages;
    expect(sent[0]).toEqual({ role: "user", content: "message 8" });
    expect(sent.at(-1)).toEqual({ role: "user", content: "And milk" });
    expect(sent.length).toBe(23);
  });

  test("keeps the question after a failure so it can be asked again", async () => {
    mockChat.mockResolvedValueOnce({ data: null, error: { response: { data: { detail: { message: "Usage limit reached" } } } } });
    const chat = useAssistantChat();

    await chat.send("What's on the list?");
    expect(chat.error.value).toBe("Usage limit reached");
    expect(chat.messages.value).toEqual([{ role: "user", content: "What's on the list?" }]);

    mockChat.mockResolvedValueOnce(reply("Rice and milk."));
    await chat.retry();
    expect(chat.error.value).toBe("");
    expect(chat.messages.value.at(-1)).toEqual({ role: "assistant", content: "Rice and milk.", actions: [] });

    chat.reset();
    expect(chat.messages.value).toEqual([]);
  });
});
