<template>
  <v-tooltip
    location="bottom"
    nudge-right="50"
  >
    <template #activator="{ props: activatorProps }">
      <v-btn
        icon
        :variant="buttonStyle ? 'outlined' : 'text'"
        :rounded="buttonStyle ? 'circle' : undefined"
        :size="buttonStyle ? 'default' : 'small'"
        :class="buttonStyle ? 'recipe-action-circle' : 'recipe-action-quiet'"
        :fab="buttonStyle"
        :aria-label="$t('recipe.open-timeline')"
        v-bind="{ ...activatorProps, ...$attrs }"
        @click.prevent="toggleTimeline"
      >
        <v-icon>
          {{ $globals.icons.timelineText }}
        </v-icon>
      </v-btn>
      <BaseDialog
        v-model="showTimeline"
        :title="$t('recipe.timeline')"
        :icon="$globals.icons.timelineText"
        width="70%"
      >
        <RecipeTimeline
          v-model="showTimeline"
          :query-filter="timelineAttrs.queryFilter"
        />
      </BaseDialog>
    </template>
    <span>{{ $t('recipe.open-timeline') }}</span>
  </v-tooltip>
</template>

<script setup lang="ts">
import RecipeTimeline from "./RecipeTimeline.vue";

interface Props {
  buttonStyle?: boolean;
  slug?: string;
  recipeName?: string;
}
const props = withDefaults(defineProps<Props>(), {
  buttonStyle: false,
  slug: "",
  recipeName: "",
});

const showTimeline = ref(false);

function toggleTimeline() {
  showTimeline.value = !showTimeline.value;
}

const timelineAttrs = computed(() => {
  return {
    queryFilter: `recipe.slug="${props.slug}"`,
  };
});
</script>
