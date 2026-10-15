<template>
  <v-img
    v-if="showImage"
    :height="height"
    cover
    :min-height="minHeight"
    max-height="fill-height"
    :src="getImage(recipeId)"
    @click="$emit('click')"
    @load="fallBackImage = false"
    @error="fallBackImage = true"
  >
    <slot />
  </v-img>
  <div
    v-else
    class="recipe-image-empty"
    :style="{ height: cssSize(height), minHeight: cssSize(minHeight) }"
    @click="$emit('click')"
  >
    <v-icon
      class="recipe-image-empty__glyph"
      :size="glyphSize"
    >
      {{ $globals.icons.primary }}
    </v-icon>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { useStaticRoutes } from "~/composables/api";

interface Props {
  tiny?: boolean | null;
  small?: boolean | null;
  large?: boolean | null;
  iconSize?: number | string;
  slug?: string | null;
  recipeId: string;
  // Recipe.image is typed unknown in the generated API types, so callers
  // passing it directly cannot narrow to string here.
  imageVersion?: unknown;
  height?: number | string;
  minHeight?: number | string;
}
const props = withDefaults(defineProps<Props>(), {
  tiny: null,
  small: null,
  large: null,
  iconSize: 100,
  slug: null,
  imageVersion: null,
  height: "100%",
  minHeight: 125,
});

defineEmits<{
  click: [];
}>();

const { recipeImage, recipeSmallImage, recipeTinyImage } = useStaticRoutes();

const fallBackImage = ref(false);

// Recipes without an image have no image version, so there is nothing to fetch.
// Rendering the image anyway would only produce a 404 before falling back.
const showImage = computed(() => !!props.imageVersion && !fallBackImage.value);

const imageSize = computed(() => {
  if (props.tiny) return "tiny";
  if (props.small) return "small";
  if (props.large) return "large";
  return "large";
});

watch(
  [() => props.recipeId, () => props.imageVersion],
  () => {
    fallBackImage.value = false;
  },
);

// Recipes without photos get a quiet paper block rather than a full-size icon.
const glyphSize = computed(() => Math.min(Number(props.iconSize) || 64, 64));

function cssSize(value: number | string) {
  return typeof value === "number" || /^\d+$/.test(value) ? `${value}px` : value;
}

function getImage(recipeId: string) {
  switch (imageSize.value) {
    case "tiny":
      return recipeTinyImage(recipeId, props.imageVersion);
    case "small":
      return recipeSmallImage(recipeId, props.imageVersion);
    case "large":
      return recipeImage(recipeId, props.imageVersion);
  }
}
</script>

<style scoped>
.recipe-image-empty {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  border-radius: 2px;
  background: rgb(var(--v-theme-surface-light));
}

.recipe-image-empty > div {
  top: 0;
  position: absolute;
  z-index: 1;
}

.recipe-image-empty__glyph {
  color: rgb(var(--v-theme-ink-muted));
  opacity: 0.45;
}
</style>
