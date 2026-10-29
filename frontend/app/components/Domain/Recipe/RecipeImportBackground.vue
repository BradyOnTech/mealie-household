<template>
  <section v-if="reports.length" class="import-jobs">
    <h2 class="paper-section-title import-jobs__title">
      {{ $t("recipe-import.recent-imports") }}
      <span class="paper-section-aside">{{ $t("recipe-import.recent-imports-aside") }}</span>
    </h2>
    <ul class="import-jobs__list">
      <li
        v-for="report in reports"
        :key="report.id"
        class="import-jobs__item"
        :class="{ 'import-jobs__item--active': isRunning(report) }"
      >
        <div class="import-jobs__row">
          <button
            type="button"
            class="import-jobs__summary"
            :aria-expanded="expanded.has(report.id)"
            @click="toggle(report)"
          >
            <v-icon
              size="20"
              class="import-jobs__kind"
              :icon="report.category === 'pdf_import' ? $globals.icons.bookOpen : $globals.icons.listLinks"
            />
            <span class="import-jobs__name">{{ report.name }}</span>
            <span class="import-jobs__status" :class="`import-jobs__status--${statusOf(report)}`">
              <v-progress-circular
                v-if="isRunning(report)"
                indeterminate
                size="12"
                width="2"
                class="mr-1"
              />
              {{ statusText(report) }}
            </span>
            <span class="import-jobs__date">{{ formatDate(report.timestamp) }}</span>
          </button>
          <v-btn
            v-if="!isRunning(report)"
            icon
            variant="text"
            size="small"
            class="import-jobs__remove"
            :aria-label="$t('recipe-import.remove-import', { name: report.name })"
            @click="remove(report)"
          >
            <v-icon size="18" :icon="$globals.icons.close" />
          </v-btn>
        </div>

        <v-expand-transition>
          <div v-if="expanded.has(report.id)" class="import-jobs__detail">
            <p v-if="progressText(report)" class="import-jobs__progress">
              {{ progressText(report) }}
            </p>
            <ol v-if="entriesOf(report).length" class="import-jobs__entries">
              <li
                v-for="entry in visibleEntries(report)"
                :key="entry.id"
                class="import-jobs__entry"
              >
                <v-icon
                  size="16"
                  class="import-jobs__entry-icon"
                  :class="entry.success ? 'import-jobs__entry-icon--ok' : 'import-jobs__entry-icon--failed'"
                  :icon="entry.success ? $globals.icons.check : $globals.icons.alertCircle"
                />
                <div class="import-jobs__entry-text">
                  <span>{{ entry.message }}</span>
                  <span v-if="!entry.success && entry.exception" class="import-jobs__entry-reason">
                    {{ entry.exception }}
                  </span>
                </div>
              </li>
            </ol>
            <p v-else-if="!details.has(report.id)" class="import-jobs__progress">
              {{ $t("general.loading") }}
            </p>
            <div class="import-jobs__links">
              <button
                v-if="entriesOf(report).length > ENTRY_LIMIT"
                type="button"
                class="import-jobs__more"
                @click="toggleAll(report.id)"
              >
                {{ showAll.has(report.id)
                  ? $t("recipe-import.show-fewer")
                  : $t("recipe-import.show-all", { count: entriesOf(report).length }) }}
              </button>
              <NuxtLink
                v-if="!isRunning(report) && hasImported(report)"
                :to="`/g/${groupSlug}`"
                class="paper-link"
              >
                {{ $t("recipe-import.see-recipes") }}
              </NuxtLink>
            </div>
          </div>
        </v-expand-transition>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { useIntervalFn } from "@vueuse/core";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { ReportEntryOut, ReportOut, ReportSummary } from "~/lib/api/types/reports";

defineProps<{ groupSlug: string }>();

const emit = defineEmits<{
  /** A background import finished, so the recipes, labels and cookbooks it added can be shown */
  (e: "finished", report: ReportOut): void;
}>();

