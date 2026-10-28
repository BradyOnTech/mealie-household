import type {
  AIModelCatalog,
  AIProviderSummary,
  AITask,
  AITaskSettingOut,
} from "~/lib/api/types/group";
import type { AIProviderSettingsOut } from "~/lib/api/types/user";

/** The tasks shown in the settings, in the order they're listed */
export const AI_TASKS: { task: AITask; readsImages: boolean }[] = [
  { task: "household_assistant", readsImages: false },
  { task: "recipe_source_reading", readsImages: true },
  { task: "recipe_building", readsImages: false },
  { task: "cookbook_discovery", readsImages: true },
  { task: "cookbook_extraction", readsImages: true },
  { task: "ingredient_parsing", readsImages: false },
  { task: "recipe_translation", readsImages: false },
  { task: "organizer_matching", readsImages: false },
];

/** What a ChatGPT provider uses when no reasoning effort was chosen (see `chatgpt.REASONING_EFFORT`) */
export const CHATGPT_DEFAULT_EFFORT = "low";

/**
 * Effort levels to offer when a provider's models can't be listed. Which ones a model accepts is up to the model,
 * so these are suggestions, not promises.
 */
export const COMMON_EFFORTS = ["minimal", "low", "medium", "high", "xhigh"];

export type AIRouteSource = "task" | "task_images" | "group_default" | "group_images";

export interface AIRoute {
  providerId: string;
  source: AIRouteSource;
  /** null to use the provider's model */
  model: string | null;
  /** null to use the provider's reasoning effort */
  reasoningEffort: string | null;
}

export interface AIEffectiveChoice {
  provider: AIProviderSummary;
  source: AIRouteSource;
  /** "" when a ChatGPT provider uses its plan's default model */
  model: string;
  /** null when nothing was chosen: ChatGPT then uses low, and an API-key provider sends none */
  reasoningEffort: string | null;
}

type Settings = Pick<AIProviderSettingsOut, "defaultProviderId" | "imageProviderId" | "taskSettings">;

export function taskSetting(settings: Settings, task: AITask): AITaskSettingOut | undefined {
  return settings.taskSettings?.find(setting => setting.task === task);
}

/** The same rules as the server's `resolve_ai_route`: see mealie/services/openai/routing.py */
export function resolveTaskRoute(settings: Settings, task: AITask, images: boolean): AIRoute | null {
  const choice = taskSetting(settings, task);
  if (images) {
    if (choice?.imageProviderId) {
      return {
        providerId: choice.imageProviderId,
        source: "task_images",
        model: choice.imageModel || null,
        reasoningEffort: choice.imageReasoningEffort || null,
      };
    }
    return settings.imageProviderId
      ? { providerId: settings.imageProviderId, source: "group_images", model: null, reasoningEffort: null }
      : null;
  }

  if (choice?.providerId) {
    return {
      providerId: choice.providerId,
      source: "task",
      model: choice.model || null,
      reasoningEffort: choice.reasoningEffort || null,
    };
  }
  return settings.defaultProviderId
    ? { providerId: settings.defaultProviderId, source: "group_default", model: null, reasoningEffort: null }
    : null;
}

/** The provider, model and reasoning a task's request runs on, or null when it has no provider */
export function effectiveChoice(
  settings: Settings,
  providers: AIProviderSummary[],
  task: AITask,
  images: boolean,
): AIEffectiveChoice | null {
  const route = resolveTaskRoute(settings, task, images);
  const provider = route && providers.find(candidate => candidate.id === route.providerId);
  if (!route || !provider) return null;

  return {
    provider,
    source: route.source,
    model: route.model ?? provider.model ?? "",
    reasoningEffort: route.reasoningEffort ?? provider.reasoningEffort ?? null,
  };
}

export type TaskChoicePatch = Partial<Omit<AITaskSettingOut, "task">>;

/**
 * The task settings with one task's choice changed. Choosing a different provider (or none) clears the model and
 * reasoning picked for the old one, since they may not exist on the new one. Tasks left with no provider at all
 * are dropped, which is how they go back to the group's defaults.
 */
export function updateTaskSetting(
  current: AITaskSettingOut[] | undefined,
  task: AITask,
  patch: TaskChoicePatch,
): AITaskSettingOut[] {
  const list = current ?? [];
  const previous: AITaskSettingOut = list.find(setting => setting.task === task) ?? { task };
  const next: AITaskSettingOut = { ...previous, ...patch, task };

  if ("providerId" in patch && (patch.providerId ?? null) !== (previous.providerId ?? null)) {
    next.model = "model" in patch ? patch.model : null;
    next.reasoningEffort = "reasoningEffort" in patch ? patch.reasoningEffort : null;
  }
  if ("imageProviderId" in patch && (patch.imageProviderId ?? null) !== (previous.imageProviderId ?? null)) {
    next.imageModel = "imageModel" in patch ? patch.imageModel : null;
    next.imageReasoningEffort = "imageReasoningEffort" in patch ? patch.imageReasoningEffort : null;
  }
  if (!next.providerId) {
    next.providerId = next.model = next.reasoningEffort = null;
  }
  if (!next.imageProviderId) {
    next.imageProviderId = next.imageModel = next.imageReasoningEffort = null;
  }

  const others = list.filter(setting => setting.task !== task);
  return next.providerId || next.imageProviderId ? [...others, next] : others;
}

/**
 * The effort levels to offer for a model: what its catalog entry lists, when the model is in the catalog, and
 * otherwise the common ones. A value already saved is always kept, so it isn't dropped just because it isn't listed.
 */
export function effortOptions(catalog: AIModelCatalog | null | undefined, model: string, saved?: string | null): string[] {
  const entry = catalog?.discovered
    ? catalog.models?.find(option => option.model === model) ?? (model ? undefined : catalog.models?.find(option => option.isDefault))
    : undefined;
  const listed = entry?.supportedReasoningEfforts?.map(option => option.effort) ?? [];
  const options = listed.length ? listed : COMMON_EFFORTS;
  return saved && !options.includes(saved) ? [...options, saved] : options;
}

/** Catalogs of the models each provider (or unsaved sign-in) lists, fetched once each, when first wanted */
export function useAIModelCatalogs(fetchCatalog: (key: string) => Promise<AIModelCatalog | null>) {
  const catalogs = reactive<Record<string, AIModelCatalog | null>>({});
  const loading = reactive<Record<string, boolean>>({});
  const pending = new Map<string, Promise<void>>();

  function load(key: string | null | undefined): Promise<void> {
    if (!key || key in catalogs) return Promise.resolve();
    const existing = pending.get(key);
    if (existing) return existing;

    loading[key] = true;
    const request = fetchCatalog(key)
      .catch(() => null)
      .then((catalog) => {
        // A failed listing still counts as loaded, so it isn't retried on every render; a model can be typed in
        catalogs[key] = catalog ?? { discovered: false, models: [] };
      })
      .finally(() => {
        loading[key] = false;
        pending.delete(key);
      });
    pending.set(key, request);
    return request;
  }

  return { catalogs, loading, load };
}
