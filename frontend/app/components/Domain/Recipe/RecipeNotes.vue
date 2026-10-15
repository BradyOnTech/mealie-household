<template>
  <div
    v-if="model.length > 0 || edit"
    class="mt-8"
  >
    <h2 class="recipe-notes__title">
      {{ $t("recipe.notes") }}
    </h2>
    <div
      v-for="(note, index) in model"
      :id="'note' + index"
      :key="'note' + index"
      class="mt-1"
    >
      <v-card v-if="edit">
        <v-card-text>
          <div class="d-flex align-center">
            <v-text-field
              v-model="model[index]['title']"
              variant="underlined"
              :label="$t('recipe.title')"
            />
            <v-btn
              icon
              class="mr-2"
              elevation="0"
              @click="removeByIndex(index)"
            >
              <v-icon>{{ $globals.icons.delete }}</v-icon>
            </v-btn>
          </div>
          <v-textarea
            v-model="model[index]['text']"
            variant="underlined"
            auto-grow
            :placeholder="$t('recipe.note')"
          />
        </v-card-text>
      </v-card>
      <div v-else class="recipe-note">
        <div v-if="note.title" class="recipe-note__title">
          {{ note.title }}
        </div>
        <SafeMarkdown class="recipe-note__text" :source="note.text" />
      </div>
    </div>

    <div
      v-if="edit"
      class="d-flex justify-end"
    >
      <BaseButton
        class="ml-auto my-2"
        @click="addNote"
      >
        {{ $t("general.add") }}
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { uuid4 } from "~/composables/use-utils";
import type { RecipeNote } from "~/lib/api/types/recipe";

const model = defineModel<RecipeNote[]>({ default: () => [] });

defineProps({
  edit: {
    type: Boolean,
    default: true,
  },
});

function addNote() {
  model.value = [...model.value, { title: "", text: "", referenceId: uuid4() }];
}

function removeByIndex(index: number) {
  const newNotes = [...model.value];
  newNotes.splice(index, 1);
  model.value = newNotes;
}
</script>

<style scoped>
.recipe-notes__title {
  margin: 0 0 14px;
  padding-bottom: 4px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 450;
  letter-spacing: -0.01em;
}

.recipe-note {
  margin: 0 0 14px;
  padding: 2px 0 2px 16px;
  border-left: 2px solid rgb(var(--v-theme-tomato));
}

.recipe-note__title {
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  font-weight: 500;
}

.recipe-note__text {
  font-family: var(--paper-serif);
  font-style: italic;
  font-size: 1rem;
  line-height: 1.55;
  color: rgb(var(--v-theme-ink-muted));
}
</style>
