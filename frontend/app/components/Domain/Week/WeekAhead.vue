<template>
  <section class="week-ahead">
    <h2 class="paper-section-title">
      {{ $t("this-week.week-ahead") }}
      <NuxtLink to="/household/mealplan/planner/edit" class="paper-section-aside week-ahead__edit">
        {{ $t("this-week.edit-plan") }}
      </NuxtLink>
    </h2>
    <template v-for="(day, index) in days" :key="day.date">
      <div v-if="startsNextWeek(index)" class="week-ahead__next paper-kicker">
        {{ $t("this-week.next-week") }}
      </div>
      <div class="week-ahead__row" :class="{ 'week-ahead__row--open': !leadOf(day) }">
        <div class="week-ahead__day">
          {{ weekday(day.day) }}
          <b>{{ day.day.getDate() }}</b>
        </div>
        <div class="week-ahead__main">
          <template v-if="leadOf(day)">
            <NuxtLink
              v-if="leadOf(day)!.recipe"
              :to="recipeLink(leadOf(day)!.recipe!.slug)"
              class="week-ahead__title"
            >
              {{ leadOf(day)!.recipe!.name }}
            </NuxtLink>
            <span v-else class="week-ahead__title">{{ leadOf(day)!.title }}</span>
            <div class="week-ahead__meta paper-meta">
              <span v-if="leadOf(day)!.recipe?.totalTime">{{ leadOf(day)!.recipe!.totalTime }}</span>
              <span v-if="leadOf(day)!.recipe?.recipeServings">
                {{ $t("this-week.serves", { count: leadOf(day)!.recipe!.recipeServings }) }}
              </span>
              <span v-if="accompaniments(day).length">
                {{ $t("this-week.with", { items: accompaniments(day).join(", ") }) }}
              </span>
            </div>
          </template>
          <template v-else>
            <span class="week-ahead__title">{{ $t("this-week.nothing-planned") }}</span>
            <div v-if="ideaFor(day)" class="week-ahead__meta">
              {{ $t("this-week.try-suggestion", { name: ideaFor(day)!.recipe.name }) }}
              <span v-if="ideaFor(day)!.reasons[0]">{{ ideaFor(day)!.reasons[0] }}.</span>
              <button
                type="button"
                class="paper-link week-ahead__add"
                :disabled="busy"
                @click="emit('plan', day.date, ideaFor(day)!.recipe.id!)"
              >
                {{ $t("this-week.add") }}
              </button>
            </div>
          </template>
        </div>
        <NuxtLink
          v-if="thumbFor(day)"
          :to="thumbFor(day)!.link"
          class="week-ahead__thumb"
          tabindex="-1"
          aria-hidden="true"
        >
          <img :src="thumbFor(day)!.src" alt="" class="paper-image">
        </NuxtLink>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useStaticRoutes } from "~/composables/api";
import { accompaniments, leadDinner, type WeekDay } from "~/composables/use-household-week";
import type { GrocerySuggestionOut } from "~/lib/api/types/grocery";

const props = defineProps<{
  days: WeekDay[];
  suggestions: Record<string, GrocerySuggestionOut[]>;
  groupSlug: string;
  busy?: boolean;
}>();

const emit = defineEmits<{
  (e: "plan", date: string, recipeId: string): void;
}>();

const { locale } = useI18n();
const { recipeSmallImage } = useStaticRoutes();

function leadOf(day: WeekDay) {
  return leadDinner(day);
}

function ideaFor(day: WeekDay) {
  return props.suggestions[day.date]?.[0];
}

function recipeLink(slug?: string | null) {
  return `/g/${props.groupSlug}/r/${slug}`;
}

function weekday(day: Date) {
  return new Intl.DateTimeFormat(locale.value, { weekday: "short" }).format(day);
}

/** A divider before the first day that belongs to next week. */
function startsNextWeek(index: number) {
  return index > 0 && props.days[index]!.day.getDay() === 1;
}

function thumbFor(day: WeekDay) {
  const recipe = leadOf(day)?.recipe ?? (leadOf(day) ? null : ideaFor(day)?.recipe);
  if (!recipe?.id || !recipe.image) {
    return null;
  }
  return { src: recipeSmallImage(recipe.id, recipe.image), link: recipeLink(recipe.slug) };
}
</script>

<style scoped>
.week-ahead__edit {
  text-decoration: none;
}

.week-ahead__edit:hover {
  color: rgb(var(--v-theme-on-background));
  text-decoration: underline;
  text-underline-offset: 3px;
}

.week-ahead__next {
  padding: 16px 0 2px;
}

.week-ahead__row {
  display: grid;
  grid-template-columns: 44px 1fr auto;
  align-items: center;
  gap: 14px;
  padding: 13px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.week-ahead__day {
  font-size: 0.65625rem;
  font-weight: 500;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.week-ahead__day b {
  display: block;
  font-family: var(--paper-serif);
  font-size: 1.5625rem;
  font-weight: 400;
  line-height: 1.05;
  letter-spacing: 0;
  color: rgb(var(--v-theme-on-background));
}

.week-ahead__main {
  min-width: 0;
}

.week-ahead__title {
  font-family: var(--paper-serif);
  font-size: 1.15625rem;
  line-height: 1.2;
  color: inherit;
  text-decoration: none;
}

a.week-ahead__title:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}

.week-ahead__row--open .week-ahead__title {
  font-style: italic;
  color: rgb(var(--v-theme-ink-muted));
}

.week-ahead__meta {
  margin-top: 3px;
  font-size: 0.78125rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
}

.week-ahead__add {
  appearance: none;
  border: 0;
  margin-left: 0.3em;
  padding: 0;
  background: none;
  font: inherit;
  font-weight: 600;
}

.week-ahead__add:disabled {
  opacity: 0.5;
  cursor: default;
}

.week-ahead__thumb,
.week-ahead__thumb img {
  display: block;
  width: 62px;
  height: 62px;
}

.week-ahead__row--open .week-ahead__thumb img {
  opacity: 0.55;
}
</style>
