<template>
  <div class="recipe-import">
    <header class="recipe-import__head">
      <span class="paper-kicker">{{ $t("recipe-import.kicker") }}</span>
      <h1 class="paper-headline recipe-import__title">
        {{ $t("recipe-import.title") }}
      </h1>
      <p class="paper-dek recipe-import__dek">
        {{ aiEnabled ? $t("recipe-import.dek") : $t("recipe-import.dek-without-ai") }}
      </p>
    </header>

    <RecipeImportBox
      ref="box"
      v-model:text="text"
      v-model:files="files"
      :label="$t('recipe-import.box-label')"
      :placeholder="placeholder"
      :submit-label="submitLabel"
      :submit-disabled="!canSubmit"
      :submit-on-enter="plan.kind === 'link'"
      :hide-text="plan.kind === 'cookbook' || plan.kind === 'archive'"
      :busy="running"
      :autofocus="!isPhone"
      @submit="start"
      @rejected="onRejected"
    >
      <template #details>
        <div v-if="sourceUrl && !running && plan.kind !== 'link'" class="recipe-import__source">
          <v-icon size="16" :icon="$globals.icons.link" />
          <span class="recipe-import__source-text">{{ $t("recipe-import.source-link", { site: sourceSite }) }}</span>
          <button
            type="button"
            class="recipe-import__source-remove"
            :aria-label="$t('recipe-import.remove-source-link')"
            @click="sourceUrl = null"
          >
            <v-icon size="14" :icon="$globals.icons.close" />
          </button>
        </div>
        <div v-if="plan.kind === 'cookbook'" class="recipe-import__cookbook">
          <v-text-field
            v-model="cookbookName"
            :label="$t('recipe.import-cookbook-pdf-name')"
            :hint="$t('recipe.import-cookbook-pdf-name-hint')"
            persistent-hint
            variant="outlined"
            density="comfortable"
            :disabled="running"
          />
          <v-checkbox
            v-model="addCookbook"
            :label="$t('recipe.import-cookbook-pdf-add-cookbook')"
            color="primary"
            density="compact"
            hide-details
            :disabled="running"
          />
        </div>
      </template>
      <template #busy>
        <RecipeImportProgress
          :title="progressTitle"
          :steps="steps"
          :started-at="startedAt"
          :note="progressNote"
        />
      </template>
    </RecipeImportBox>

    <div v-if="!running" class="recipe-import__status">
      <p v-if="hint" class="recipe-import__hint" :class="{ 'recipe-import__hint--warning': hint.warning }">
        <v-icon size="18" class="recipe-import__hint-icon" :icon="hint.icon" />
        <span>
          {{ hint.text }}
          <NuxtLink v-if="hint.link" :to="hint.link.to" class="paper-link">{{ hint.link.label }}</NuxtLink>
          <button v-if="hint.action" type="button" class="recipe-import__hint-action" @click="hint.action.run">{{ hint.action.label }}</button>
        </span>
      </p>
      <p v-if="duplicate" class="recipe-import__hint recipe-import__hint--duplicate">
        <v-icon size="18" class="recipe-import__hint-icon" :icon="$globals.icons.duplicate" />
        <span>
          {{ $t("recipe-import.already-saved") }}
          <NuxtLink :to="`/g/${groupSlug}/r/${duplicate.slug}`" class="paper-link">{{ duplicate.name }}</NuxtLink>
        </span>
      </p>
    </div>

    <section v-if="failure && !running" class="recipe-import__failure" role="alert">
      <h2 class="recipe-import__failure-title">
        {{ failure.title }}
      </h2>
      <p class="recipe-import__failure-text">
        {{ failure.message }}
      </p>
      <div v-if="failure.actions.length" class="recipe-import__failure-actions">
        <v-btn
          v-for="(action, index) in failure.actions"
          :key="action.label"
          :variant="index === 0 ? 'flat' : 'outlined'"
          :color="index === 0 ? 'primary' : undefined"
          :prepend-icon="action.icon"
          @click="action.run"
        >
          {{ action.label }}
        </v-btn>
      </div>
    </section>

    <section class="recipe-import__ways" :aria-label="$t('recipe-import.other-ways')">
      <h2 class="paper-kicker recipe-import__ways-title">
        {{ $t("recipe-import.other-ways") }}
      </h2>
      <div class="recipe-import__ways-grid">
        <button
          v-for="way in ways"
          :key="way.key"
          type="button"
          class="recipe-import__way"
          :disabled="running"
          @click="way.run"
        >
          <v-icon class="recipe-import__way-icon" size="22" :icon="way.icon" />
          <span class="recipe-import__way-title">{{ way.title }}</span>
          <span class="recipe-import__way-text">{{ way.text }}</span>
        </button>
      </div>
    </section>

    <RecipeImportSettings class="recipe-import__settings" :ai-enabled="aiEnabled" />

    <RecipeImportBackground
      ref="background"
      class="recipe-import__jobs"
      :group-slug="groupSlug"
      @finished="onBackgroundFinished"
    />

    <footer class="recipe-import__footer">
      <NuxtLink v-if="canMigrate" to="/group/migrations" class="paper-link">
        {{ $t("recipe-import.from-another-app") }}
      </NuxtLink>
      <NuxtLink :to="`/g/${groupSlug}/r/create/debug`" class="paper-link">
        {{ $t("recipe-import.check-a-link") }}
      </NuxtLink>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { useDebounceFn } from "@vueuse/core";
