<template>
  <div class="recipe-debug">
    <header class="recipe-debug__head">
      <NuxtLink :to="`/g/${groupSlug}/r/create/url`" class="paper-kicker recipe-debug__back">
        {{ $t("recipe-import.title") }}
      </NuxtLink>
      <h1 class="paper-headline recipe-debug__title">
        {{ $t('recipe.recipe-debugger') }}
      </h1>
      <p class="paper-dek recipe-debug__dek">
        {{ $t('recipe.recipe-debugger-description') }}
      </p>
    </header>
    <v-form
      ref="domUrlForm"
      @submit.prevent="debugUrl(recipeUrl)"
    >
      <v-text-field
        v-model="recipeUrl"
        :label="$t('new-recipe.recipe-url')"
        validate-on="blur"
        :prepend-inner-icon="$globals.icons.link"
        autofocus
        variant="outlined"
        clearable
        :rules="[validators.url]"
      />
      <template v-if="group?.aiProviderSettings?.aiEnabled">
        <v-checkbox
          v-model="state.useOpenAI"
          :label="$t('recipe.use-openai')"
          :hint="$t('recipe.recipe-debugger-use-openai-description')"
          persistent-hint
          color="primary"
        />
      </template>
      <v-btn
        :disabled="!recipeUrl"
        type="submit"
        color="primary"
        variant="flat"
        size="large"
        class="mt-4"
        :loading="state.loading"
        :prepend-icon="$globals.icons.robot"
      >
        {{ $t('recipe.debug') }}
      </v-btn>
    </v-form>
    <section v-if="debugData" class="mt-8">
      <v-checkbox
        v-model="debugTreeView"
        :label="$t('recipe.tree-view')"
        color="primary"
      />
      <RecipeJsonEditor
        v-model="debugData"
        height="700px"
        :mode="debugTreeView ? 'tree' : 'text'"
        :main-menu-bar="false"
        :read-only="true"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import { useGroupSelf } from "~/composables/use-groups";
import { validators } from "~/composables/use-validators";
import type { Recipe } from "~/lib/api/types/recipe";

const state = reactive({
  loading: false,
  useOpenAI: false,
});

const api = useUserApi();
const auth = useMealieAuth();
const route = useRoute();
const router = useRouter();
const { group } = useGroupSelf();
const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");

const recipeUrl = computed({
  set(recipe_import_url: string | null) {
    if (recipe_import_url !== null) {
      recipe_import_url = recipe_import_url.trim();
      router.replace({ query: { ...route.query, recipe_import_url } });
    }
  },
  get() {
    return route.query.recipe_import_url as string | null;
  },
});

const debugTreeView = ref(false);

const debugData = ref<Recipe | null>(null);

async function debugUrl(url: string | null) {
  if (url === null) {
    return;
  }

  state.loading = true;

  const { data } = await api.recipes.testCreateOneUrl(url, state.useOpenAI);

  state.loading = false;
  debugData.value = data;
}
</script>

<style scoped>
.recipe-debug {
  max-width: 760px;
  margin: 0 auto;
  padding: 40px 0 72px;
}

.recipe-debug__head {
  margin-bottom: 24px;
}

.recipe-debug__back {
  text-decoration: none;
}

.recipe-debug__title {
  margin: 6px 0 0;
  font-size: 2.5rem;
}

.recipe-debug__dek {
  max-width: 60ch;
  margin: 10px 0 0;
}

@media (max-width: 599px) {
  .recipe-debug {
    padding-top: 20px;
  }

  .recipe-debug__title {
    font-size: 2rem;
  }
}
</style>
