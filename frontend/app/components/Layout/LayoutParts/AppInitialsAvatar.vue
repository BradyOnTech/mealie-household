<template>
  <span
    class="app-initials-avatar"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Number(size) * 0.46}px` }"
    aria-hidden="true"
  >
    {{ initials }}
  </span>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ name: string; size?: string | number }>(), {
  size: 36,
});

const initials = computed(() => {
  const words = props.name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) {
    return "·";
  }
  const first = words[0]!.charAt(0);
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : "";
  return `${first}${last}`.toUpperCase();
});
</script>

<style scoped>
.app-initials-avatar {
  display: inline-grid;
  flex: none;
  place-items: center;
  border-radius: 50%;
  background: rgb(var(--v-theme-sage));
  color: rgb(var(--v-theme-background));
  font-family: var(--paper-serif);
  font-weight: 450;
  letter-spacing: 0.02em;
  line-height: 1;
  user-select: none;
}
</style>
