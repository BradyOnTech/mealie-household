<template>
  <div class="plan-day-head" :class="{ 'plan-day-head--today': isToday(day) }">
    <div class="plan-day-head__date">
      <span class="plan-day-head__weekday">{{ weekday }}</span>
      <span class="plan-day-head__num">{{ day.getDate() }}</span>
      <span class="plan-day-head__month">{{ month }}</span>
      <span v-if="isToday(day)" class="paper-kicker plan-day-head__today">{{ $t("this-week.today") }}</span>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { isSameDay } from "date-fns";

interface Props {
  day: Date;
};
const props = defineProps<Props>();

const { locale } = useI18n();

const weekday = computed(() => new Intl.DateTimeFormat(locale.value, { weekday: "short" }).format(props.day));
const month = computed(() => new Intl.DateTimeFormat(locale.value, { month: "short" }).format(props.day));

const isToday = (date: Date) => {
  return isSameDay(date, new Date());
};
</script>

<style scoped>
.plan-day-head {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  border-bottom: 1px solid rgb(var(--v-theme-on-background));
}

.plan-day-head__date {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.plan-day-head__weekday,
.plan-day-head__month {
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.plan-day-head__num {
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-size: 1.875rem;
  font-weight: 400;
  line-height: 1;
}

.plan-day-head--today .plan-day-head__num {
  color: rgb(var(--v-theme-tomato));
}

.plan-day-head__today {
  margin-left: 4px;
}
</style>