const POLL_INTERVAL_MS = 3000;
const RECENT_LIMIT = 5;
const ENTRY_LIMIT = 6;
/**
 * Link imports that are still "in progress" after this long were cut short by a restart: unlike
 * cookbook imports, nothing marks them as stopped.
 */
const STALE_LINKS_AFTER_MS = 2 * 60 * 60 * 1000;

const i18n = useI18n();
const api = useUserApi();

const summaries = ref<ReportSummary[]>([]);
const details = reactive(new Map<string, ReportOut>());
const expanded = reactive(new Set<string>());
const showAll = reactive(new Set<string>());
/** How many links each import started here was given, to count down */
const totals = reactive<Record<string, number>>({});
/** Imports started on this page, which count as running until they're seen to finish */
const followed = new Set<string>();

const reports = computed(() => {
  const merged = summaries.value.map(summary => details.get(summary.id) ?? summary);
  const running = merged.filter(isRunning);
  const finished = merged.filter(report => !isRunning(report)).slice(0, RECENT_LIMIT);
  return [...running, ...finished];
});

/** The server's timestamps are UTC, though not always marked as such */
function parseTimestamp(value: string | undefined) {
  if (!value) {
    return 0;
  }
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

function timestampOf(report: ReportSummary) {
  return parseTimestamp(report.timestamp);
}

function isStale(report: ReportSummary) {
  return report.category === "bulk_import" && Date.now() - timestampOf(report) > STALE_LINKS_AFTER_MS;
}

function isRunning(report: ReportSummary) {
  return report.status === "in-progress" && !isStale(report);
}

function statusOf(report: ReportSummary) {
  if (isRunning(report)) {
    return "running";
  }
  if (report.status === "in-progress") {
    return "stopped";
  }
  return report.status ?? "failure";
}

function statusText(report: ReportSummary) {
  return i18n.t(`recipe-import.status.${statusOf(report)}`);
}

function entriesOf(report: ReportSummary): ReportEntryOut[] {
  const entries = details.get(report.id)?.entries ?? [];
  return [...entries].sort((a, b) => parseTimestamp(b.timestamp) - parseTimestamp(a.timestamp));
}

function visibleEntries(report: ReportSummary) {
  const entries = entriesOf(report);
  return showAll.has(report.id) ? entries : entries.slice(0, ENTRY_LIMIT);
}

function hasImported(report: ReportSummary) {
  return report.status === "success" || report.status === "partial";
}

function progressText(report: ReportSummary) {
  if (!isRunning(report)) {
    return "";
  }
  const total = totals[report.id];
  const done = entriesOf(report).length;
  if (report.category === "bulk_import" && total) {
    return i18n.t("recipe-import.links-progress", { done, total });
  }
  return report.category === "pdf_import"
    ? i18n.t("recipe-import.cookbook-progress")
    : i18n.t("recipe-import.links-progress-unknown");
}

function formatDate(timestamp: string | undefined) {
  if (!timestamp) {
    return "";
  }
  const date = new Date(parseTimestamp(timestamp));
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString(i18n.locale.value, { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString(i18n.locale.value, { month: "short", day: "numeric" });
}

// =========================================================
// Loading and following

async function loadSummaries() {
  const [links, cookbooks] = await Promise.all([
    api.groupReports.getAll("bulk_import"),
    api.groupReports.getAll("pdf_import"),
  ]);
  summaries.value = [...(links.data ?? []), ...(cookbooks.data ?? [])]
    .sort((a, b) => timestampOf(b) - timestampOf(a));
}

async function loadDetail(id: string) {
  const { data } = await api.groupReports.getOne(id);
  if (!data) {
    return null;
  }
  const before = details.get(id);
  const wasRunning = before ? isRunning(before) : followed.has(id) || isRunning(data);
  details.set(id, data);
  if (wasRunning && !isRunning(data)) {
    emit("finished", data);
  }
  return data;
}

async function refreshRunning() {
  const running = reports.value.filter(isRunning);
  if (!running.length) {
    pause();
    return;
  }
  await Promise.all(running.map(report => loadDetail(report.id)));
  if (!reports.value.some(isRunning)) {
    pause();
  }
}

const { pause, resume } = useIntervalFn(refreshRunning, POLL_INTERVAL_MS, { immediate: false });

/** Shows an import that was just started, and follows it until it's done */
async function follow(reportId: string, total?: number) {
  if (total) {
    totals[reportId] = total;
  }
  followed.add(reportId);
  await loadSummaries();
  expanded.add(reportId);
  await loadDetail(reportId);
  resume();
}

async function toggle(report: ReportSummary) {
  if (expanded.has(report.id)) {
    expanded.delete(report.id);
    return;
  }
  expanded.add(report.id);
  if (!details.has(report.id)) {
    await loadDetail(report.id);
  }
}

function toggleAll(id: string) {
  if (showAll.has(id)) {
    showAll.delete(id);
  }
  else {
    showAll.add(id);
  }
}

async function remove(report: ReportSummary) {
  const { response } = await api.groupReports.deleteOne(report.id);
  if (response?.status !== 200) {
    alert.error(i18n.t("recipe.report-deletion-failed"));
    return;
  }
  summaries.value = summaries.value.filter(summary => summary.id !== report.id);
  details.delete(report.id);
  expanded.delete(report.id);
}

onMounted(async () => {
  await loadSummaries();
  const running = reports.value.filter(isRunning);
  // imports still going when the page opens, e.g. after leaving and coming back, show their progress
  running.forEach(report => expanded.add(report.id));
  await Promise.all(running.map(report => loadDetail(report.id)));
  if (running.length) {
    resume();
  }
});

onBeforeUnmount(() => pause());

defineExpose({ follow });
</script>

<style scoped>
.import-jobs__title {
  margin-bottom: 4px;
}

.import-jobs__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.import-jobs__item {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.import-jobs__row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.import-jobs__summary {
  appearance: none;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  cursor: pointer;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  padding: 14px 2px;
  color: rgb(var(--v-theme-on-background));
  text-align: left;
}

.import-jobs__kind {
  color: rgb(var(--v-theme-ink-muted));
}

.import-jobs__name {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.import-jobs__status {
  display: inline-flex;
  align-items: center;
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
}

.import-jobs__status--running {
  color: rgb(var(--v-theme-tomato));
}

.import-jobs__status--success {
  color: rgb(var(--v-theme-sage));
}

.import-jobs__status--partial,
.import-jobs__status--stopped {
  color: rgb(var(--v-theme-warning));
}

.import-jobs__status--failure {
  color: rgb(var(--v-theme-error));
}

.import-jobs__date {
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
  white-space: nowrap;
}

.import-jobs__remove {
  color: rgb(var(--v-theme-ink-muted));
}

.import-jobs__detail {
  padding: 0 0 16px 34px;
}

.import-jobs__progress {
  margin: 0 0 8px;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-ink-muted));
}

.import-jobs__entries {
  margin: 0;
  padding: 0;
  list-style: none;
}

.import-jobs__entry {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 0.875rem;
}

.import-jobs__entry-icon {
  flex: none;
  margin-top: 2px;
}

.import-jobs__entry-icon--ok {
  color: rgb(var(--v-theme-sage));
}

.import-jobs__entry-icon--failed {
  color: rgb(var(--v-theme-error));
}

.import-jobs__entry-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-wrap: anywhere;
}

.import-jobs__entry-reason {
  color: rgb(var(--v-theme-ink-muted));
}

.import-jobs__more {
  appearance: none;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  cursor: pointer;
  color: rgb(var(--v-theme-tomato));
  font-weight: 600;
}

.import-jobs__links {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 8px;
  font-size: 0.875rem;
}

@media (max-width: 599px) {
  .import-jobs__summary {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .import-jobs__date {
    display: none;
  }

  .import-jobs__detail {
    padding-left: 0;
  }
}
</style>
