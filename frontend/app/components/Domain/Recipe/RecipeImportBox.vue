<template>
  <div
    class="import-box"
    :class="{ 'import-box--dragging': dragging, 'import-box--busy': busy }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <div v-if="files.length" class="import-box__files">
      <template v-for="(file, index) in files" :key="fileKeys[index]">
        <figure v-if="previews[index]" class="import-box__photo">
          <img :src="previews[index]" :alt="file.name">
          <figcaption v-if="photoCount > 1 && index === 0" class="import-box__cover">
            {{ $t("recipe-import.cover-photo") }}
          </figcaption>
          <button
            v-else-if="photoCount > 1 && !busy"
            type="button"
            class="import-box__make-cover"
            :aria-label="$t('recipe-import.use-as-cover-photo', { name: file.name })"
            :title="$t('recipe-import.use-as-cover-photo', { name: file.name })"
            @click="makeCover(index)"
          >
            <v-icon size="14" :icon="$globals.icons.star" />
          </button>
          <button
            v-if="!busy"
            type="button"
            class="import-box__remove"
            :aria-label="$t('recipe-import.remove-file', { name: file.name })"
            @click="removeFile(index)"
          >
            <v-icon size="14" :icon="$globals.icons.close" />
          </button>
        </figure>
        <div v-else class="import-box__file">
          <v-icon size="22" :icon="importFileKind(file) === 'archive' ? $globals.icons.zip : $globals.icons.book" />
          <div class="import-box__file-text">
            <span class="import-box__file-name">{{ file.name }}</span>
            <span class="import-box__file-size">{{ fileSize(file.size) }}</span>
          </div>
          <button
            v-if="!busy"
            type="button"
            class="import-box__file-remove"
            :aria-label="$t('recipe-import.remove-file', { name: file.name })"
            @click="removeFile(index)"
          >
            <v-icon size="16" :icon="$globals.icons.close" />
          </button>
        </div>
      </template>
    </div>

    <textarea
      v-if="!hideText"
      ref="textarea"
      v-model="text"
      class="import-box__input"
      :placeholder="placeholder"
      :aria-label="label"
      :readonly="busy"
      rows="1"
      spellcheck="false"
      autocomplete="off"
      autocapitalize="off"
      :enterkeyhint="submitOnEnter ? 'go' : 'enter'"
      @keydown.enter="onEnter"
      @paste="onPaste"
    />

    <slot name="details" />

    <div class="import-box__footer">
      <slot v-if="busy" name="busy" />
      <template v-else>
        <div class="import-box__tools">
          <v-btn
            v-if="canPaste && !text && !files.length"
            variant="text"
            size="small"
            class="import-box__tool"
            :prepend-icon="$globals.icons.contentPaste"
            @click="pasteFromClipboard"
          >
            {{ $t("recipe-import.paste") }}
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            class="import-box__tool"
            :prepend-icon="$globals.icons.paperclip"
            @click="pickFiles()"
          >
            {{ $t("recipe-import.add-files") }}
          </v-btn>
        </div>
        <v-btn
          color="primary"
          variant="flat"
          size="large"
          class="import-box__submit"
          :disabled="submitDisabled"
          @click="emit('submit')"
        >
          {{ submitLabel }}
          <v-icon end :icon="$globals.icons.arrowRight" />
        </v-btn>
      </template>
    </div>

    <input
      ref="fileInput"
      type="file"
      class="d-none"
      multiple
      :accept="pickerAccept"
      @change="onPicked"
    >
  </div>
</template>

<script setup lang="ts">
import { IMPORT_FILE_TYPES, importFileKind } from "~/composables/use-recipe-import";

const props = withDefaults(defineProps<{
  placeholder: string;
  label: string;
  submitLabel: string;
  submitDisabled?: boolean;
  busy?: boolean;
  /** Enter imports, rather than starting a new line */
  submitOnEnter?: boolean;
  /** For files with no text to go with them, like a cookbook */
  hideText?: boolean;
  autofocus?: boolean;
}>(), {
  submitDisabled: false,
  busy: false,
  submitOnEnter: false,
  hideText: false,
  autofocus: false,
});

