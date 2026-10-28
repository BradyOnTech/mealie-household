import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, test } from "vitest";
import GroupAIModelFields from "./GroupAIModelFields.vue";
import type { AIModelCatalog } from "~/lib/api/types/group";

const CATALOG: AIModelCatalog = {
  discovered: true,
  models: [
    {
      model: "fast-model",
      displayName: "Fast",
      isDefault: true,
      defaultReasoningEffort: "low",
      supportedReasoningEfforts: [{ effort: "low", description: "Quickest" }, { effort: "medium" }],
    },
    { model: "deep-model", displayName: "Deep", supportedReasoningEfforts: [{ effort: "high" }, { effort: "xhigh" }] },
  ],
};

const field = (cls: string) => ({
  props: ["modelValue", "items", "label", "hint", "placeholder"],
  emits: ["update:modelValue"],
  template: `<div class="${cls}" :data-hint="hint" :data-placeholder="placeholder">
    <span v-for="item in items ?? []" :key="item.value" class="item" :data-value="item.value">{{ item.title }}</span>
    <input :value="modelValue" @change="$emit('update:modelValue', $event.target.value)" />
  </div>`,
});

const wrappers: VueWrapper[] = [];

function mountFields(props: InstanceType<typeof GroupAIModelFields>["$props"]) {
  const wrapper = mount(GroupAIModelFields, {
    props,
    global: { stubs: { VCombobox: field("combobox"), VTextField: field("text"), VSelect: field("select") } },
  });
  wrappers.push(wrapper);
  return wrapper;
}

function effortItems(wrapper: VueWrapper) {
  return wrapper.get(".select").findAll(".item").map(item => [item.attributes("data-value"), item.text()]);
}

describe("GroupAIModelFields", () => {
  afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()));

  test("a ChatGPT provider picks from its catalog, and its reasoning defaults to low", () => {
    const wrapper = mountFields({ providerType: "chatgpt", catalog: CATALOG, model: null, effort: null });

    expect(wrapper.get(".combobox").findAll(".item").map(item => item.attributes("data-value"))).toEqual(["fast-model", "deep-model"]);
    expect(wrapper.get(".combobox").attributes("data-hint")).toContain("isn't a promise your plan can use it");
    // no model chosen means the plan's default model, so its levels are offered
    expect(effortItems(wrapper)).toEqual([
      ["__inherit__", "Mealie's default (low)"],
      ["low", "Low"],
      ["medium", "Medium"],
    ]);
  });

  test("the levels follow the chosen model", () => {
    const wrapper = mountFields({ providerType: "chatgpt", catalog: CATALOG, model: "deep-model", effort: null });
    expect(effortItems(wrapper).map(([value]) => value)).toEqual(["__inherit__", "high", "xhigh"]);
  });

  test("choosing the default stores no effort at all", async () => {
    const wrapper = mountFields({ "providerType": "chatgpt", "catalog": CATALOG, "model": null, "effort": "medium", "onUpdate:effort": () => {} });

    await wrapper.get(".select input").setValue("__inherit__");
    expect(wrapper.emitted("update:effort")?.at(-1)).toEqual([null]);

    await wrapper.get(".select input").setValue("low");
    expect(wrapper.emitted("update:effort")?.at(-1)).toEqual(["low"]);
  });

  test("a blank model means the provider's model", async () => {
    const wrapper = mountFields({ providerType: "chatgpt", catalog: CATALOG, model: "deep-model", effort: null });
    await wrapper.get(".combobox input").setValue("  ");
    expect(wrapper.emitted("update:model")?.at(-1)).toEqual([null]);
  });

  test("when the models can't be listed, it says why and a name can still be typed", () => {
    const wrapper = mountFields({ providerType: "chatgpt", catalog: { discovered: false, message: "Codex isn't installed" }, model: null, effort: null });
    expect(wrapper.get(".combobox").attributes("data-hint")).toContain("Codex isn't installed");
    expect(effortItems(wrapper).map(([value]) => value)).toContain("medium");
  });

  test("an API-key provider sends no reasoning unless a level is chosen", () => {
    const wrapper = mountFields({ providerType: "openai", model: null, effort: null, showModel: false });
    expect(wrapper.find(".text").exists()).toBe(false);
    expect(effortItems(wrapper)[0]).toEqual(["__inherit__", "Not sent (the model decides)"]);
    expect(wrapper.get(".select").attributes("data-hint")).toContain("Only sent when you choose a level");
  });

  test("a task's override falls back to its provider's choices", () => {
    const wrapper = mountFields({
      providerType: "openai",
      model: null,
      effort: null,
      inheriting: true,
      inheritedModel: "gpt-api",
      inheritedEffort: "high",
    });
    expect(wrapper.get(".text").attributes("data-placeholder")).toBe("Provider's model (gpt-api)");
    expect(effortItems(wrapper)[0]).toEqual(["__inherit__", "Provider's setting (High)"]);
  });
});
