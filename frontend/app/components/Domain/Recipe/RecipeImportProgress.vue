<template>
  <div class="import-progress" role="status" aria-live="polite">
    <div class="import-progress__head">
      <v-progress-circular
        indeterminate
        size="18"
        width="2"
        color="tomato"
      />
      <span class="import-progress__title">{{ title }}</span>
      <span class="import-progress__time" :aria-label="$t('recipe-import.elapsed-time')">{{ elapsed }}</span>
    </div>
    <ol class="import-progress__steps">
      <li
        v-for="(step, index) in steps"
        :key="index"
        class="import-progress__step"
        :class="{ 'import-progress__step--current': index === steps.length - 1 }"
      >
        <v-icon
          v-if="index < steps.length - 1"
          size="16"
          class="import-progress__check"
          :icon="$globals.icons.check"
        />
        <span v-else class="import-progress__dot" aria-hidden="true" />
        {{ step }}
      </li>
    </ol>
    <p v-if="note && seconds >= NOTE_AFTER_SECONDS" class="import-progress__note">
      {{ note }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { useIntervalFn } from "@vueuse/core";

const props = defineProps<{
  title: string;
  steps: string[];
  /** When the import started, in milliseconds */
  startedAt: number;
  /** Shown once the import has taken a while, e.g. that videos are slow */
  note?: string;
}>();

const NOTE_AFTER_SECONDS = 8;

const now = ref(Date.now());
useIntervalFn(() => (now.value = Date.now()), 1000);

const seconds = computed(() => Math.max(0, Math.floor((now.value - props.startedAt) / 1000)));
const elapsed = computed(() => `${Math.floor(seconds.value / 60)}:${String(seconds.value % 60).padStart(2, "0")}`);
</script>

<style scoped>
.import-progress {
  width: 100%;
  padding: 4px 8px 2px;
}

.import-progress__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-progress__title {
  font-weight: 600;
}

.import-progress__time {
  margin-left: auto;
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--v-theme-ink-muted));
}

.import-progress__steps {
  margin: 10px 0 0;
  padding: 0 0 0 28px;
  list-style: none;
}

.import-progress__step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
}

.import-progress__step--current {
  color: rgb(var(--v-theme-on-surface));
}

.import-progress__check {
  color: rgb(var(--v-theme-sage));
}

.import-progress__dot {
  display: inline-block;
  width: 16px;
  height: 16px;
  flex: none;
  position: relative;
}

.import-progress__dot::after {
  content: "";
  position: absolute;
  inset: 5px;
  border-radius: 999px;
  background: rgb(var(--v-theme-tomato));
  animation: import-progress-pulse 1.2s ease-in-out infinite;
}

.import-progress__note {
  margin: 8px 0 0 28px;
  font-family: var(--paper-serif);
  font-style: italic;
  font-size: 0.9375rem;
  color: rgb(var(--v-theme-ink-muted));
}

@keyframes import-progress-pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .import-progress__dot::after {
    animation: none;
  }
}
</style>