import { useDisplay } from "vuetify";
import RecipeImportBackground from "~/components/Domain/Recipe/RecipeImportBackground.vue";
import RecipeImportBox from "~/components/Domain/Recipe/RecipeImportBox.vue";
import RecipeImportProgress from "~/components/Domain/Recipe/RecipeImportProgress.vue";
import RecipeImportSettings from "~/components/Domain/Recipe/RecipeImportSettings.vue";
import { useUserApi } from "~/composables/api";
import { useCategoryStore, useTagStore, useToolStore } from "~/composables/store";
import { useCookbookStore } from "~/composables/store/use-cookbook-store";
import { useGroupSelf } from "~/composables/use-groups";
import { useNewRecipeOptions } from "~/composables/use-new-recipe-options";
import {
  IMPORT_FILE_TYPES,
  linkKey,
  linkSearchTerm,
  linkSource,
  planImport,
  progressStep,
  scraperError,
  type ImportPlan,
} from "~/composables/use-recipe-import";
import { alert } from "~/composables/use-toast";
import type { ReportOut } from "~/lib/api/types/reports";

definePageMeta({
  key: route => route.path,
});

const i18n = useI18n();
const api = useUserApi();
const auth = useMealieAuth();
const route = useRoute();
const router = useRouter();
const { $globals } = useNuxtApp();
const { xs: isPhone } = useDisplay();
const { group } = useGroupSelf();
const tags = useTagStore();
const categories = useCategoryStore();
const tools = useToolStore();
const cookbooks = useCookbookStore();
const {
  organize,
  createNewOrganizers,
  keepSourceLabels,
  translateRecipe,
  stayInEditMode,
  navigateToRecipe,
} = useNewRecipeOptions();

useSeoMeta({ title: i18n.t("recipe-import.title") });

const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");
const createPath = computed(() => `/g/${groupSlug.value}/r/create/url`);
const aiEnabled = computed(() => !!group.value?.aiProviderSettings?.aiEnabled);
const photosEnabled = computed(
  () => !!group.value?.aiProviderSettings?.imageReadingTasks?.includes("recipe_source_reading"),
);
const cookbookImagesEnabled = computed(() => {
  const tasks = group.value?.aiProviderSettings?.imageReadingTasks ?? [];
  return tasks.includes("cookbook_discovery") && tasks.includes("cookbook_extraction");
});
const canManageGroup = computed(() => !!auth.user.value?.canManage);
// moving recipes over from another app is an advanced feature
const canMigrate = computed(() => !!auth.user.value?.advanced);

const box = ref<InstanceType<typeof RecipeImportBox> | null>(null);
const background = ref<InstanceType<typeof RecipeImportBackground> | null>(null);

// =========================================================
// What's in the box

