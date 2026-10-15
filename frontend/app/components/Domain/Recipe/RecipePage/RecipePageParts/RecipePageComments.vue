<template>
  <div>
    <h2 class="recipe-comments__title">
      {{ $t("recipe.comments") }}
    </h2>
    <div
      v-if="user.id"
      class="d-flex flex-column"
    >
      <div
        class="d-flex mt-3"
        style="gap: 10px"
      >
        <UserAvatar
          :tooltip="false"
          size="40"
          :user-id="user.id"
        />

        <v-textarea
          v-model="comment"
          hide-details
          density="compact"
          single-line
          variant="outlined"
          auto-grow
          rows="2"
          :placeholder="$t('recipe.join-the-conversation')"
        />
      </div>
      <div class="ml-auto mt-1">
        <BaseButton
          size="small"
          :disabled="!comment.trim()"
          @click="submitComment"
        >
          <template #icon>
            {{ $globals.icons.check }}
          </template>
          {{ $t("general.submit") }}
        </BaseButton>
      </div>
    </div>
    <div
      v-for="recipeComment in recipe.comments"
      :key="recipeComment.id"
      class="d-flex my-2"
      style="gap: 10px"
    >
      <UserAvatar
        :tooltip="false"
        size="40"
        :user-id="recipeComment.userId"
      />
      <v-card
        variant="outlined"
        class="flex-grow-1"
      >
        <v-card-text class="pa-3 pb-0">
          <p class="">
            {{ recipeComment.user.fullName }} • {{ $d(Date.parse(recipeComment.createdAt), "medium") }}
          </p>
          <SafeMarkdown :source="recipeComment.text" />
        </v-card-text>
        <v-card-actions class="justify-end mt-0 pt-0">
          <v-btn
            v-if="user.id == recipeComment.user.id || user.admin"
            color="error"
            variant="text"
            size="x-small"
            @click="deleteComment(recipeComment.id)"
          >
            {{ $t("general.delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import type { Recipe } from "~/lib/api/types/recipe";
import UserAvatar from "~/components/Domain/User/UserAvatar.vue";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import { usePageUser } from "~/composables/recipe-page/shared-state";
import SafeMarkdown from "~/components/global/SafeMarkdown.vue";

const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });
const api = useUserApi();
const { user } = usePageUser();
const comment = ref("");

async function submitComment() {
  const text = comment.value.trim();
  if (!text) {
    return;
  }
  const { data } = await api.recipes.comments.createOne({
    recipeId: recipe.value.id,
    text,
  });

  if (data) {
    recipe.value.comments.push(data);
  }

  comment.value = "";
}

async function deleteComment(id: string) {
  const { response } = await api.recipes.comments.deleteOne(id);

  if (response?.status === 200) {
    recipe.value.comments = recipe.value.comments.filter(comment => comment.id !== id);
  }
}
</script>

<style scoped>
.recipe-comments__title {
  margin: 0 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 450;
  letter-spacing: -0.01em;
}
</style>
