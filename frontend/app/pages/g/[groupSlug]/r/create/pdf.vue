<template>
  <div>
    <v-form ref="domForm" @submit.prevent="startImport">
      <v-card-title class="headline">
        {{ $t('recipe.import-cookbook-pdf') }}
      </v-card-title>
      <v-card-text v-if="!aiEnabled">
        <v-alert type="info" variant="tonal">
          {{ $t('recipe.import-with-ai-provider-required') }}
        </v-alert>
      </v-card-text>
      <template v-else>
        <v-card-text>
          <p>{{ $t('recipe.import-cookbook-pdf-description') }}</p>
          <p class="mt-2">
            {{ $t('recipe.import-cookbook-pdf-resume-description') }}
          </p>

          <v-file-input
            v-model="pdfFile"
            :label="$t('recipe.import-cookbook-pdf-file')"
            accept="application/pdf,.pdf,application/epub+zip,.epub"
            prepend-icon=""
            :prepend-inner-icon="$globals.icons.filePDF"
            variant="solo-filled"
            rounded
            show-size
            class="mt-8 mb-2"
            :disabled="state.loading"
            @update:model-value="nameFromFile"
          />
          <v-text-field
            v-model="cookbookName"
            :label="$t('recipe.import-cookbook-pdf-name')"
            :hint="$t('recipe.import-cookbook-pdf-name-hint')"
            persistent-hint
            :prepend-inner-icon="$globals.icons.tags"
            variant="solo-filled"
            rounded
            :rules="[validators.required]"
            :disabled="state.loading"
          />

          <v-alert
            v-if="!imagesEnabled"
            type="info"
            variant="tonal"
            class="mt-6"
          >
            {{ $t('recipe.import-cookbook-pdf-text-only') }}
          </v-alert>

          <v-checkbox
            v-model="addCookbook"
            color="primary"
            hide-details
            class="mt-4"
            :label="$t('recipe.import-cookbook-pdf-add-cookbook')"
            :disabled="state.loading"
          />
          <div class="d-flex align-center">
            <v-checkbox
              v-model="addOrganizers"
              color="primary"
              hide-details
              :label="$t('recipe.import-cookbook-pdf-add-organizers')"
              :disabled="state.loading"
            />
            <v-tooltip location="bottom" max-width="300">
              <template #activator="{ props: tooltipProps }">
                <v-icon v-bind="tooltipProps" size="small" class="ms-2">
                  {{ $globals.icons.help }}
                </v-icon>
              </template>
              <span>{{ $t('recipe.import-cookbook-pdf-add-organizers-hint') }}</span>
            </v-tooltip>
          </div>
        </v-card-text>
        <v-card-actions class="justify-center">
          <div style="width: 250px">
            <BaseButton
              :disabled="!pdfFile || !cookbookName.trim() || importing"
              :text="$t('general.import')"
              :icon="$globals.icons.filePDF"
              rounded
              block
              type="submit"
              :loading="state.loading"
            />
          </div>
        </v-card-actions>
      </template>
    </v-form>

    <v-expand-transition>
      <section v-if="activeReport" class="mt-8">
        <v-alert :type="statusType" variant="tonal">
          {{ statusMessage }}
        </v-alert>
        <v-progress-linear
          v-if="importing"
          indeterminate
          color="primary"
          class="mt-2"
        />
        <v-list density="compact" class="mt-2">
          <v-list-item
            v-for="entry in activeEntries"
            :key="entry.id"
            :title="entry.message"
            :subtitle="entry.exception || undefined"
          >
            <template #prepend>
              <v-icon :color="entry.success ? 'success' : 'error'">
                {{ entry.success ? $globals.icons.checkboxMarkedCircle : $globals.icons.alertCircle }}
              </v-icon>
            </template>
          </v-list-item>
        </v-list>
      </section>
    </v-expand-transition>

    <section class="mt-12">
      <BaseCardSectionTitle :title="$t('recipe.pdf-imports')" />
      <ReportTable
        :items="reports"
        @delete="deleteReport"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { useIntervalFn } from "@vueuse/core";
import { useUserApi } from "~/composables/api";
import { useCookbookStore } from "~/composables/store/use-cookbook-store";
import { useTagStore } from "~/composables/store/use-tag-store";
import { useGroupSelf } from "~/composables/use-groups";
import { alert } from "~/composables/use-toast";
import { validators } from "~/composables/use-validators";
import type { ReportOut, ReportSummary } from "~/lib/api/types/reports";
import type { VForm } from "~/types/auto-forms";

definePageMeta({
  key: route => route.path,
});

const POLL_INTERVAL_MS = 3000;