const text = ref("");
const files = ref<File[]>([]);
/** A link that couldn't be read, kept as the source of the text or photos imported in its place */
const sourceUrl = ref<string | null>(null);
/** What someone said they'd add, by picking "Several links" or arriving to import a cookbook, until they do */
const expecting = ref<"links" | "cookbook" | null>(null);

const plan = computed(() => planImport(text.value, files.value, { ai: aiEnabled.value, photos: photosEnabled.value }));
const sourceSite = computed(() => (sourceUrl.value && linkSource(sourceUrl.value)?.site) || "");

const cookbookName = ref("");
const addCookbook = ref(true);
// the name suggested for the last cookbook picked, so picking another replaces it, but not a name someone typed
let suggestedName = "";

watch(() => plan.value.file, (file) => {
  if (plan.value.kind !== "cookbook" || !file) {
    return;
  }
  if (!cookbookName.value || cookbookName.value === suggestedName) {
    suggestedName = file.name.replace(/\.(pdf|epub)$/i, "").replace(/[_-]+/g, " ").trim();
    cookbookName.value = suggestedName;
  }
});

watch([text, files], () => {
  if (text.value || files.value.length) {
    expecting.value = null;
  }
  // what failed was a different import
  failure.value = null;
});

// a link kept as the source of pasted text or photos doesn't belong with anything else
watch(() => plan.value.kind, (kind) => {
  if (["link", "links", "cookbook", "archive"].includes(kind)) {
    sourceUrl.value = null;
  }
});

const placeholder = computed(() => {
  if (sourceUrl.value && plan.value.kind !== "photos") {
    return i18n.t("recipe-import.placeholder-paste-text");
  }
  if (plan.value.kind === "photos") {
    return i18n.t("recipe-import.placeholder-photo-notes");
  }
  if (expecting.value === "links") {
    return i18n.t("recipe-import.placeholder-links");
  }
  return aiEnabled.value ? i18n.t("recipe-import.placeholder") : i18n.t("recipe-import.placeholder-without-ai");
});

const submitLabel = computed(() => {
  switch (plan.value.kind) {
    case "links":
      return i18n.t("recipe-import.import-count", { count: plan.value.urls.length });
    case "cookbook":
      return i18n.t("recipe-import.import-cookbook");
    default:
      return duplicate.value ? i18n.t("recipe-import.import-again") : i18n.t("recipe-import.import");
  }
});

const canSubmit = computed(() => {
  const current = plan.value;
  if (current.kind === "empty" || current.blocker || running.value) {
    return false;
  }
  return current.kind !== "cookbook" || !!cookbookName.value.trim();
});

interface Hint {
  icon: string;
  text: string;
  warning?: boolean;
  link?: { to: string; label: string };
  action?: { label: string; run: () => void };
}

const aiSettingsLink = computed(() =>
  canManageGroup.value ? { to: "/group", label: i18n.t("recipe-import.set-up-ai") } : undefined,
);

