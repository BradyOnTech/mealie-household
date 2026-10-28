import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import GroupAITaskSettings from "./GroupAITaskSettings.vue";
import type { AIProviderSettingsOut } from "~/lib/api/types/user";

const api = { listModels: vi.fn() };
vi.mock("~/composables/use-ai-providers", () => ({ useAIProviders: () => api }));

function baseSettings(overrides: Partial<AIProviderSettingsOut> = {}): AIProviderSettingsOut {
  return {
    defaultProviderId: "chatgpt",
    audioProviderId: null,
    imageProviderId: "chatgpt",
    providers: [
      { id: "chatgpt", name: "Family ChatGPT", providerType: "chatgpt", model: "", reasoningEffort: null },
      { id: "api", name: "OpenAI key", providerType: "openai", model: "gpt-api", reasoningEffort: null },
    ],
    taskSettings: [],
    aiEnabled: true,
    audioProviderEnabled: false,
    imageProviderEnabled: true,
    imageReadingTasks: ["recipe_source_reading", "cookbook_discovery", "cookbook_extraction"],
    ...overrides,
  };
}

// Plain stand-ins for Vuetify's fields, so the test can choose options the way a person would
const VSelect = {
  props: ["modelValue", "items", "label"],
  emits: ["update:modelValue"],
  template: `<label class="select">{{ label }}
    <select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)">
      <option v-for="item in items" :key="item.value" :value="item.value">{{ item.title }}</option>
    </select></label>`,
};

const wrappers: VueWrapper[] = [];

