import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import GroupChatGPTSignIn from "./GroupChatGPTSignIn.vue";
import type { ChatGPTLoginOut } from "~/lib/api/types/group";

const api = {
  startChatGPTLogin: vi.fn(),
  getChatGPTLogin: vi.fn(),
  cancelChatGPTLogin: vi.fn(),
};
vi.mock("~/composables/use-ai-providers", () => ({ useAIProviders: () => api }));

const copy = vi.fn();
vi.mock("@vueuse/core", async (original) => {
  const actual = await original<typeof import("@vueuse/core")>();
  return { ...actual, useClipboard: () => ({ copy, copied: ref(false) }) };
});

const WAITING: ChatGPTLoginOut = {
  id: "login-1",
  state: "waiting",
  verificationUrl: "https://auth.openai.com/codex/device",
  userCode: "KJCF-LG982",
};

const wrappers: VueWrapper[] = [];

function mountSignIn(props: Record<string, unknown> = {}) {
  const wrapper = mount(GroupChatGPTSignIn, {
    props,
    global: {
      mocks: { $globals: { icons: new Proxy({}, { get: (_, name) => String(name) }) } },
      stubs: {
        VBtn: {
          props: ["href", "loading"],
          emits: ["click"],
          template: `<a v-if="href" :href="href" class="btn" @click.prevent="$emit('click', $event)"><slot /></a>
            <button v-else type="button" class="btn" @click="$emit('click', $event)"><slot /></button>`,
        },
        VIcon: { template: "<i />" },
        VProgressCircular: { template: "<span />" },
        VExpansionPanels: { props: ["modelValue"], template: "<div class=\"help\" :data-open=\"modelValue ?? ''\"><slot /></div>" },
        VExpansionPanel: { template: "<div><slot /></div>" },
        VExpansionPanelTitle: { template: "<div><slot /></div>" },
        VExpansionPanelText: { template: "<div><slot /></div>" },
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

function button(wrapper: VueWrapper, text: string) {
  const found = wrapper.findAll(".btn").find(candidate => candidate.text().includes(text));
  if (!found) throw new Error(`No button "${text}" in: ${wrapper.text()}`);
  return found;
}

describe("GroupChatGPTSignIn", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.values(api).forEach(fn => fn.mockReset());
    copy.mockReset();
    api.cancelChatGPTLogin.mockResolvedValue({ data: null });
  });

  afterEach(() => {
    wrappers.splice(0).forEach(wrapper => wrapper.unmount());
    vi.useRealTimers();
  });

  test("leads with the ChatGPT setting that has to be on", () => {
    const wrapper = mountSignIn();
    expect(wrapper.text()).toContain("Allow sign-in with a code");
    expect(wrapper.text()).toContain("Device code authorization for Codex");
    expect(wrapper.find("a[href='https://chatgpt.com/#settings/Security']").exists()).toBe(true);
  });

  test("shows the code, and copies it on the way to OpenAI's page", async () => {
    api.startChatGPTLogin.mockResolvedValueOnce({ data: WAITING });
    const wrapper = mountSignIn();

    await button(wrapper, "Get a sign-in code").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("KJCF-LG982");
    expect(wrapper.text()).toContain("Code expires in 15:00");
    const open = button(wrapper, "Copy code and open OpenAI");
    expect(open.attributes("href")).toBe(WAITING.verificationUrl);
    await open.trigger("click");
    expect(copy).toHaveBeenCalledWith("KJCF-LG982");
  });

  test("notices when the sign-in finishes", async () => {
    api.startChatGPTLogin.mockResolvedValueOnce({ data: WAITING });
    api.getChatGPTLogin.mockResolvedValueOnce({ data: { ...WAITING, state: "connected", account: "cook@example.com" } });
    const wrapper = mountSignIn();

    await button(wrapper, "Get a sign-in code").trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();

    expect(wrapper.text()).toContain("Signed in to ChatGPT as cook@example.com");
    expect(wrapper.emitted("connected")?.[0]?.[0]).toMatchObject({ state: "connected" });
  });

  test("explains a failed sign-in and opens the help", async () => {
    api.startChatGPTLogin.mockResolvedValueOnce({ data: WAITING });
    api.getChatGPTLogin.mockResolvedValueOnce({ data: { ...WAITING, state: "failed", error: "The ChatGPT sign-in failed" } });
    const wrapper = mountSignIn();

    await button(wrapper, "Get a sign-in code").trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();

    expect(wrapper.text()).toContain("Couldn't sign in to ChatGPT");
    expect(wrapper.text()).toContain("device code authorization is on");
    expect(wrapper.find(".help").attributes("data-open")).toBe("help");
    expect(button(wrapper, "Get a new code").exists()).toBe(true);
  });

  test("says when a start fails", async () => {
    api.startChatGPTLogin.mockResolvedValueOnce({ data: null, error: { response: { data: { detail: { message: "Codex isn't installed" } } } } });
    const wrapper = mountSignIn();

    await button(wrapper, "Get a sign-in code").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Codex isn't installed");
  });

  test("shows a saved provider's account", () => {
    const wrapper = mountSignIn({ savedAccount: "cook@example.com" });
    expect(wrapper.text()).toContain("Signed in to ChatGPT as cook@example.com");
    expect(wrapper.text()).not.toContain("Allow sign-in with a code");
  });

  test("cancels a sign-in still waiting when it goes away", async () => {
    api.startChatGPTLogin.mockResolvedValueOnce({ data: WAITING });
    const wrapper = mountSignIn();

    await button(wrapper, "Get a sign-in code").trigger("click");
    await flushPromises();
    wrappers.splice(0).forEach(mounted => mounted.unmount());

    expect(api.cancelChatGPTLogin).toHaveBeenCalledWith("login-1");
  });
});
