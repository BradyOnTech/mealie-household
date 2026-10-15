<template>
  <article class="recipe-card" :class="{ 'recipe-card--link': showRecipeContent }">
    <component
      :is="showRecipeContent ? NuxtLink : 'div'"
      :to="showRecipeContent ? recipeRoute : undefined"
      class="recipe-card__figure"
      tabindex="-1"
      @click="$emit('click')"
    >
      <RecipeCardImage
        small
        :icon-size="imageHeight"
        :height="imageHeight"
        :min-height="imageHeight"
        :slug="slug"
        :recipe-id="recipeId"
        :image-version="image"
      />
    </component>
    <div class="recipe-card__body">
      <span v-if="kicker" class="paper-kicker recipe-card__kicker">{{ kicker }}</span>
      <component
        :is="showRecipeContent ? NuxtLink : 'span'"
        :to="showRecipeContent ? recipeRoute : undefined"
        class="recipe-card__title"
      >
        {{ name }}
      </component>
      <p v-if="plainDescription" class="recipe-card__dek">
        {{ plainDescription }}
      </p>
      <slot name="actions">
        <div v-if="showRecipeContent" class="recipe-card__actions">
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
          <RecipeContextMenu
            v-if="isOwnGroup"
            :slug="slug"
            :menu-icon="$globals.icons.dotsVertical"
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
            @deleted="$emit('delete', slug)"
          />
        </div>
      </slot>
    </div>
    <slot />
  </article>
</template>

<script setup lang="ts">
import RecipeFavoriteBadge from "./RecipeFavoriteBadge.vue";
import RecipeContextMenu from "./RecipeContextMenu/RecipeContextMenu.vue";
import RecipeCardImage from "./RecipeCardImage.vue";
import RecipeCardRating from "./RecipeCardRating.vue";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { plainTextExcerpt } from "~/lib/sanitize/text";

// Resolved by name so the template can switch between a link and a plain element.
const NuxtLink = resolveComponent("NuxtLink");

interface Props {
  name: string;
  slug: string;
  description?: string | null;
  rating?: number;
  ratingColor?: string;
  image?: string;
  tags?: Array<any>;
  recipeId: string;
  imageHeight?: number;
}
const props = withDefaults(defineProps<Props>(), {
  description: null,
  rating: 0,
  ratingColor: "secondary",
  image: undefined,
  tags: () => [],
  imageHeight: 220,
});

defineEmits<{
  click: [];
  delete: [slug: string];
}>();

const auth = useMealieAuth();
const { isOwnGroup } = useLoggedInState();

const route = useRoute();
const groupSlug = computed(() => route.params.groupSlug || auth.user.value?.groupSlug || "");
const showRecipeContent = computed(() => !!(props.recipeId && props.slug));
const recipeRoute = computed<string>(() => {
  return showRecipeContent.value ? `/g/${groupSlug.value}/r/${props.slug}` : "";
});

const kicker = computed(() => props.tags.slice(0, 2).map(tag => tag.name).join(" · "));
const plainDescription = computed(() => plainTextExcerpt(props.description || "", 140));
</script>

<style scoped>
.recipe-card {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.recipe-card__figure {
  display: block;
  overflow: hidden;
  border-radius: 2px;
}

.recipe-card__figure :deep(.v-img__img) {
  transition: transform 0.6s cubic-bezier(0.2, 0.7, 0.2, 1);
}

.recipe-card--link:hover .recipe-card__figure :deep(.v-img__img) {
  transform: scale(1.03);
}

.recipe-card__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  padding-top: 12px;
}

.recipe-card__kicker {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recipe-card__title {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  margin-top: 2px;
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-size: 1.3125rem;
  font-weight: 420;
  line-height: 1.2;
  letter-spacing: -0.01em;
  color: rgb(var(--v-theme-on-background));
  text-decoration: none;
}

a.recipe-card__title:hover {
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 4px;
}

.recipe-card__dek {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  margin: 6px 0 0;
  font-size: 0.875rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
}

.recipe-card__actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: auto;
  padding-top: 8px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
</style>