const i18n = useI18n();
const api = useUserApi();
const { group } = useGroupSelf();
const cookbooks = useCookbookStore();
const tags = useTagStore();

const aiEnabled = computed(() => !!group.value?.aiProviderSettings?.aiEnabled);
// Image-only pages need both finding and reading recipes to have a provider that reads images
const imagesEnabled = computed(() => {
  const tasks = group.value?.aiProviderSettings?.imageReadingTasks ?? [];
  return tasks.includes("cookbook_discovery") && tasks.includes("cookbook_extraction");
});

const state = reactive({ loading: false });
const domForm = ref<VForm | null>(null);
const pdfFile = ref<File | null>(null);
const cookbookName = ref("");
const addCookbook = ref(true);
const addOrganizers = ref(false);

// the name suggested from the last file picked, so picking another replaces it but not a name the user typed
let suggestedName = "";

function nameFromFile(value: File | File[] | null) {
  const file = Array.isArray(value) ? value[0] : value;
  if (!file || (cookbookName.value && cookbookName.value !== suggestedName)) {
    return;
  }

  suggestedName = file.name.replace(/\.(pdf|epub)$/i, "").trim();
  cookbookName.value = suggestedName;
}

// =========================================================
// The import being followed

const activeReport = ref<ReportOut | null>(null);
const importing = computed(() => activeReport.value?.status === "in-progress");

const activeEntries = computed(() =>
  [...(activeReport.value?.entries ?? [])].sort((a, b) => Date.parse(b.timestamp!) - Date.parse(a.timestamp!)),
);

const statusMessage = computed(() => {
  const report = activeReport.value;
  if (!report) {
    return "";
  }

  const name = report.name;
  switch (report.status) {
    case "in-progress":
      return i18n.t("recipe.import-cookbook-pdf-in-progress", { name });
    case "success":
      return i18n.t("recipe.import-cookbook-pdf-success", { name });
    case "partial":
      return i18n.t("recipe.import-cookbook-pdf-partial", { name });
    default:
      return i18n.t("recipe.import-cookbook-pdf-failure", { name });
  }
});

const statusType = computed(() => {
  switch (activeReport.value?.status) {
    case "in-progress":
      return "info";
    case "success":
      return "success";
    case "partial":
      return "warning";
    default:
      return "error";
  }
});

async function refreshActiveReport() {
  if (!activeReport.value) {
    pause();
    return;
  }

  const { data } = await api.groupReports.getOne(activeReport.value.id);
  if (data) {
    activeReport.value = data;
  }

  if (!importing.value) {
    pause();
    fetchReports();
    // the import may have added a cookbook to the navigation, and tags
    cookbooks.actions.refresh();
    tags.actions.refresh();
  }
}

const { pause, resume } = useIntervalFn(refreshActiveReport, POLL_INTERVAL_MS, { immediate: false });

async function followReport(id: string) {
  const { data } = await api.groupReports.getOne(id);
  activeReport.value = data ?? null;
  if (importing.value) {
    resume();
  }
}

async function startImport() {
  if (!pdfFile.value) {
    return;
  }

  const isValid = await domForm.value?.validate();
  if (!isValid?.valid) {
    return;
  }

  state.loading = true;
  const { data } = await api.recipes.createManyFromPdf({
    file: pdfFile.value,
    name: cookbookName.value.trim(),
    addCookbook: addCookbook.value,
    addOrganizers: addOrganizers.value,
  });
  state.loading = false;

  // the server's reason for refusing it has already been shown
  if (!data) {
    return;
  }

  pdfFile.value = null;
  cookbookName.value = "";
  suggestedName = "";
  // after the cleared fields have re-validated, or they'd show as missing
  await nextTick();
  domForm.value?.resetValidation();

  await followReport(data.reportId);
  fetchReports();
}

// =========================================================
// Past imports

const reports = ref<ReportSummary[]>([]);

async function fetchReports() {
  const { data } = await api.groupReports.getAll("pdf_import");
  reports.value = data ?? [];
}

async function deleteReport(id: string) {
  const { response } = await api.groupReports.deleteOne(id);
  if (response?.status !== 200) {
    alert.error(i18n.t("recipe.report-deletion-failed"));
    return;
  }

  if (activeReport.value?.id === id) {
    activeReport.value = null;
  }
  fetchReports();
}

onMounted(async () => {
  await fetchReports();

  // pick back up on an import that's still running, e.g. after leaving the page and coming back
  const running = reports.value.find(report => report.status === "in-progress");
  if (running) {
    await followReport(running.id);
  }
});

onBeforeUnmount(() => pause());
</script>
