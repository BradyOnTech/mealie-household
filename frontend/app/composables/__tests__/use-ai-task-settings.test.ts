import { describe, expect, test, vi } from "vitest";
import {
  COMMON_EFFORTS,
  effectiveChoice,
  effortOptions,
  resolveTaskRoute,
  updateTaskSetting,
  useAIModelCatalogs,
} from "../use-ai-task-settings";
import type { AIModelCatalog, AIProviderSummary, AITaskSettingOut } from "~/lib/api/types/group";

const chatgpt: AIProviderSummary = { id: "chatgpt", name: "ChatGPT", providerType: "chatgpt", model: "", reasoningEffort: null };
const api: AIProviderSummary = { id: "api", name: "OpenAI", providerType: "openai", model: "gpt-api", reasoningEffort: "high" };
const providers = [chatgpt, api];

function settings(taskSettings: AITaskSettingOut[] = [], imageProviderId: string | null = "chatgpt") {
  return { defaultProviderId: "chatgpt", imageProviderId, taskSettings };
}

describe("resolveTaskRoute", () => {
  test("a task with no choices follows the group's providers", () => {
    expect(resolveTaskRoute(settings(), "recipe_building", false)).toEqual({
      providerId: "chatgpt", source: "group_default", model: null, reasoningEffort: null,
    });
    expect(resolveTaskRoute(settings(), "recipe_source_reading", true)?.source).toBe("group_images");
  });

  test("a task's provider is used for text, but never for images", () => {
    const choice: AITaskSettingOut = { task: "recipe_source_reading", providerId: "api", model: "gpt-big", reasoningEffort: "medium" };

    expect(resolveTaskRoute(settings([choice]), "recipe_source_reading", false)).toEqual({
      providerId: "api", source: "task", model: "gpt-big", reasoningEffort: "medium",
    });
    expect(resolveTaskRoute(settings([choice]), "recipe_source_reading", true)?.providerId).toBe("chatgpt");
    expect(resolveTaskRoute(settings([choice], null), "recipe_source_reading", true)).toBeNull();
  });

  test("a task's image provider is used for its images", () => {
    const choice: AITaskSettingOut = { task: "cookbook_extraction", imageProviderId: "api", imageModel: "gpt-vision" };

    expect(resolveTaskRoute(settings([choice], null), "cookbook_extraction", true)).toEqual({
      providerId: "api", source: "task_images", model: "gpt-vision", reasoningEffort: null,
    });
    // other tasks don't pick it up
    expect(resolveTaskRoute(settings([choice], null), "cookbook_discovery", true)).toBeNull();
  });
});

describe("effectiveChoice", () => {
  test("model and reasoning fall back to the provider's", () => {
    const choice = effectiveChoice(settings([{ task: "ingredient_parsing", providerId: "api" }]), providers, "ingredient_parsing", false);
    expect(choice).toMatchObject({ provider: api, model: "gpt-api", reasoningEffort: "high", source: "task" });
  });

  test("a ChatGPT provider with nothing chosen uses the plan's model and Mealie's default effort", () => {
    const choice = effectiveChoice(settings(), providers, "household_assistant", false);
    expect(choice).toMatchObject({ provider: chatgpt, model: "", reasoningEffort: null, source: "group_default" });
  });

  test("a provider that's gone is no choice at all, rather than another provider", () => {
    expect(effectiveChoice(settings([{ task: "recipe_translation", providerId: "deleted" }]), providers, "recipe_translation", false)).toBeNull();
  });
});

describe("updateTaskSetting", () => {
  test("choosing a provider adds the task", () => {
    expect(updateTaskSetting([], "recipe_building", { providerId: "api" })).toEqual([
      { task: "recipe_building", providerId: "api", model: null, reasoningEffort: null, imageProviderId: null, imageModel: null, imageReasoningEffort: null },
    ]);
  });

  test("switching provider clears the model and reasoning picked for the old one", () => {
    const before: AITaskSettingOut[] = [{ task: "recipe_building", providerId: "api", model: "gpt-big", reasoningEffort: "high" }];
    const [after] = updateTaskSetting(before, "recipe_building", { providerId: "chatgpt" });
    expect(after).toMatchObject({ providerId: "chatgpt", model: null, reasoningEffort: null });
  });

  test("changing the model keeps the provider and reasoning", () => {
    const before: AITaskSettingOut[] = [{ task: "recipe_building", providerId: "api", model: "a", reasoningEffort: "high" }];
    const [after] = updateTaskSetting(before, "recipe_building", { model: "b" });
    expect(after).toMatchObject({ providerId: "api", model: "b", reasoningEffort: "high" });
  });

  test("clearing every provider drops the task, so it goes back to the group's providers", () => {
    const before: AITaskSettingOut[] = [
      { task: "recipe_building", providerId: "api", model: "a" },
      { task: "ingredient_parsing", providerId: "api" },
    ];
    expect(updateTaskSetting(before, "recipe_building", { providerId: null })).toEqual([{ task: "ingredient_parsing", providerId: "api" }]);
  });

  test("text and image choices are independent", () => {
    const before: AITaskSettingOut[] = [{ task: "cookbook_discovery", providerId: "api", model: "a" }];
    const [after] = updateTaskSetting(before, "cookbook_discovery", { imageProviderId: "chatgpt" });
    expect(after).toMatchObject({ providerId: "api", model: "a", imageProviderId: "chatgpt" });
  });
});

describe("effortOptions", () => {
  const catalog: AIModelCatalog = {
    discovered: true,
    models: [
      { model: "fast", displayName: "Fast", isDefault: true, supportedReasoningEfforts: [{ effort: "low" }, { effort: "medium" }] },
      { model: "deep", displayName: "Deep", supportedReasoningEfforts: [{ effort: "high" }, { effort: "max" }] },
    ],
  };

  test("offers what the model's catalog entry lists", () => {
    expect(effortOptions(catalog, "deep")).toEqual(["high", "max"]);
    // no model chosen means the plan's default model
    expect(effortOptions(catalog, "")).toEqual(["low", "medium"]);
  });

  test("falls back to common levels for unlisted models or no catalog", () => {
    expect(effortOptions(catalog, "custom-model")).toEqual(COMMON_EFFORTS);
    expect(effortOptions(null, "anything")).toEqual(COMMON_EFFORTS);
    expect(effortOptions({ discovered: false, models: [] }, "")).toEqual(COMMON_EFFORTS);
  });

  test("keeps a saved level that isn't listed", () => {
    expect(effortOptions(catalog, "deep", "low")).toEqual(["high", "max", "low"]);
  });
});

describe("useAIModelCatalogs", () => {
  test("lists each provider's models once, even when asked twice at the same time", async () => {
    const fetchCatalog = vi.fn(async () => ({ discovered: true, models: [] }) as AIModelCatalog);
    const { catalogs, load } = useAIModelCatalogs(fetchCatalog);

    await Promise.all([load("chatgpt"), load("chatgpt")]);
    await load("chatgpt");

    expect(fetchCatalog).toHaveBeenCalledTimes(1);
    expect(catalogs.chatgpt?.discovered).toBe(true);
  });

  test("a failed listing is remembered as undiscovered rather than retried", async () => {
    const fetchCatalog = vi.fn(async () => {
      throw new Error("offline");
    });
    const { catalogs, loading, load } = useAIModelCatalogs(fetchCatalog);

    await load("chatgpt");
    await load("chatgpt");

    expect(fetchCatalog).toHaveBeenCalledTimes(1);
    expect(catalogs.chatgpt).toEqual({ discovered: false, models: [] });
    expect(loading.chatgpt).toBe(false);
  });
});