function mountTasks(settings: AIProviderSettingsOut) {
  const wrapper = mount(GroupAITaskSettings, {
    props: {
      "modelValue": settings,
      "onUpdate:modelValue": (value: AIProviderSettingsOut) => wrapper.setProps({ modelValue: value }),
    },
    global: {
      stubs: {
        VBtn: { emits: ["click"], template: `<button type="button" class="btn" @click="$emit('click')"><slot /></button>` },
        VSelect,
        GroupAIModelFields: {
          props: ["model", "effort", "providerType", "catalog", "catalogLoading", "inheritedModel", "inheritedEffort"],
          emits: ["update:model", "update:effort"],
          template: `<div class="model-fields" :data-type="providerType" :data-inherited-model="inheritedModel">
            <input class="model" :value="model" @change="$emit('update:model', $event.target.value)" />
            <input class="effort" :value="effort" @change="$emit('update:effort', $event.target.value)" />
          </div>`,
        },
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

function row(wrapper: VueWrapper, task: string) {
  return wrapper.get(`[data-task="${task}"]`);
}

function latest(wrapper: VueWrapper): AIProviderSettingsOut {
  const emitted = wrapper.emitted("update:modelValue") ?? [];
  return emitted[emitted.length - 1]![0] as AIProviderSettingsOut;
}

describe("GroupAITaskSettings", () => {
  beforeEach(() => {
    api.listModels.mockResolvedValue({ data: { discovered: true, models: [] } });
  });

  afterEach(() => {
    wrappers.splice(0).forEach(wrapper => wrapper.unmount());
    vi.clearAllMocks();
  });

  test("says the choices are shared by the whole group", () => {
    const wrapper = mountTasks(baseSettings());
    expect(wrapper.text()).toContain("shared by every household in this group");
  });

  test("shows what each task runs on when nothing has been customized", () => {
    const wrapper = mountTasks(baseSettings());

    const uses = row(wrapper, "recipe_building").get("[data-testid=uses-text]").text();
    expect(uses).toContain("Family ChatGPT");
    expect(uses).toContain("Plan's default model");
    expect(uses).toContain("Low reasoning");
    expect(uses).toContain("group default");

    const images = row(wrapper, "recipe_source_reading").get("[data-testid=uses-images]").text();
    expect(images).toContain("group photos provider");
    // text-only tasks don't mention images
    expect(row(wrapper, "recipe_building").find("[data-testid=uses-images]").exists()).toBe(false);
  });

  test("an API-key provider with no reasoning chosen lets the model decide", () => {
    const wrapper = mountTasks(baseSettings({ defaultProviderId: "api" }));
    const uses = row(wrapper, "ingredient_parsing").get("[data-testid=uses-text]").text();
    expect(uses).toContain("gpt-api");
    expect(uses).toContain("model's own reasoning");
  });

  test("says when a task has no provider to read images with", () => {
    const wrapper = mountTasks(baseSettings({ imageProviderId: null }));
    expect(row(wrapper, "cookbook_discovery").get("[data-testid=uses-images]").text()).toContain("No provider reads images");
  });

  test("customizing is behind a disclosure button that says whether it's open", async () => {
    const wrapper = mountTasks(baseSettings());
    const toggle = row(wrapper, "recipe_building").get(".btn");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(row(wrapper, "recipe_building").find(".select").exists()).toBe(false);

    await toggle.trigger("click");

    expect(row(wrapper, "recipe_building").get(".btn").attributes("aria-expanded")).toBe("true");
    expect(row(wrapper, "recipe_building").get(".btn").attributes("aria-controls")).toBe("ai-task-recipe_building");
    expect(row(wrapper, "recipe_building").find("#ai-task-recipe_building").exists()).toBe(true);
  });

  test("choosing a provider and model for one task saves only that task", async () => {
    const wrapper = mountTasks(baseSettings());
    await row(wrapper, "recipe_building").get(".btn").trigger("click");

    await row(wrapper, "recipe_building").get("select").setValue("api");
    await row(wrapper, "recipe_building").get("input.model").setValue("gpt-bigger");
    await row(wrapper, "recipe_building").get("input.model").trigger("change");

    expect(latest(wrapper).taskSettings).toEqual([
      expect.objectContaining({ task: "recipe_building", providerId: "api", model: "gpt-bigger" }),
    ]);
    // the fields fall back to the chosen provider's model
    expect(row(wrapper, "recipe_building").get(".model-fields").attributes("data-inherited-model")).toBe("gpt-api");
    expect(row(wrapper, "recipe_building").get("[data-testid=uses-text]").text()).toContain("gpt-bigger");
    expect(row(wrapper, "recipe_building").text()).toContain("Customized");
    // an API-key provider has no catalog to list
    expect(api.listModels).not.toHaveBeenCalled();
  });

  test("lists a ChatGPT provider's models only once a task using it is opened", async () => {
    const wrapper = mountTasks(baseSettings({ taskSettings: [{ task: "household_assistant", providerId: "chatgpt" }] }));
    await flushPromises();
    expect(api.listModels).not.toHaveBeenCalled();

    await row(wrapper, "household_assistant").get(".btn").trigger("click");
    await flushPromises();

    expect(api.listModels).toHaveBeenCalledExactlyOnceWith("chatgpt");
  });

  test("an image-reading task can have its own image provider", async () => {
    const wrapper = mountTasks(baseSettings({ imageProviderId: null }));
    await row(wrapper, "cookbook_extraction").get(".btn").trigger("click");

    const selects = row(wrapper, "cookbook_extraction").findAll("select");
    expect(selects).toHaveLength(2);
    expect(selects[1]!.text()).toContain("Group photos provider (none chosen)");
    await selects[1]!.setValue("api");

    expect(latest(wrapper).taskSettings).toEqual([
      expect.objectContaining({ task: "cookbook_extraction", providerId: null, imageProviderId: "api" }),
    ]);
    expect(row(wrapper, "cookbook_extraction").get("[data-testid=uses-images]").text()).toContain("chosen for this task's images");
  });

  test("resetting a task goes back to the group's providers", async () => {
    const wrapper = mountTasks(baseSettings({ taskSettings: [{ task: "recipe_translation", providerId: "api" }] }));
    await row(wrapper, "recipe_translation").get(".btn").trigger("click");

    const reset = row(wrapper, "recipe_translation").findAll(".btn").find(button => button.text().includes("Use the group's providers"));
    await reset!.trigger("click");

    expect(latest(wrapper).taskSettings).toEqual([]);
  });
});
