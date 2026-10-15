<template>
  <v-card
    :min-width="minWidth"
    :to="to"
    variant="outlined"
    class="stat-card"
    :class="{ 'stat-card--link': !!to }"
  >
    <div class="stat-card__body">
      <v-icon class="stat-card__icon" size="18">
        {{ activeIcon }}
      </v-icon>
      <div class="stat-card__value">
        <slot name="value" />
      </div>
      <div class="stat-card__label">
        <slot name="title" />
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
const props = defineProps({
  icon: {
    type: String,
    default: null,
  },
  minWidth: {
    type: String,
    default: "",
  },
  to: {
    type: String,
    default: null,
  },
});

const { $globals } = useNuxtApp();

const activeIcon = computed(() => {
  return props.icon ?? $globals.icons.primary;
});
</script>

<style scoped>
.stat-card {
  background: rgb(var(--v-theme-surface));
}

.stat-card__body {
  display: flex;
  flex-direction: column;
  padding: 14px 16px 12px;
}

.stat-card__icon {
  margin-bottom: 8px;
  color: rgb(var(--v-theme-tomato));
}

.stat-card__value {
  font-family: var(--paper-serif);
  font-optical-sizing: auto;
  font-size: 2rem;
  font-weight: 400;
  line-height: 1;
}

.stat-card__label {
  margin-top: 6px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-ink-muted));
}

.stat-card--link:hover .stat-card__value {
  color: rgb(var(--v-theme-tomato));
}
</style>
