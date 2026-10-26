import { beforeEach, describe, expect, test, vi } from "vitest";
import { useHouseholdConversation, useHouseholdUnread } from "../use-household-messages";
import type { HouseholdMessageOut } from "~/lib/api/types/messages";

const api = {
  list: vi.fn(),
  send: vi.fn(),
  remove: vi.fn(),
  markRead: vi.fn(),
  unread: vi.fn(),
};
vi.mock("~/composables/api", () => ({
  useUserApi: () => ({ messages: api }),
}));

function message(id: string, minute: number, userId = "user-2"): HouseholdMessageOut {
  return {
    id,
    userId,
    user: { id: userId, fullName: userId === "user-1" ? "Me" : "Sam" },
    text: `message ${id}`,
    createdAt: `2026-10-26T12:${String(minute).padStart(2, "0")}:00Z`,
  };
}

function page(items: HouseholdMessageOut[], extra: { hasOlder?: boolean; unread?: number } = {}) {
  return { data: { items, hasOlder: false, unread: 0, ...extra }, error: null, response: {} };
}

describe("useHouseholdConversation", () => {
  beforeEach(() => {
    Object.values(api).forEach(fn => fn.mockReset());
    api.markRead.mockResolvedValue({ data: { unread: 0 }, error: null, response: {} });
  });

  test("loads the latest messages and marks them read", async () => {
    api.list.mockResolvedValueOnce(page([message("a", 1), message("b", 2)], { hasOlder: true, unread: 2 }));
    const unread = useHouseholdUnread();
    unread.set(2);
    const chat = useHouseholdConversation();

    await chat.load();

    expect(chat.messages.value.map(m => m.id)).toEqual(["a", "b"]);
    expect(chat.hasOlder.value).toBe(true);
    expect(chat.loading.value).toBe(false);
    expect(api.markRead).toHaveBeenCalledWith({ readAt: "2026-10-26T12:02:00Z" });
    expect(unread.unread.value).toBe(0);
  });

  test("polls for what's new after the newest message, without repeats", async () => {
    api.list.mockResolvedValueOnce(page([message("a", 1)]));
    const chat = useHouseholdConversation();
    await chat.load();

    api.list.mockResolvedValueOnce(page([message("a", 1), message("b", 2)]));
    await chat.poll();

    expect(api.list).toHaveBeenLastCalledWith({ after: "2026-10-26T12:01:00Z", limit: 50 });
    expect(chat.messages.value.map(m => m.id)).toEqual(["a", "b"]);
  });

  test("pages back through older messages", async () => {
    api.list.mockResolvedValueOnce(page([message("c", 3)], { hasOlder: true }));
    const chat = useHouseholdConversation();
    await chat.load();

    api.list.mockResolvedValueOnce(page([message("a", 1), message("b", 2)]));
    await chat.loadOlder();

    expect(api.list).toHaveBeenLastCalledWith({ before: "2026-10-26T12:03:00Z", limit: 50 });
    expect(chat.messages.value.map(m => m.id)).toEqual(["a", "b", "c"]);
    expect(chat.hasOlder.value).toBe(false);
  });

  test("adds a sent message, and reports a failed one", async () => {
    api.list.mockResolvedValueOnce(page([]));
    const chat = useHouseholdConversation();
    await chat.load();

    api.send.mockResolvedValueOnce({ data: message("mine", 5, "user-1"), error: null, response: {} });
    expect(await chat.send("  Out of eggs  ")).toBe(true);
    expect(api.send).toHaveBeenCalledWith({ text: "Out of eggs" });
    expect(chat.messages.value.map(m => m.id)).toEqual(["mine"]);

    api.send.mockResolvedValueOnce({ data: null, error: { response: { data: { detail: "Too long" } } }, response: null });
    expect(await chat.send("again")).toBe(false);
    expect(chat.error.value).toBe("Too long");

    expect(await chat.send("   ")).toBe(false);
    expect(api.send).toHaveBeenCalledTimes(2);
  });

  test("removes a deleted message", async () => {
    api.list.mockResolvedValueOnce(page([message("a", 1, "user-1"), message("b", 2)]));
    const chat = useHouseholdConversation();
    await chat.load();

    api.remove.mockResolvedValueOnce({ data: message("a", 1, "user-1"), error: null, response: {} });
    await chat.remove("a");

    expect(api.remove).toHaveBeenCalledWith("a");
    expect(chat.messages.value.map(m => m.id)).toEqual(["b"]);
  });
});
