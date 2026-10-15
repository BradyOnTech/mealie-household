<template>
  <v-app>
    <main class="error-page">
      <span class="paper-kicker">{{ error.statusCode }}</span>
      <h1 class="error-page__title paper-headline">
        {{ notFound ? $t("page.not-found-title") : $t("page.an-error-occurred") }}
      </h1>
      <p v-if="notFound" class="error-page__dek paper-dek">
        {{ $t("page.not-found-detail") }}
      </p>
      <v-btn
        color="primary"
        size="large"
        :prepend-icon="$globals.icons.home"
        @click="goHome"
      >
        {{ $t("general.home") }}
      </v-btn>
    </main>
  </v-app>
</template>

<script setup lang="ts">
import type { NuxtError } from "#app";

const props = defineProps<{ error: NuxtError }>();

const i18n = useI18n();
const notFound = computed(() => props.error.statusCode === 404);

useSeoMeta({
  title: notFound.value ? i18n.t("page.404-not-found") : i18n.t("page.an-error-occurred"),
});

function goHome() {
  clearError({ redirect: "/" });
}
</script>

<style scoped>
.error-page {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  width: 100%;
  max-width: 720px;
  min-height: 100vh;
  margin: 0 auto;
  padding: 48px var(--paper-gutter);
}

.error-page__title {
  margin: 10px 0 14px;
  font-size: 3.5rem;
}

.error-page__dek {
  margin: 0 0 28px;
  font-size: 1.1875rem;
}

@media (max-width: 599px) {
  .error-page__title {
    font-size: 2.5rem;
  }
}
</style>