/** What will happen to what's in the box, or why it can't be imported */
const hint = computed<Hint | null>(() => {
  const current = plan.value;
  const icons = $globals.icons;

  switch (current.blocker) {
    case "needs-ai":
      return {
        icon: icons.alertCircle,
        warning: true,
        text: i18n.t(`recipe-import.needs-ai.${current.kind}`, { site: current.url ? linkSource(current.url)?.site : "" }),
        link: aiSettingsLink.value,
      };
    case "needs-image-ai":
      return { icon: icons.alertCircle, warning: true, text: i18n.t("recipe-import.needs-image-ai"), link: aiSettingsLink.value };
    case "one-file":
      return { icon: icons.alertCircle, warning: true, text: i18n.t("recipe-import.one-file") };
    case "unsupported-file":
      return { icon: icons.alertCircle, warning: true, text: i18n.t("recipe-import.unsupported-file") };
  }

  switch (current.kind) {
    case "link": {
      const source = linkSource(current.url!);
      return source?.video
        ? { icon: icons.link, text: i18n.t("recipe-import.hint.video", { site: source.site }) }
        : { icon: icons.link, text: i18n.t(aiEnabled.value ? "recipe-import.hint.page" : "recipe-import.hint.page-without-ai", { site: source?.site ?? "" }) };
    }
    case "links":
      return { icon: icons.listLinks, text: i18n.t("recipe-import.hint.links", { count: current.urls.length }) };
    case "markup":
      return { icon: icons.codeTags, text: i18n.t("recipe-import.hint.markup") };
    case "text":
      return { icon: icons.textBox, text: i18n.t("recipe-import.hint.text") };
    case "photos":
      return {
        icon: icons.photos,
        text: current.url
          ? i18n.t("recipe-import.hint.photos-with-link", { count: current.photos.length, site: linkSource(current.url)?.site ?? "" }, current.photos.length)
          : i18n.t("recipe-import.hint.photos", current.photos.length),
      };
    case "cookbook":
      return {
        icon: icons.bookOpen,
        text: cookbookImagesEnabled.value ? i18n.t("recipe-import.hint.cookbook") : i18n.t("recipe-import.hint.cookbook-text-only"),
      };
    case "archive":
      return { icon: icons.zip, text: i18n.t("recipe-import.hint.archive") };
  }

  if (expecting.value === "cookbook" && aiEnabled.value) {
    return {
      icon: icons.bookOpen,
      text: i18n.t("recipe-import.hint.choose-cookbook"),
      action: { label: i18n.t("recipe-import.choose-file"), run: () => box.value?.pickFiles(IMPORT_FILE_TYPES.cookbook) },
    };
  }
  return null;
});

function onRejected(rejected: File[]) {
  alert.error(i18n.t("recipe-import.files-not-imported", { names: rejected.map(file => file.name).join(", ") }));
}

// =========================================================
// A link that's been imported before

interface SavedRecipe {
  name: string;
  slug: string;
}

const duplicate = ref<SavedRecipe | null>(null);

const findDuplicate = useDebounceFn(async (url: string) => {
  const term = linkSearchTerm(url);
  const key = linkKey(url);
  if (!term || !key) {
    return;
  }

  const { data } = await api.recipes.getAll(1, 10, { queryFilter: `orgURL LIKE "%${term}%"` });
  // the box may have moved on while this was looking
  if (plan.value.url !== url) {
    return;
  }
  const match = data?.items.find(recipe => recipe.orgURL && linkKey(recipe.orgURL) === key);
  duplicate.value = match?.slug ? { name: match.name || match.slug, slug: match.slug } : null;
}, 350);

watch(() => (plan.value.kind === "link" ? plan.value.url : null), (url) => {
  duplicate.value = null;
  if (url) {
    findDuplicate(url);
  }
});

// =========================================================
// Other ways in

const ways = computed(() => {
  const icons = $globals.icons;
  const all = [
    {
      key: "photos",
      icon: icons.photos,
      title: i18n.t("recipe-import.way.photos"),
      text: i18n.t("recipe-import.way.photos-text"),
      needsAI: true,
      run: () => box.value?.pickFiles(IMPORT_FILE_TYPES.photo),
    },
    {
      key: "cookbook",
      icon: icons.bookOpen,
      title: i18n.t("recipe-import.way.cookbook"),
      text: i18n.t("recipe-import.way.cookbook-text"),
      needsAI: true,
      run: () => box.value?.pickFiles(IMPORT_FILE_TYPES.cookbook),
    },
    {
      key: "links",
      icon: icons.listLinks,
      title: i18n.t("recipe-import.way.links"),
      text: i18n.t("recipe-import.way.links-text"),
      run: () => {
        expecting.value = "links";
        box.value?.focus();
      },
    },
    {
      key: "write",
      icon: icons.pencil,
      title: i18n.t("recipe-import.way.write"),
      text: i18n.t("recipe-import.way.write-text"),
      run: () => router.push(`/g/${groupSlug.value}/r/create/new`),
    },
  ];
  return all.filter(way => aiEnabled.value || !way.needsAI);
});

// =========================================================
// Importing

const running = ref(false);
const steps = ref<string[]>([]);
const startedAt = ref(0);
/** What the running import is reading, for its progress */
const runningPlan = ref<ImportPlan | null>(null);

