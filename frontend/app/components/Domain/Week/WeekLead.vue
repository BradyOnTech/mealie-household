<template>
  <article class="week-lead">
    <template v-if="lead?.recipe">
      <NuxtLink :to="recipeLink(lead.recipe.slug)" class="week-lead__figure" tabindex="-1" aria-hidden="true">
        <img
          v-if="lead.recipe.image && !imageFailed"
          :src="recipeImage(lead.recipe.id!, lead.recipe.image)"
          alt=""
          class="week-lead__image paper-image"
          @error="imageFailed = true"
        >
        <div v-else class="week-lead__image week-lead__image--empty">
          <span>{{ lead.recipe.name?.charAt(0) }}</span>
        </div>
      </NuxtLink>
      <div class="week-lead__body">
        <span class="paper-kicker">{{ $t("this-week.tonight") }}</span>
        <h1 class="week-lead__title paper-headline">
          <NuxtLink :to="recipeLink(lead.recipe.slug)">{{ lead.recipe.name }}</NuxtLink>
        </h1>
        <p v-if="lead.recipe.description" class="week-lead__dek paper-dek">
          {{ lead.recipe.description }}
        </p>
        <p v-if="sides.length" class="week-lead__sides">
          {{ $t("this-week.with", { items: listFormat(sides) }) }}
        </p>
        <div class="week-lead__foot">
          <div class="paper-meta week-lead__meta">
            <span v-if="lead.recipe.totalTime">{{ lead.recipe.totalTime }}</span>
            <span v-if="lead.recipe.recipeServings">{{ $t("this-week.serves", { count: lead.recipe.recipeServings }) }}</span>
            <span v-if="lead.recipe.lastMade">{{ $t("this-week.last-made", { date: shortDate(lead.recipe.lastMade) }) }}</span>
          </div>
          <NuxtLink :to="recipeLink(lead.recipe.slug)" class="paper-link">
            {{ $t("this-week.read-recipe") }}
          </NuxtLink>
          <v-btn
            color="primary"
            size="large"
            :to="`${recipeLink(lead.recipe.slug)}?cook=true`"
          >
            {{ $t("this-week.start-cooking") }}
          </v-btn>
        </div>
      </div>
    </template>

    <div v-else class="week-lead__plain">
      <span class="paper-kicker">{{ $t("this-week.tonight") }}</span>
      <template v-if="lead">
        <h1 class="week-lead__title week-lead__title--plain paper-headline">
          {{ lead.title }}
        </h1>
        <p v-if="lead.text" class="week-lead__dek paper-dek">
          {{ lead.text }}
        </p>
        <p v-if="sides.length" class="week-lead__sides">
          {{ $t("this-week.with", { items: listFormat(sides) }) }}
        </p>
      </template>
      <template v-else>
        <h1 class="week-lead__title week-lead__title--plain paper-headline">
          {{ $t("this-week.nothing-tonight") }}
        </h1>
        <p class="week-lead__dek paper-dek">
          {{ $t("this-week.nothing-tonight-detail") }}
        </p>
        <div v-if="suggestions.length" class="week-lead__ideas">
          <div
            v-for="idea in suggestions.slice(0, 3)"
            :key="idea.recipe.id ?? idea.recipe.slug ?? ''"
            class="week-lead__idea"
          >
            <NuxtLink :to="recipeLink(idea.recipe.slug)" class="week-lead__idea-figure" tabindex="-1" aria-hidden="true">
              <img
                v-if="idea.recipe.image"
                :src="recipeSmallImage(idea.recipe.id!, idea.recipe.image)"
                alt=""
                class="paper-image"
              >
            </NuxtLink>
            <div class="week-lead__idea-body">
              <NuxtLink :to="recipeLink(idea.recipe.slug)" class="week-lead__idea-title">
                {{ idea.recipe.name }}
              </NuxtLink>
              <div class="week-lead__idea-reason">
                {{ idea.reasons.join(" · ") }}
              </div>
            </div>
            <v-btn
              variant="outlined"
              :loading="busy"
              :disabled="busy"
              @click="emit('plan', idea.recipe.id!)"
            >
              {{ $t("this-week.plan-tonight") }}
            </v-btn>
          </div>
        </div>
      </template>
    </div>
  </article>