const emit = defineEmits<{
  (e: "submit"): void;
  /** Files of a type none of the importers read */
  (e: "rejected", files: File[]): void;
}>();

const text = defineModel<string>("text", { required: true });
const files = defineModel<File[]>("files", { required: true });

const textarea = ref<HTMLTextAreaElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const pickerAccept = ref<string>(Object.values(IMPORT_FILE_TYPES).join(","));

// =========================================================
// Files

const photoCount = computed(() => files.value.filter(file => importFileKind(file) === "photo").length);

// Object URLs for photo previews, made once per file and released when it's removed
const previewCache = new Map<File, string>();
const previews = computed(() => files.value.map((file) => {
  if (importFileKind(file) !== "photo") {
    return null;
  }
  let url = previewCache.get(file);
  if (!url) {
    url = URL.createObjectURL(file);
    previewCache.set(file, url);
  }
  return url;
}));

// Files have no identity of their own to key a list by
const keys = new WeakMap<File, number>();
let nextKey = 0;
const fileKeys = computed(() => files.value.map((file) => {
  if (!keys.has(file)) {
    keys.set(file, nextKey++);
  }
  return keys.get(file)!;
}));

watch(files, (current) => {
  for (const [file, url] of previewCache) {
    if (!current.includes(file)) {
      URL.revokeObjectURL(url);
      previewCache.delete(file);
    }
  }
});

onBeforeUnmount(() => {
  previewCache.forEach(url => URL.revokeObjectURL(url));
  previewCache.clear();
});

function addFiles(added: File[]) {
  const accepted = added.filter(file => importFileKind(file) !== "other");
  const rejected = added.filter(file => importFileKind(file) === "other");
  if (rejected.length) {
    emit("rejected", rejected);
  }
  if (accepted.length) {
    files.value = [...files.value, ...accepted];
  }
}

function removeFile(index: number) {
  files.value = files.value.filter((_, i) => i !== index);
}

/** The first photo becomes the recipe's image */
function makeCover(index: number) {
  const file = files.value[index];
  if (!file) {
    return;
  }
  files.value = [file, ...files.value.filter((_, i) => i !== index)];
}

function fileSize(bytes: number) {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Opens the file picker, for any of the importers' file types or just one kind */
function pickFiles(accept?: string) {
  pickerAccept.value = accept ?? Object.values(IMPORT_FILE_TYPES).join(",");
  // the accept list has to be in place before the picker opens
  nextTick(() => fileInput.value?.click());
}

function onPicked(event: Event) {
  const input = event.target as HTMLInputElement;
  addFiles(Array.from(input.files ?? []));
  // so picking the same file again still counts as a change
  input.value = "";
}

// =========================================================
// Dragging and pasting

const dragging = ref(false);
let dragDepth = 0;

function onDragEnter() {
  if (props.busy) {
    return;
  }
  dragDepth++;
  dragging.value = true;
}

function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) {
    dragging.value = false;
  }
}

function onDrop(event: DragEvent) {
  dragDepth = 0;
  dragging.value = false;
  if (props.busy || !event.dataTransfer) {
    return;
  }

  const dropped = Array.from(event.dataTransfer.files);
  if (dropped.length) {
    addFiles(dropped);
    return;
  }

  // a link dragged from another tab
  const droppedText = event.dataTransfer.getData("text/uri-list") || event.dataTransfer.getData("text/plain");
  if (droppedText) {
    text.value = text.value.trim() ? `${text.value.trim()}\n${droppedText.trim()}` : droppedText.trim();
  }
}

/** Screenshots pasted into the box are attached as photos */
function onPaste(event: ClipboardEvent) {
  const pasted = Array.from(event.clipboardData?.files ?? []);
  if (pasted.length) {
    event.preventDefault();
    addFiles(pasted);
  }
}

const canPaste = ref(false);
onMounted(() => {
  canPaste.value = typeof navigator !== "undefined" && !!navigator.clipboard?.readText;
});

