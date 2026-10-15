<template>
  <div
    class="recipe-row"
    :class="{
      'recipe-row--vertical': vertical,
      'recipe-row--flat': isFlat,
      'recipe-row--link': !!linkTarget,
      'disable-highlight': disableHighlight,
    }"
    :style="{ cursor }"
  >
    <component
      :is="linkTarget ? NuxtLink : 'div'"
      :to="linkTarget"
      class="recipe-row__figure"
      tabindex="-1"
      @click="$emit('selected')"
    >
      <slot v-if="!vertical" name="avatar">
        <RecipeCardImage
          tiny
          :icon-size="40"
          :slug="slug"
          :recipe-id="recipeId"
          :image-version="image"
          :height="72"
          :min-height="72"
        />
      </slot>
      <RecipeCardImage
        v-else
        small
        :icon-size="64"
        :slug="slug"
        :recipe-id="recipeId"
        :image-version="image"
        :height="height"
        :min-height="height"
      />
    </component>
    <div class="recipe-row__body">
      <span v-if="kicker" class="paper-kicker recipe-row__kicker">{{ kicker }}</span>
      <component
        :is="linkTarget ? NuxtLink : 'span'"
        :to="linkTarget"
        class="recipe-row__title"
        @click="$emit('selected')"
      >
        {{ name }}
      </component>
      <p v-if="plainDescription" class="recipe-row__dek">
        {{ plainDescription }}
      </p>
      <slot name="actions">
        <div v-if="showRecipeContent" class="recipe-row__actions">
          <RecipeCardRating
            :model-value="rating"
            :recipe-id="recipeId"
          />
          <v-spacer />
          <RecipeFavoriteBadge
            v-if="isOwnGroup"
            :recipe-id="recipeId"
            show-always
          />
          <!-- If we're not logged-in, no items display, so we hide this menu -->
          <slot name="context-menu">
            <RecipeContextMenu
              v-if="isOwnGroup"
              :slug="slug"
              :menu-icon="$globals.icons.dotsHorizontal"
              :name="name"
              :recipe-id="recipeId"
              :use-items="{
                delete: false,
                edit: false,
                download: true,
                mealplanner: true,
                shoppingList: true,
                print: false,
                printPreferences: false,
                share: true,
              }"
              :leading-items="contextMenuLeadingItems"
              :append-items="contextMenuAppendItems"
              @deleted="$emit('delete', slug)"
              @mealplan-remove="$emit('mealplanRemove')"
              @mealplan-edit="$emit('mealplanEdit')"
            />
          </slot>
        </div>
      </slot>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { plainTextExcerpt } from "~/lib/sanitize/text";
import RecipeCardImage from "./RecipeCardImage.vue";
import RecipeCardRating from "./RecipeCardRating.vue";
import RecipeContextMenu from "./RecipeContextMenu/RecipeContextMenu.vue";
import RecipeFavoriteBadge from "./RecipeFavoriteBadge.vue";
import type { ContextMenuItem } from "./RecipeContextMenu/RecipeContextMenu.vue";

// Resolved by name so the template can switch between a link and a plain element.
const NuxtLink = resolveComponent("NuxtLink");

interface Props {
  name: string;
  slug: string;
  description: string;
  rating?: number;
  image?: string;
  tags?: Array<any>;
  recipeId: string;
  vertical?: boolean;
  isFlat?: boolean;
  height?: number;
  disableHighlight?: boolean;
  contextMenuAppendItems?: ContextMenuItem[];
  contextMenuLeadingItems?: ContextMenuItem[];
}
const props = withDefaults(defineProps<Props>(), {
  rating: 0,
  image: undefined,
  tags: () => [],
  vertical: false,
  isFlat: false,
  height: 150,
  disableHighlight: false,
});

defineEmits<{
  mealplanRemove: [];
  mealplanEdit: [];
  selected: [];
  delete: [slug: string];
}>();

const attrs = useAttrs();
const auth = useMealieAuth();
const { isOwnGroup } = useLoggedInState();

const route = useRoute();
const groupSlug = computed(() => route.params.groupSlug || auth.user.value?.groupSlug || "");
const showRecipeContent = computed(() => !!(props.recipeId && props.slug));
const recipeRoute = computed<string>(() => {
  return showRecipeContent.value ? `/g/${groupSlug.value}/r/${props.slug}` : "";
});
// In pickers ("selected" is bound) a click chooses the recipe instead of opening it.
const linkTarget = computed(() => (attrs.selected || !recipeRoute.value ? undefined : recipeRoute.value));
const cursor = computed(() => (showRecipeContent.value || attrs.selected ? "pointer" : "auto"));

const kicker = computed(() => props.tags.slice(0, 2).map(tag => tag.name).join(" · "));
const plainDescription = computed(() => plainTextExcerpt(props.description || "", 110));
</script>

<style scoped>
.recipe-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.recipe-row--flat {
  border-bottom: 0;
}

.recipe-row--vertical {
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
}

.recipe-row__figure {
  display: block;
  overflow: hidden;
  border-radius: 2px;
}

.recipe-row__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.recipe-row__kicker {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recipe-row__title {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-size: 1.125rem;
  font-weight: 420;
  line-height: 1.22;
  letter-spacing: -0.005em;
  color: rgb(var(--v-theme-on-background));
  text-decoration: none;
}

.recipe-row--link a.recipe-row__title:hover {
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}

.recipe-row__dek {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  line-clamp: 1;
  overflow: hidden;
  margin: 3px 0 0;
  font-size: 0.8125rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.recipe-row__actions {
  display: flex;
  align-items: center;
  margin-top: 2px;
  margin-bottom: -6px;
}
</style>
