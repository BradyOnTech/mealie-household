<template>
  <section class="message-notifications paper-box" :aria-label="$t('messages.notifications')">
    <h2 class="message-notifications__title">
      <v-icon size="18" :icon="state === 'on' ? $globals.icons.bellOutline : $globals.icons.bellOffOutline" />
      {{ $t("messages.notifications") }}
    </h2>
    <p class="message-notifications__text">
      {{ description }}
    </p>
    <p v-if="error" class="message-notifications__error" role="alert">
      {{ error }}
    </p>
    <div v-if="state === 'off' || state === 'on'" class="message-notifications__actions">
      <v-btn
        v-if="state === 'off'"
        color="primary"
        variant="flat"
        :loading="busy"
        :prepend-icon="$globals.icons.bellOutline"
        @click="enable"
      >
        {{ $t("messages.turn-on") }}
      </v-btn>
      <template v-else>
        <v-btn variant="outlined" :disabled="busy || testing" :loading="testing" @click="sendTest">
          {{ $t("messages.send-test") }}
        </v-btn>
        <v-btn variant="text" :disabled="busy" @click="disable">
          {{ $t("messages.turn-off") }}
        </v-btn>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { alert } from "~/composables/use-toast";
import { useWebPush } from "~/composables/use-web-push";

const i18n = useI18n();
const { state, busy, error, enable, disable, test } = useWebPush();

const description = computed(() => {
  switch (state.value) {
    case "on": return i18n.t("messages.notifications-on");
    case "needs-install": return i18n.t("messages.notifications-needs-install");
    case "denied": return i18n.t("messages.notifications-denied");
    case "unsupported": return i18n.t("messages.notifications-unsupported");
    default: return i18n.t("messages.notifications-off");
  }
});

const testing = ref(false);
async function sendTest() {
  testing.value = true;
  try {
    const sent = await test();
    if (!error.value) alert.success(i18n.t(sent ? "messages.test-sent" : "messages.test-none"));
  }
  finally {
    testing.value = false;
  }
}
</script>

<style scoped>
.message-notifications {
  padding: 18px 20px;
}

.message-notifications__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-family: var(--paper-serif);
  font-size: 1.25rem;
  font-weight: 420;
}

.message-notifications__text {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

.message-notifications__error {
  margin: 8px 0 0;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-error));
}

.message-notifications__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
</style>
