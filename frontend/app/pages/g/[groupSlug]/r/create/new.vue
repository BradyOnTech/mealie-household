<template>
  <div class="recipe-write">
    <header class="recipe-write__head">
      <span class="paper-kicker">{{ $t("recipe-import.kicker") }}</span>
      <h1 class="paper-headline recipe-write__title">
        {{ $t("recipe-import.write-title") }}
      </h1>
      <p class="paper-dek recipe-write__dek">
        {{ $t("recipe-import.write-dek") }}
      </p>
    </header>

    <v-form ref="domCreateByName" class="recipe-write__form" @submit.prevent="createByName">
      <v-text-field
        v-model="newRecipeName"
        :label="$t('recipe.recipe-name')"
        :rules="[validators.required]"
        :error-messages="state.error ? [$t('recipe-import.write-name-taken')] : []"
        :hint="$t('recipe.new-recipe-names-must-be-unique')"
        persistent-hint
        variant="outlined"
        autofocus
        validate-on="submit"
        @update:model-value="state.error = false"
      />
      <v-btn
        type="submit"
        color="primary"
        variant="flat"
        size="large"
        class="recipe-write__submit"
        :loading="state.loading"
        :disabled="!newRecipeName.trim()"
      >
        {{ $t("recipe-import.write-submit") }}
        <v-icon end :icon="$globals.icons.arrowRight" />
      </v-btn>
    </v-form>

    <p class="recipe-write__import">
      {{ $t("recipe-import.write-or-import") }}
      <NuxtLink :to="`/g/${groupSlug}/r/create/url`" class="paper-link">{{ $t("recipe-import.write-import-link") }}</NuxtLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import { validators } from "~/composables/use-validators";
import type { VForm } from "~/types/auto-forms";

definePageMeta({
  key: route => route.path,
});

const i18n = useI18n();
const auth = useMealieAuth();
const route = useRoute();
const router = useRouter();
const api = useUserApi();

useSeoMeta({ title: i18n.t("recipe-import.write-title") });

const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");

const state = reactive({
  error: false,
  loading: false,
});
const newRecipeName = ref("");
const domCreateByName = ref<VForm | null>(null);

async function createByName() {
  const name = newRecipeName.value.trim();
  const validation = await domCreateByName.value?.validate();
  if (!name || validation?.valid === false) {
    return;
  }

  state.loading = true;
  const { response } = await api.recipes.createOne({ name });
  state.loading = false;

  if (response?.status !== 201) {
    state.error = true;
    return;
  }
  router.push(`/g/${groupSlug.value}/r/${response.data}?edit=true`);
}
</script>

<style scoped>
.recipe-write {
  max-width: 760px;
  margin: 0 auto;
  padding: 40px 0 72px;
}

.recipe-write__head {
  margin-bottom: 28px;
}

.recipe-write__title {
  margin: 6px 0 0;
  font-size: 3rem;
}

.recipe-write__dek {
  max-width: 54ch;
  margin: 10px 0 0;
  font-size: 1.125rem;
}

.recipe-write__form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
}

.recipe-write__form > :first-child {
  flex: 1 1 320px;
}

.recipe-write__submit {
  margin-top: 4px;
  padding-inline: 22px;
}

.recipe-write__import {
  margin-top: 28px;
  color: rgb(var(--v-theme-ink-muted));
}

@media (max-width: 599px) {
  .recipe-write {
    padding-top: 20px;
  }

  .recipe-write__title {
    font-size: 2.25rem;
  }

  .recipe-write__submit {
    width: 100%;
  }
}
</style>