const progressTitle = computed(() => {
  const current = runningPlan.value;
  if (!current) {
    return "";
  }
  if (current.kind === "link") {
    return i18n.t("recipe-import.progress.link", { site: linkSource(current.url!)?.site ?? "" });
  }
  return i18n.t(`recipe-import.progress.${current.kind}`);
});

const progressNote = computed(() => {
  const current = runningPlan.value;
  if (current?.kind === "link" && linkSource(current.url!)?.video) {
    return i18n.t("recipe-import.progress.video-note");
  }
  if (current?.kind === "text" || current?.kind === "photos") {
    return i18n.t("recipe-import.progress.ai-note");
  }
  return "";
});

function onProgress(message: string) {
  const step = progressStep(message);
  if (step && steps.value[steps.value.length - 1] !== step) {
    steps.value.push(step);
  }
}

interface FailureAction {
  label: string;
  icon: string;
  run: () => void;
}

interface Failure {
  title: string;
  message: string;
  actions: FailureAction[];
}

const failure = ref<Failure | null>(null);

function failureMessage(current: ImportPlan, message: string | null | undefined) {
  switch (scraperError(message)) {
    case "no-recipe":
      return i18n.t(current.kind === "markup" ? "recipe-import.error.no-recipe-in-markup" : "recipe-import.error.no-recipe-on-page");
    case "unreachable":
      return i18n.t("recipe-import.error.unreachable");
  }
  return message || i18n.t("recipe-import.error.unknown");
}

/** Ways forward after an import fails: other ways to give Mealie the same recipe, or another go */
function failureActions(current: ImportPlan): FailureAction[] {
  const icons = $globals.icons;
  const retry = { label: i18n.t("recipe-import.try-again"), icon: icons.refresh, run: () => runSingle(current) };
  const actions: FailureAction[] = [];

  if (current.kind === "link" && aiEnabled.value) {
    actions.push({ label: i18n.t("recipe-import.paste-text-instead"), icon: icons.textBox, run: () => importInstead(current.url!, false) });
    if (photosEnabled.value) {
      actions.push({ label: i18n.t("recipe-import.add-screenshots-instead"), icon: icons.photos, run: () => importInstead(current.url!, true) });
    }
  }
  if (current.kind === "markup" && aiEnabled.value) {
    actions.push({ label: i18n.t("recipe-import.read-with-ai"), icon: icons.autoFix, run: () => runSingle({ ...current, kind: "text" }) });
  }
  actions.push(retry);
  return actions;
}

/** Swaps a link that couldn't be read for the recipe's text or screenshots, keeping the link as its source */
function importInstead(url: string, screenshots: boolean) {
  sourceUrl.value = url;
  text.value = "";
  failure.value = null;
  nextTick(() => {
    if (screenshots) {
      box.value?.pickFiles(IMPORT_FILE_TYPES.photo);
    }
    else {
      box.value?.focus();
    }
  });
}

async function refreshLabels() {
  await Promise.all([tags.actions.refresh(), categories.actions.refresh(), tools.actions.refresh()]);
}

async function start() {
  const current = plan.value;
  if (current.kind === "empty" || current.blocker || running.value) {
    return;
  }
  failure.value = null;

  if (current.kind === "links") {
    await startLinks(current.urls);
  }
  else if (current.kind === "cookbook") {
    await startCookbook(current.file!);
  }
  else {
    await runSingle(current);
  }
}

