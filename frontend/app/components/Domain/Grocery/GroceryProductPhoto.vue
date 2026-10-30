<template>
  <button
    v-if="zoomable && shown"
    type="button"
    class="grocery-photo grocery-photo--zoomable"
    :style="frame"
    :aria-label="$t('grocery-photos.view', { name })"
    @click.stop="viewing = true"
  >
    <img :src="src!" alt="" loading="lazy" decoding="async" @error="failed = true">
    <v-dialog v-model="viewing" max-width="520">
      <v-card class="grocery-photo__viewer">
        <div class="grocery-photo__large">
          <img :src="large ?? src!" :alt="$t('grocery-photos.photo-of', { name })">
        </div>
        <div class="grocery-photo__caption">
          <span>{{ name }}</span>
          <v-btn variant="text" @click.stop="viewing = false">
            {{ $t('general.close') }}
          </v-btn>
        </div>
      </v-card>
    </v-dialog>
  </button>
  <div
    v-else-if="shown || placeholder"
    class="grocery-photo"
    :class="{ 'grocery-photo--empty': !shown }"
    :style="frame"
  >
    <img
      v-if="shown"
      :src="src!"
      :alt="$t('grocery-photos.photo-of', { name })"
      loading="lazy"
      decoding="async"
      @error="failed = true"
    >
    <v-icon v-else :icon="$globals.icons.camera" :size="Math.round(size * 0.34)" />
  </div>
</template>

<script setup lang="ts">
/** A grocery product's photo, in a frame that shows the whole package; tapping it can show it large */
const props = withDefaults(defineProps<{
  /** The photo at its small size. Without one nothing shows, unless `placeholder`. */
  src?: string | null;
  /** The photo at its large size, shown when it's tapped */
  large?: string | null;
  /** What the photo is of */
  name: string;
  /** The frame's width and height, in pixels */
  size?: number;
  /** Shows the photo large when it's tapped */
  zoomable?: boolean;
  /** Shows an empty frame when there's no photo */
  placeholder?: boolean;
}>(), { src: null, large: null, size: 56, zoomable: false, placeholder: false });

const failed = ref(false);
const viewing = ref(false);
// a photo that wouldn't load may be replaced by one that will
watch(() => props.src, () => (failed.value = false));
const shown = computed(() => !!props.src && !failed.value);
const frame = computed(() => ({ "--photo-size": `${props.size}px` }));
</script>

<style scoped>
.grocery-photo {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--photo-size);
  height: var(--photo-size);
  padding: 3px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  overflow: hidden;
  /* store photos are shot on white, so the frame is white too */
  background: #fff;
  color: rgb(var(--v-theme-ink-muted));
}

.grocery-photo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.grocery-photo--empty {
  border-style: dashed;
  background: rgb(var(--v-theme-surface-light));
}

.grocery-photo--zoomable {
  cursor: zoom-in;
  font: inherit;
}

.grocery-photo--zoomable:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.grocery-photo__large {
  display: flex;
  justify-content: center;
  padding: 20px;
  background: #fff;
}

.grocery-photo__large img {
  width: 100%;
  max-height: min(70vh, 640px);
  object-fit: contain;
}

.grocery-photo__caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px 10px 20px;
  border-top: 1px solid rgb(var(--v-theme-rule));
  font-weight: 600;
}
</style>