async function pasteFromClipboard() {
  try {
    const clipboard = await navigator.clipboard.readText();
    if (clipboard.trim()) {
      text.value = clipboard.trim();
      return;
    }
  }
  catch {
    // the browser said no; pasting by hand still works
  }
  focus();
}

// =========================================================
// Typing

function onEnter(event: KeyboardEvent) {
  if (event.isComposing) {
    return;
  }
  // Cmd/Ctrl+Enter always imports; plain Enter does when the box holds just a link
  if (event.metaKey || event.ctrlKey || (props.submitOnEnter && !event.shiftKey)) {
    event.preventDefault();
    if (!props.submitDisabled && !props.busy) {
      emit("submit");
    }
  }
}

const MAX_HEIGHT = 360;

function resize() {
  const el = textarea.value;
  if (!el) {
    return;
  }
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? "auto" : "hidden";
}

watch(text, () => nextTick(resize));
onMounted(() => {
  resize();
  // the autofocus attribute only works on a page's first load, not on one the app navigates to
  if (props.autofocus) {
    focus();
  }
});

function focus() {
  textarea.value?.focus();
}

defineExpose({ focus, pickFiles });
</script>

<style scoped>
.import-box {
  position: relative;
  display: flex;
  flex-direction: column;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), 0.26);
  border-radius: 14px;
  box-shadow:
    0 1px 2px rgba(var(--v-shadow-color), 0.04),
    0 14px 32px -24px rgba(var(--v-shadow-color), 0.4);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    background-color 0.15s ease;
}

.import-box:focus-within {
  border-color: rgb(var(--v-theme-on-surface));
}

.import-box--dragging {
  border-color: rgb(var(--v-theme-tomato));
  border-style: dashed;
  background: rgb(var(--v-theme-wash));
}

.import-box__input {
  display: block;
  width: 100%;
  min-height: 64px;
  padding: 18px 20px 6px;
  border: 0;
  outline: none;
  resize: none;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  font-family: var(--paper-sans);
  /* 17px keeps iOS from zooming in on focus */
  font-size: 1.0625rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.import-box__input::placeholder {
  color: rgb(var(--v-theme-ink-muted));
  opacity: 1;
}

.import-box--busy .import-box__input {
  color: rgb(var(--v-theme-ink-muted));
}

.import-box__files {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 16px 18px 0;
}

.import-box__photo {
  position: relative;
  width: 76px;
  height: 76px;
  margin: 0;
}

.import-box__photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-light));
}

.import-box__cover {
  position: absolute;
  left: 4px;
  bottom: 4px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(33, 28, 22, 0.78);
  color: #fcf9f3;
  font-size: 0.625rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.import-box__remove,
.import-box__make-cover,
.import-box__file-remove {
  appearance: none;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  cursor: pointer;
}

.import-box__remove,
.import-box__make-cover {
  position: absolute;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: rgba(33, 28, 22, 0.78);
  color: #fcf9f3;
}

.import-box__remove {
  top: -6px;
  right: -6px;
}

.import-box__make-cover {
  left: 4px;
  bottom: 4px;
  opacity: 0.85;
}

.import-box__file {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 100%;
  padding: 10px 12px 10px 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  background: rgb(var(--v-theme-background));
}

.import-box__file-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.import-box__file-name {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.import-box__file-size {
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
}

.import-box__file-remove {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-left: 4px;
  border-radius: 999px;
  color: rgb(var(--v-theme-ink-muted));
}

.import-box__file-remove:hover {
  background: rgba(var(--v-border-color), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.import-box__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px 12px 10px;
}

.import-box__tools {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
}

.import-box__tool {
  color: rgb(var(--v-theme-ink-muted));
}

.import-box__submit {
  margin-left: auto;
  padding-inline: 22px;
}

@media (max-width: 599px) {
  .import-box__input {
    min-height: 88px;
    padding: 16px 16px 4px;
  }

  .import-box__files {
    padding: 14px 16px 0;
  }

  .import-box__submit {
    width: 100%;
  }
}
</style>