/** Imports one recipe, following its progress, then opens it */
async function runSingle(current: ImportPlan) {
  failure.value = null;
  running.value = true;
  runningPlan.value = current;
  startedAt.value = Date.now();
  steps.value = [i18n.t(`recipe-import.first-step.${current.kind}`)];

  const options = {
    organize: organize.value,
    createNewOrganizers: createNewOrganizers.value,
    includeTags: keepSourceLabels.value,
    includeCategories: keepSourceLabels.value,
  };

  let slug: string | null = null;
  let message: string | null | undefined;

  if (current.kind === "link") {
    const { data, error } = await api.recipes.createOneByUrl(current.url!, options, onProgress);
    slug = data;
    message = error?.message;
  }
  else if (current.kind === "markup") {
    const { data, error } = await api.recipes.createOneByHtmlOrJson(current.content!, sourceUrl.value, options, onProgress);
    slug = data;
    message = error?.message;
  }
  else if (current.kind === "text" || current.kind === "photos") {
    const { data, error } = await api.recipes.createOneWithAI(
      {
        content: current.content,
        url: current.url ?? sourceUrl.value,
        images: current.photos,
        translateLanguage: translateRecipe.value ? i18n.locale.value : null,
        createNewOrganizers: createNewOrganizers.value,
        organize: organize.value,
      },
      onProgress,
    );
    slug = data;
    message = error?.message;
  }
  else if (current.kind === "archive") {
    const { data } = await api.recipes.createOneFromZip(current.file!);
    slug = data;
    message = data ? null : i18n.t("recipe-import.error.archive");
  }

  running.value = !!slug;
  if (!onPage) {
    // the import carried on after its page was left, so say how it went rather than going anywhere
    if (slug) {
      alert.success(i18n.t("recipe-import.imported-while-away"));
    }
    else {
      alert.error(failureMessage(current, message));
    }
    return;
  }

  if (!slug) {
    failure.value = {
      title: i18n.t("recipe-import.error.title"),
      message: failureMessage(current, message),
      actions: failureActions(current),
    };
    return;
  }

  steps.value.push(i18n.t("recipe-import.done"));
  await refreshLabels();
  navigateToRecipe(slug, groupSlug.value, createPath.value);
}

// An import keeps going on the server when its page is left, and this page hears how it went
let onPage = true;
onBeforeUnmount(() => {
  onPage = false;
});

/** Starts importing several links in the background, and shows how they're going */
async function startLinks(urls: string[]) {
  running.value = true;
  const { data } = await api.recipes.createManyByUrl({
    imports: urls.map(url => ({ url })),
    organize: organize.value,
    createNewOrganizers: createNewOrganizers.value,
  });
  running.value = false;

  if (!data?.reportId) {
    alert.error(i18n.t("recipe.bulk-import-process-has-failed"));
    return;
  }

  text.value = "";
  alert.success(i18n.t("recipe-import.links-started", { count: urls.length }));
  await background.value?.follow(data.reportId, urls.length);
}

/** Starts importing a cookbook in the background, and shows how it's going */
async function startCookbook(file: File) {
  running.value = true;
  const { data } = await api.recipes.createManyFromPdf({
    file,
    name: cookbookName.value.trim(),
    addCookbook: addCookbook.value,
    addOrganizers: organize.value,
  });
  running.value = false;

  // the server's reason for refusing it has already been shown
  if (!data) {
    return;
  }

  files.value = [];
  cookbookName.value = "";
  suggestedName = "";
  alert.success(i18n.t("recipe-import.cookbook-started"));
  await background.value?.follow(data.reportId);
}

async function onBackgroundFinished(report: ReportOut) {
  await refreshLabels();
  if (report.category === "pdf_import") {
    // the import may have added a cookbook to the navigation
    cookbooks.actions.refresh();
  }
}

// =========================================================
// Links shared to Mealie, and older bookmarklets

onMounted(() => {
  const sharedUrl = route.query.recipe_import_url as string | undefined;
  const sharedText = route.query.recipe_import_text as string | undefined;
  // apps that share links as text often wrap them in a line about the link, which the box sorts out
  const shared = sharedUrl || sharedText;
  if (shared) {
    text.value = shared.trim();
  }

  // Older automations, such as the Bookmarklet, still pass these
  if (route.query.use_keywords === "1" || route.query.use_keywords === "0") {
    keepSourceLabels.value = route.query.use_keywords === "1";
  }
  if (route.query.edit === "1" || route.query.edit === "0") {
    stayInEditMode.value = route.query.edit === "1";
  }
  if (route.query.source === "cookbook" && !shared) {
    expecting.value = "cookbook";
  }

  if (shared || Object.keys(route.query).length) {
    // the box has what was shared, so the address doesn't need to (and shouldn't import it again on reload)
    router.replace({ query: {} });
  }
});
</script>

