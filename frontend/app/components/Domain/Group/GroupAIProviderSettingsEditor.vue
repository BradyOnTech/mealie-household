<template>
  <div v-if="providerSettings" class="ai-settings">
    <template v-if="!hideHeader">
      <BaseCardSectionTitle :title="$t('group.ai-provider-settings.ai-provider-settings')" />
      <p class="ai-settings__intro">
        {{ $t("group.ai-provider-settings.ai-provider-settings-description") }}
      </p>
    </template>

    <GroupAIProviderDialog
      v-model="dialogOpen"
      :provider-id="editingProviderId ?? undefined"
      :initial-type="newProviderType"
      @create="(data) => $emit('create', data)"
      @update="(id, data) => $emit('update', id, data)"
    />

    <!-- Nothing connected yet: the two ways to start -->
    <div v-if="!local.providers.length" class="ai-settings__empty">
      <h3 class="ai-settings__empty-title">
        {{ $t('group.ai-provider-settings.empty-title') }}
      </h3>
      <p class="ai-settings__empty-text">
        {{ $t('group.ai-provider-settings.empty-detail') }}
      </p>
      <div class="ai-settings__choices">
        <button type="button" class="ai-settings__choice ai-settings__choice--primary" @click="openCreate('chatgpt')">
          <span class="ai-settings__choice-title">
            {{ $t('group.ai-provider-settings.connect-chatgpt') }}
            <span class="ai-settings__badge">{{ $t('group.ai-provider-settings.recommended') }}</span>
          </span>
          <span class="ai-settings__choice-text">{{ $t('group.ai-provider-settings.provider-type-chatgpt-description') }}</span>
        </button>
        <button type="button" class="ai-settings__choice" @click="openCreate('openai')">
          <span class="ai-settings__choice-title">{{ $t('group.ai-provider-settings.use-api-key') }}</span>
          <span class="ai-settings__choice-text">{{ $t('group.ai-provider-settings.provider-type-api-key-description') }}</span>
        </button>
      </div>
    </div>

    <template v-else>
      <div class="ai-settings__head">
        <h3 class="ai-settings__heading">
          {{ $t('group.ai-provider-settings.providers') }}
        </h3>
        <BaseButton
          :text="$t('group.ai-provider-settings.add-provider')"
          create
          small
          @click="openCreate()"
        />
      </div>

      <ul class="ai-settings__providers">
        <li v-for="provider in local.providers" :key="provider.id" class="ai-settings__provider">
          <div class="ai-settings__provider-main">
            <span class="ai-settings__provider-name">{{ provider.name }}</span>
            <span class="ai-settings__provider-type">
              {{ provider.providerType === 'chatgpt'
                ? $t('group.ai-provider-settings.provider-type-chatgpt')
                : $t('group.ai-provider-settings.provider-type-api-key') }}
            </span>
            <span v-if="rolesOf(provider.id).length" class="ai-settings__roles">
              <span v-for="role in rolesOf(provider.id)" :key="role" class="ai-settings__role">{{ role }}</span>
            </span>
          </div>
          <v-btn
            icon
            variant="text"
            size="small"
            :aria-label="$t('general.edit')"
            @click="openEdit(provider.id)"
          >
            <v-icon :icon="$globals.icons.edit" size="20" />
          </v-btn>
          <v-btn
            icon
            variant="text"
            size="small"
            :aria-label="$t('general.delete')"
            @click="$emit('delete', provider.id)"
          >
            <v-icon :icon="$globals.icons.delete" size="20" />
          </v-btn>
        </li>
      </ul>

      <v-alert
        v-if="noDefaultProviderWarning"
        type="warning"
        density="compact"
        variant="tonal"
        class="mb-4"
      >
        {{ $t('group.ai-provider-settings.no-default-provider-warning') }}
      </v-alert>

      <h3 class="ai-settings__heading mb-1">
        {{ $t('group.ai-provider-settings.roles-title') }}
      </h3>
      <p class="ai-settings__intro">
        {{ $t('group.ai-provider-settings.roles-detail') }}
      </p>

      <div class="ai-settings__role-fields">
        <div>
          <v-autocomplete
            v-model="local.defaultProviderId"
            :label="$t('group.ai-provider-settings.default-provider')"
            :items="local.providers"
            item-title="name"
            item-value="id"
            clearable
            hide-details
            density="compact"
            variant="outlined"
          />
          <p class="ai-settings__field-hint">
            {{ $t("group.ai-provider-settings.default-provider-description") }}
          </p>
        </div>
        <div>
          <v-autocomplete
            v-model="local.imageProviderId"
            :label="$t('group.ai-provider-settings.image-provider')"
            :items="local.providers"
            item-title="name"
            item-value="id"
            clearable
            hide-details
            density="compact"
            variant="outlined"
          />
          <p class="ai-settings__field-hint">
            {{ $t("group.ai-provider-settings.image-provider-description") }}
          </p>
        </div>
        <div>
          <v-autocomplete
            v-model="local.audioProviderId"
            :label="$t('group.ai-provider-settings.audio-provider')"
            :items="audioProviders"
            item-title="name"
            item-value="id"
            :no-data-text="$t('group.ai-provider-settings.no-audio-providers')"
            clearable
            hide-details
            density="compact"
            variant="outlined"
          />
          <p class="ai-settings__field-hint">
            {{ $t("group.ai-provider-settings.audio-provider-description") }}
          </p>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import GroupAIProviderDialog from "~/components/Domain/Group/GroupAIProviderDialog.vue";
