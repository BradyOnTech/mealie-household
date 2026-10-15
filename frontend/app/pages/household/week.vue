<template>
  <div class="week-page">
    <div class="paper-container">
      <div class="week-dateline">
        <b>{{ longDate }}</b>
        <span>{{ $t("this-week.week-number", { week: weekNumber }) }}</span>
        <span class="week-dateline__spacer" />
        <span v-if="!loading">{{ summary }}</span>
      </div>

      <v-alert
        v-if="error"
        type="error"
        closable
        class="mt-6"
        @click:close="error = ''"
      >
        {{ error }}
      </v-alert>

      <v-progress-linear v-if="loading" indeterminate color="tomato" class="mt-8" />

      <div v-else class="week-grid">
        <WeekLead
          :day="tonight"
          :suggestions="suggestions[tonight.date] ?? []"
          :group-slug="groupSlug"
          :busy="busy"
          @plan="recipeId => plan(tonight.date, recipeId)"
        />
        <aside class="week-aside">
          <WeekAhead
            :days="ahead"
            :suggestions="suggestions"
            :group-slug="groupSlug"
            :busy="busy"
            @plan="plan"
          />
          <p v-if="earlierNames.length" class="week-earlier">
            {{ $t("this-week.earlier") }}: {{ earlierNames.join(", ") }}.
          </p>
          <WeekGroceries :view="groceries" />
        </aside>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import WeekAhead from "~/components/Domain/Week/WeekAhead.vue";
import WeekGroceries from "~/components/Domain/Week/WeekGroceries.vue";
import WeekLead from "~/components/Domain/Week/WeekLead.vue";
import { leadDinner, parsePlanDay, useHouseholdWeek } from "~/composables/use-household-week";
import { alert } from "~/composables/use-toast";

definePageMeta({ middleware: ["household-only"] });

const i18n = useI18n();
const auth = useMealieAuth();
useSeoMeta({ title: i18n.t("this-week.title") });

const groupSlug = computed(() => auth.user.value?.groupSlug ?? "");
const {
  today, weekNumber, tonight, earlier, ahead, thisWeek, groceries, suggestions, loading, busy, error, load, planDinner,
} = useHouseholdWeek();

const longDate = computed(() =>
  new Intl.DateTimeFormat(i18n.locale.value, { weekday: "long", month: "long", day: "numeric" }).format(today),
);

const summary = computed(() => {
  const planned = thisWeek.value.filter(day => leadDinner(day)).length;
  const open = thisWeek.value
    .filter(day => !day.isPast && !leadDinner(day))
    .map(day => new Intl.DateTimeFormat(i18n.locale.value, { weekday: "long" }).format(day.day));
  const parts = [i18n.t("this-week.dinners-planned", planned)];
  if (open.length) {
    const days = new Intl.ListFormat(i18n.locale.value, { style: "long", type: "conjunction" }).format(open);
    parts.push(i18n.t("this-week.open-nights", { days }));
  }
  return parts.join(" · ");
});

const earlierNames = computed(() =>
  earlier.value
    .map(day => leadDinner(day))
    .map(entry => entry?.recipe?.name || entry?.title || "")
    .filter(Boolean),
);

async function plan(date: string, recipeId: string) {
  if (await planDinner(date, recipeId)) {
    const day = new Intl.DateTimeFormat(i18n.locale.value, { weekday: "long" }).format(parsePlanDay(date));
    alert.success(i18n.t("this-week.added", { day }));
  }
}

onMounted(load);
</script>

<style scoped>
.week-page {
  padding-bottom: 72px;
}

.week-dateline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 22px;
  padding: 12px 0;
  border-bottom: 3px double rgb(var(--v-theme-rule));
  font-size: 0.71875rem;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.week-dateline b {
  font-weight: 600;
  color: rgb(var(--v-theme-on-background));
}

.week-dateline__spacer {
  flex: 1;
}

.week-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 352px;
  gap: 52px;
  padding-top: 28px;
}

.week-earlier {
  margin: 0;
  padding-top: 11px;
  font-size: 0.78125rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

@media (max-width: 959px) {
  .week-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 36px;
    padding-top: 20px;
  }

  .week-dateline__spacer {
    display: none;
  }

  .week-dateline {
    gap: 2px 14px;
  }
}
</style>
