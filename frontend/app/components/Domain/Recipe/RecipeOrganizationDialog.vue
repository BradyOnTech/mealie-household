<template>
  <BaseDialog
    v-model="open"
    :title="$t('recipe.organize-recipes')"
    :icon="$globals.icons.tags"
    width="750"
    can-submit
    keep-open
    :loading="applying"
    :submit-disabled="previewing || applying || accepted.length === 0"
    :submit-text="$t('recipe.apply-organization')"
    @submit="apply"
  >
    <v-card-text>
      <p>{{ $t('recipe.organization-review-hint') }}</p>
      <v-alert v-if="error" type="error" variant="tonal" class="mt-4" role="alert">
        {{ error }}
      </v-alert>
      <div v-if="previewing" class="my-4" role="status" aria-live="polite">
        {{ $t('recipe.organization-progress', [suggestions.length, targets.length]) }}
        <v-progress-linear :model-value="100 * suggestions.length / targets.length" class="mt-2" />
      </div>
      <v-card v-for="suggestion in suggestions" :key="suggestion.recipeId" variant="outlined" class="mt-4 pa-3">
        <v-checkbox
          v-model="accepted"
          :value="suggestion.recipeId"
          :label="suggestion.name"
          :disabled="suggestion.error || applying || previewing"
          hide-details
          density="compact"
        />
        <p v-if="suggestion.error" class="text-error" role="status">
          {{ $t('recipe.organization-failed') }}
        </p>
        <template v-else>
          <div v-for="kind in kinds" :key="kind.key" class="mt-2">
            <span class="text-caption me-2">{{ $t(kind.label) }}</span>
            <v-chip
              v-for="name in suggestion[kind.key]"
              :key="name"
              closable
              :disabled="applying || previewing"
              class="ma-1"
              size="small"
              @click:close="removeLabel(suggestion, kind.key, name)"
            >
              {{ name }}
            </v-chip>
            <span v-if="!suggestion[kind.key]?.length" class="text-caption">—</span>
          </div>
        </template>
      </v-card>
    </v-card-text>
  </BaseDialog>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import { useCategoryStore, useTagStore, useToolStore } from "~/composables/store";
import type { Recipe, RecipeOrganizationOut } from "~/lib/api/types/recipe";

const props = defineProps<{ recipes: Recipe[] }>();
const emit = defineEmits<{ applied: [] }>();
const open = defineModel<boolean>({ default: false });
const api = useUserApi();
const i18n = useI18n();
const tags = useTagStore();
const categories = useCategoryStore();
const tools = useToolStore();

const kinds = [
  { key: "categories", label: "recipe.categories" },
  { key: "cuisines", label: "recipe.cuisines" },
  { key: "tags", label: "tag.tags" },
  { key: "tools", label: "tool.tools" },
] as const;
type LabelKind = typeof kinds[number]["key"];

const targets = ref<Recipe[]>([]);
const suggestions = ref<RecipeOrganizationOut[]>([]);
const accepted = ref<string[]>([]);
const previewing = ref(false);
const applying = ref(false);
const error = ref("");
let generation = 0;

watch(open, async (value) => {
  const current = ++generation;
  if (!value) return;
  targets.value = [...props.recipes];
  suggestions.value = [];
  accepted.value = [];
  error.value = "";
  previewing.value = false;
  if (targets.value.length > 50) {
    error.value = i18n.t("recipe.organization-batch-limit");
    return;
  }
  previewing.value = true;
  try {
    // One recipe per request keeps long model calls from timing out an entire batch.
    for (const recipe of targets.value) {
      const { data } = await api.bulk.previewOrganization([recipe.slug ?? ""]);
      if (current !== generation) return;
      if (!data) throw new Error("preview failed");
      suggestions.value.push(...data);
      accepted.value.push(...data.filter(item => !item.error).map(item => item.recipeId));
    }
  }
  catch {
    if (current === generation) error.value = i18n.t("recipe.organization-failed");
  }
  finally {
    if (current === generation) previewing.value = false;
  }
});

function removeLabel(suggestion: RecipeOrganizationOut, kind: LabelKind, name: string) {
  const labels: string[] | undefined = suggestion[kind];
  const index = labels?.indexOf(name) ?? -1;
  if (labels && index >= 0) labels.splice(index, 1);
}

async function apply() {
  if (previewing.value || applying.value || !accepted.value.length) return;
  applying.value = true;
  error.value = "";
  try {
    const recipes = suggestions.value
      .filter(item => accepted.value.includes(item.recipeId) && !item.error)
      .map(({ recipeId, tags, categories, cuisines, tools }) => ({ recipeId, tags, categories, cuisines, tools }));
    const { response } = await api.bulk.applyOrganization(recipes);
    if (response?.status !== 200) throw new Error("apply failed");
    await Promise.all([tags.actions.refresh(), categories.actions.refresh(), tools.actions.refresh()]);
    emit("applied");
    open.value = false;
  }
  catch {
    error.value = i18n.t("recipe.organization-failed");
  }
  finally {
    applying.value = false;
  }
}
</script>