import type { AIProviderCreate, AIProviderType, AIProviderUpdate } from "~/lib/api/types/group";
import type { AIProviderSettingsOut } from "~/lib/api/types/user";

const providerSettings = defineModel<AIProviderSettingsOut>({ required: true });

const props = withDefaults(defineProps<{
  hideHeader?: boolean;
}>(), {
  hideHeader: false,
});

const { hideHeader } = toRefs(props);
const i18n = useI18n();

const local = reactive({ ...providerSettings.value });
watch(local, (newVal) => { providerSettings.value = { ...newVal }; });
// Sync back when the parent refreshes after create/update/delete
watch(providerSettings, (newVal) => { if (newVal) Object.assign(local, newVal); });

// ChatGPT subscription providers can't transcribe audio
const audioProviders = computed(() => local.providers.filter(provider => provider.providerType !== "chatgpt"));

const noDefaultProviderWarning = computed(
  () => local.providers.length > 0 && !local.defaultProviderId,
);

/** The jobs a provider has, as labels for its card */
function rolesOf(id: string) {
  return [
    local.defaultProviderId === id ? i18n.t("group.ai-provider-settings.role-default") : null,
    local.imageProviderId === id ? i18n.t("group.ai-provider-settings.role-images") : null,
    local.audioProviderId === id ? i18n.t("group.ai-provider-settings.role-audio") : null,
  ].filter((role): role is string => !!role);
}

defineEmits<{
  (e: "create", data: AIProviderCreate): void;
  (e: "update", id: string, data: AIProviderUpdate): void;
  (e: "delete", id: string): void;
}>();

const dialogOpen = ref(false);
const editingProviderId = ref<string | null>(null);
const newProviderType = ref<AIProviderType>("chatgpt");

function openCreate(providerType: AIProviderType = "chatgpt") {
  editingProviderId.value = null;
  newProviderType.value = providerType;
  dialogOpen.value = true;
}

function openEdit(id: string) {
  editingProviderId.value = id;
  dialogOpen.value = true;
}
</script>

<style scoped>
.ai-settings__intro {
  margin: 0 0 16px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

.ai-settings__empty {
  padding: 20px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 14px;
  background: rgb(var(--v-theme-surface));
}

.ai-settings__empty-title {
  margin: 0 0 6px;
  font-family: var(--paper-serif);
  font-size: 1.375rem;
  font-weight: 420;
}

.ai-settings__empty-text {
  margin: 0 0 16px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-ink-muted));
}

.ai-settings__choices {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.ai-settings__choice {
  appearance: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  background: rgb(var(--v-theme-background));
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.ai-settings__choice--primary {
  border-color: rgb(var(--v-theme-on-background));
}

.ai-settings__choice:hover {
  border-color: rgb(var(--v-theme-on-background));
}

.ai-settings__choice:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.ai-settings__choice-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 0.9375rem;
  font-weight: 600;
}

.ai-settings__choice-text {
  font-size: 0.8125rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-ink-muted));
}

.ai-settings__badge,
.ai-settings__role {
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: 700;
}

.ai-settings__badge {
  background: rgba(var(--v-theme-sage), 0.15);
  color: rgb(var(--v-theme-sage));
}

.ai-settings__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.ai-settings__heading {
  margin: 0;
  font-family: var(--paper-serif);
  font-size: 1.25rem;
  font-weight: 420;
}

.ai-settings__providers {
  margin: 0 0 18px;
  padding: 0;
  list-style: none;
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.ai-settings__provider {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.ai-settings__provider-main {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 10px;
  min-width: 0;
}

.ai-settings__provider-name {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.ai-settings__provider-type {
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
}

.ai-settings__roles {
  display: flex;
  flex-basis: 100%;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.ai-settings__role {
  background: rgb(var(--v-theme-wash));
  color: rgb(var(--v-theme-on-background));
}

.ai-settings__role-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ai-settings__field-hint {
  margin: 6px 2px 0;
  font-size: 0.8125rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
}

@media (max-width: 599px) {
  .ai-settings__choices {
    grid-template-columns: 1fr;
  }
}
</style>
