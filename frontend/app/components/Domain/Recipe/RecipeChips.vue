<template>
  <div v-if="items.length > 0">
    <h2
      v-if="title"
      class="mt-4"
    >
      {{ title }}
    </h2>
    <v-chip
      v-for="category in items.slice(0, limit)"
      :key="category.name"
      class="recipe-chip mr-1 mt-1"
      variant="outlined"
      :size="small ? 'small' : 'default'"
      @click.prevent="() => $emit('item-selected', category, urlPrefix)"
    >
      {{ truncateText(category.name) }}
    </v-chip>
  </div>
</template>

<script setup lang="ts">
import type { RecipeCategory, RecipeTag, RecipeTool } from "~/lib/api/types/recipe";
import { truncateText as truncatePlainText } from "~/lib/sanitize/text";

export type UrlPrefixParam = "tags" | "categories" | "tools";

interface Props {
  truncate?: boolean;
  items?: RecipeCategory[] | RecipeTag[] | RecipeTool[];
  title?: boolean;
  urlPrefix?: UrlPrefixParam;
  limit?: number;
  small?: boolean;
  maxWidth?: string | null;
}
const props = withDefaults(defineProps<Props>(), {
  truncate: false,
  items: () => [],
  title: false,
  urlPrefix: "categories",
  limit: 999,
  small: false,
  maxWidth: null,
});

defineEmits(["item-selected"]);
function truncateText(text: string, length = 20, clamp = "...") {
  if (!props.truncate) return text;
  return truncatePlainText(text, length, clamp);
}
</script>

<style scoped>
.recipe-chip.v-chip--variant-outlined {
  border-color: rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
}

.recipe-chip:hover {
  border-color: rgb(var(--v-theme-on-background));
}
</style>