</template>

<script setup lang="ts">
import { useStaticRoutes } from "~/composables/api";
import { accompaniments, leadDinner, type WeekDay } from "~/composables/use-household-week";
import type { GrocerySuggestionOut } from "~/lib/api/types/grocery";

const props = defineProps<{
  day: WeekDay;
  suggestions: GrocerySuggestionOut[];
  groupSlug: string;
  busy?: boolean;
}>();

const emit = defineEmits<{
  (e: "plan", recipeId: string): void;
}>();

const { locale } = useI18n();
const { recipeImage, recipeSmallImage } = useStaticRoutes();

const lead = computed(() => leadDinner(props.day));
const sides = computed(() => accompaniments(props.day));
const imageFailed = ref(false);

function recipeLink(slug?: string | null) {
  return `/g/${props.groupSlug}/r/${slug}`;
}

function listFormat(items: string[]) {
  return new Intl.ListFormat(locale.value, { style: "long", type: "conjunction" }).format(items);
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat(locale.value, { month: "short", day: "numeric" }).format(new Date(value));
}
</script>

<style scoped>
.week-lead__figure {
  display: block;
}

.week-lead__image {
  height: 380px;
}

.week-lead__image--empty {
  display: grid;
  place-items: center;
  border-radius: 2px;
  background: rgb(var(--v-theme-surface-light));
  font-family: var(--paper-serif);
  font-size: 7rem;
  font-style: italic;
  color: rgb(var(--v-theme-ink-muted));
}

.week-lead__body {
  padding-top: 20px;
}

.week-lead__title {
  margin: 8px 0 12px;
  font-size: 3.25rem;
}

.week-lead__title a {
  color: inherit;
  text-decoration: none;
}

.week-lead__title a:hover {
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 6px;
}

.week-lead__title--plain {
  font-size: 3.5rem;
}

.week-lead__dek {
  margin: 0;
  max-width: 46ch;
  font-size: 1.1875rem;
}

.week-lead__sides {
  margin: 10px 0 0;
  font-size: 0.9375rem;
  color: rgb(var(--v-theme-ink-muted));
}

.week-lead__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px 22px;
  margin-top: 22px;
}

.week-lead__meta {
  margin-right: auto;
}

.week-lead__plain {
  padding: 36px 0 8px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.week-lead__ideas {
  margin-top: 28px;
  border-top: 1px solid rgb(var(--v-theme-on-background));
}

.week-lead__idea {
  display: grid;
  grid-template-columns: 72px 1fr auto;
  align-items: center;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.week-lead__idea-figure img,
.week-lead__idea-figure {
  display: block;
  width: 72px;
  height: 72px;
}

.week-lead__idea-figure {
  border-radius: 2px;
  background: rgb(var(--v-theme-surface-light));
}

.week-lead__idea-title {
  font-family: var(--paper-serif);
  font-size: 1.25rem;
  color: inherit;
  text-decoration: none;
}

.week-lead__idea-title:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}

.week-lead__idea-reason {
  margin-top: 2px;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
}

@media (max-width: 959px) {
  .week-lead__image {
    height: 260px;
  }

  .week-lead__title {
    font-size: 2.375rem;
  }

  .week-lead__title--plain {
    font-size: 2.5rem;
  }

  .week-lead__dek {
    font-size: 1.0625rem;
  }

  .week-lead__plain {
    padding-top: 20px;
  }

  .week-lead__idea {
    grid-template-columns: 56px 1fr;
  }

  .week-lead__idea-figure,
  .week-lead__idea-figure img {
    width: 56px;
    height: 56px;
  }

  .week-lead__idea .v-btn {
    grid-column: 2;
    justify-self: start;
  }
}
</style>
