<template>
  <div class="d-flex align-center flex-wrap ga-1 text-body-2 text-medium-emphasis">
    <span>{{ $t('recipe.parser.read-with-parser', { parser: parserText(currentParser) }) }}</span>
    <v-spacer />
    <BaseButton
      minor
      small
      color="info"
      :icon="$globals.icons.refresh"
      @click="open = true"
    >
      {{ $t('recipe.parser.select-parser') }}
    </BaseButton>
  </div>
  <v-alert
    v-if="showNlpLanguageHint"
    type="info"
    variant="tonal"
    density="compact"
    class="mt-2 text-body-2"
  >
    {{ $t("recipe.parser.natural-language-processor-english-only") }}
  </v-alert>
  <BaseDialog
    v-model="open"
    bottom-sheet
    :title="$t('recipe.parser.select-parser')"
    :icon="$globals.icons.fileSign"
  >
    <v-card-text class="pb-0">
      {{ $t('recipe.parser.select-parser-description') }}
    </v-card-text>
    <v-list lines="three">
      <v-list-item
        v-for="option in availableParsers.filter(({ hide }) => !hide)"
        :key="option.value"
        link
        :title="option.text"
        :subtitle="parserDescription(option.value as Parser)"
        :active="option.value === currentParser"
        :append-icon="option.value === currentParser ? $globals.icons.check : $globals.icons.chevronRight"
        @click="choose(option.value as Parser)"
      />
    </v-list>
  </BaseDialog>
</template>

<script setup lang="ts">
import type { MenuItem } from "~/components/global/BaseOverflowButton.vue";
import type { Parser } from "~/lib/api/user/recipes/recipe";

defineProps<{ availableParsers: MenuItem[]; showNlpLanguageHint: boolean }>();
const emit = defineEmits<{ parse: [] }>();
const currentParser = defineModel<Parser>({ default: "nlp" });

const { t } = useI18n();

function parserText(parser: Parser) {
  switch (parser) {
    case "brute": return t("recipe.parser.brute-parser");
    case "openai": return t("recipe.parser.openai-parser");
  }
  return t("recipe.parser.natural-language-processor");
}

function parserDescription(parser: Parser) {
  switch (parser) {
    case "brute": return t("recipe.parser.brute-parser-description");
    case "openai": return t("recipe.parser.openai-parser-description");
  }
  return t("recipe.parser.natural-language-processor-description");
}

const open = ref(false);

function choose(parser: Parser) {
  open.value = false;
  if (parser === currentParser.value) {
    // Same reader: read the lines again from scratch (the watch below won't fire)
    emit("parse");
    return;
  }
  currentParser.value = parser;
}

watch(currentParser, () => emit("parse"));
</script>
