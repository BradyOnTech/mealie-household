<template>
  <v-card height="100%" :loading="loading">
    <template #loader="{ isActive }">
      <v-progress-linear
        :active="isActive"
        indeterminate
      />
    </template>
    <div class="base-dialog__head">
      <span v-if="icon" class="base-dialog__icon" :class="`text-${accentColor}`">
        <v-icon size="20">
          {{ icon }}
        </v-icon>
      </span>
      <h2 class="base-dialog__title">
        {{ title }}
      </h2>
    </div>

    <div style="flex: 1 1 auto; min-height: 0; overflow: auto">
      <slot />
    </div>

    <v-spacer />
    <v-divider />
    <v-card-actions :class="$vuetify.display.xs ? 'pb-4 grid-small' : undefined">
      <slot name="card-actions">
        <v-btn
          variant="text"
          color="grey"
          @click="emit('cancel')"
        >
          {{ cancelLabel }}
        </v-btn>
        <v-spacer v-if="!$vuetify.display.xs" />
        <slot name="custom-card-action" />
        <BaseButton
          v-if="canDelete"
          delete
          @click="emit('delete')"
        />
        <BaseButton
          v-if="canConfirm"
          :color="color"
          type="submit"
          :disabled="submitDisabled"
          @click="emit('confirm')"
        >
          <template #icon>
            {{ $globals.icons.check }}
          </template>
          {{ $t("general.confirm") }}
        </BaseButton>
        <BaseButton
          v-if="canSubmit"
          type="submit"
          :disabled="submitDisabled || loading"
          @click="emit('submit')"
        >
          {{ submitLabel }}
          <template
            v-if="submitIcon"
            #icon
          >
            {{ submitIcon }}
          </template>
        </BaseButton>
      </slot>
    </v-card-actions>
  </v-card>
</template>

<script setup lang="ts">
import { useGlobalI18n } from "~/composables/use-global-i18n";

interface DialogProps {
  color?: string;
  title?: string;
  icon?: string | null;
  loading?: boolean;

  // submit
  submitIcon?: string | null;
  submitText?: string;
  submitDisabled?: boolean;

  // cancel
  cancelText?: string;

  // actions
  canDelete?: boolean;
  canConfirm?: boolean;
  canSubmit?: boolean;
}

interface DialogEmits {
  (e: "submit" | "cancel" | "confirm" | "delete"): void;
}

// Using TypeScript interface with withDefaults for props
const props = withDefaults(defineProps<DialogProps>(), {
  color: "primary",
  title: "Modal Title",
  icon: null,
  loading: false,

  // submit
  submitIcon: null,
  submitDisabled: false,

  // actions
  canDelete: false,
  canConfirm: false,
  canSubmit: false,
});
const emit = defineEmits<DialogEmits>();

const i18n = useGlobalI18n();

const submitLabel = computed(() => props.submitText ?? i18n.t("general.create"));
// The dialog's color tints its icon; the default reads as the editorial accent.
const accentColor = computed(() => (props.color === "primary" ? "tomato" : props.color));
const cancelLabel = computed(() => props.cancelText ?? i18n.t("general.cancel"));
</script>

<style scoped>
/* On extra-small displays the dialog is a bottom sheet or fullscreen, so the
   actions stretch evenly across the full width. Larger displays keep the
   default v-card-actions flex row, where the spacer pushes the actions right. */
.grid-small {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(min-content, 1fr);
}

.base-dialog__head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px 14px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.base-dialog__icon {
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: currentColor;
}

.base-dialog__icon .v-icon {
  color: rgb(var(--v-theme-surface));
}

.base-dialog__title {
  margin: 0;
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 450;
  line-height: 1.2;
  letter-spacing: -0.01em;
}
</style>