<style scoped>
.recipe-import {
  max-width: 760px;
  margin: 0 auto;
  padding: 40px 0 72px;
}

.recipe-import__head {
  margin-bottom: 24px;
}

.recipe-import__title {
  margin: 6px 0 0;
  font-size: 3rem;
}

.recipe-import__dek {
  max-width: 54ch;
  margin: 10px 0 0;
  font-size: 1.125rem;
}

.recipe-import__status {
  min-height: 12px;
  padding: 10px 6px 0;
}

.recipe-import__hint {
  display: flex;
  gap: 8px;
  margin: 0 0 4px;
  font-size: 0.9375rem;
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-muted));
}

.recipe-import__hint-action,
.recipe-import__source-remove,
.recipe-import__way {
  appearance: none;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  cursor: pointer;
}

.recipe-import__hint-action {
  color: rgb(var(--v-theme-tomato));
  font-weight: 600;
}

.recipe-import__hint-action:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.recipe-import__hint-icon {
  flex: none;
  margin-top: 1px;
}

.recipe-import__hint--warning {
  color: rgb(var(--v-theme-warning));
}

.recipe-import__hint--duplicate {
  color: rgb(var(--v-theme-on-background));
}

.recipe-import__source {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 20px 4px;
  padding: 6px 8px 6px 12px;
  width: fit-content;
  max-width: calc(100% - 40px);
  border-radius: 999px;
  background: rgb(var(--v-theme-wash));
  font-size: 0.875rem;
}

.recipe-import__source-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recipe-import__source-remove {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  color: rgb(var(--v-theme-ink-muted));
}

.recipe-import__cookbook {
  display: grid;
  gap: 4px;
  padding: 16px 18px 0;
}

.recipe-import__failure {
  margin-top: 16px;
  padding: 18px 20px 20px;
  border: 1px solid rgba(var(--v-theme-error), 0.35);
  border-left: 3px solid rgb(var(--v-theme-error));
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
}

.recipe-import__failure-title {
  margin: 0;
  font-size: 1.25rem;
}

.recipe-import__failure-text {
  margin: 6px 0 0;
  line-height: 1.5;
}

.recipe-import__failure-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.recipe-import__ways {
  margin-top: 36px;
}

.recipe-import__ways-title {
  margin: 0 0 12px;
  /* a kicker, though it's a heading, which would otherwise be set like one */
  font-family: var(--paper-sans);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.15em;
}

.recipe-import__ways-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.recipe-import__way {
  display: grid;
  grid-template-columns: auto 1fr;
  align-content: start;
  column-gap: 10px;
  row-gap: 2px;
  padding: 14px 16px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-background));
  text-align: left;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.recipe-import__way:hover:not(:disabled) {
  border-color: rgb(var(--v-theme-on-background));
}

.recipe-import__way:focus-visible {
  outline: 2px solid rgb(var(--v-theme-tomato));
  outline-offset: 2px;
}

.recipe-import__way:disabled {
  opacity: 0.5;
}

.recipe-import__way-icon {
  grid-row: span 2;
  color: rgb(var(--v-theme-tomato));
}

.recipe-import__way-title {
  font-weight: 600;
}

.recipe-import__way-text {
  font-size: 0.8125rem;
  line-height: 1.35;
  color: rgb(var(--v-theme-ink-muted));
}

.recipe-import__settings {
  margin-top: 28px;
}

.recipe-import__jobs {
  margin-top: 36px;
}

.recipe-import__footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin-top: 40px;
  padding-top: 16px;
  border-top: 1px solid rgb(var(--v-theme-rule));
  font-size: 0.875rem;
}

@media (max-width: 599px) {
  .recipe-import {
    padding-top: 20px;
  }

  .recipe-import__title {
    font-size: 2.25rem;
  }

  .recipe-import__dek {
    font-size: 1rem;
  }

  .recipe-import__ways-grid {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .recipe-import__way {
    grid-template-columns: 1fr;
    padding: 12px 14px;
  }

  .recipe-import__way-icon {
    grid-row: auto;
    margin-bottom: 4px;
  }
}
</style>
