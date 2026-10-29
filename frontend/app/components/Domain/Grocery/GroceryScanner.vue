<template>
  <v-dialog
    v-model="open"
    fullscreen
    transition="dialog-bottom-transition"
    :scrim="false"
    class="grocery-scanner"
  >
    <div class="scanner" role="document">
      <video
        ref="video"
        class="scanner__video"
        :class="{ 'scanner__video--ready': cameraReady }"
        playsinline
        muted
        autoplay
        aria-hidden="true"
      />

      <header class="scanner__top">
        <v-btn
          icon
          variant="text"
          color="white"
          :aria-label="$t('grocery-scan.close')"
          @click="open = false"
        >
          <v-icon :icon="$globals.icons.close" />
        </v-btn>
        <span class="scanner__title">{{ title }}</span>
        <v-btn
          v-if="torchAvailable"
          icon
          variant="text"
          color="white"
          :aria-label="torchOn ? $t('grocery-scan.torch-off') : $t('grocery-scan.torch-on')"
          :aria-pressed="torchOn"
          @click="toggleTorch"
        >
          <v-icon :icon="torchOn ? $globals.icons.flashlightOff : $globals.icons.flashlight" />
        </v-btn>
        <span v-else class="scanner__top-spacer" />
      </header>

      <div
        v-if="cameraReady && !typing"
        class="scanner__guide"
        :class="{ 'scanner__guide--found': found, 'scanner__guide--photo': photoOnly }"
        aria-hidden="true"
      >
        <span v-if="!found && !photoOnly" class="scanner__line" />
      </div>

      <div v-if="!cameraReady && !typing" class="scanner__message">
        <v-progress-circular v-if="starting" indeterminate color="white" size="32" width="3" />
        <template v-else-if="cameraProblem">
          <v-icon size="40" color="white" :icon="$globals.icons.camera" />
          <p>{{ cameraProblem === 'denied' ? $t('grocery-scan.camera-denied') : $t('grocery-scan.camera-unavailable') }}</p>
        </template>
      </div>

      <form v-if="typing" class="scanner__type" @submit.prevent="submitTyped">
        <label for="scanner-typed" class="scanner__type-label">{{ $t('grocery-scan.type-label') }}</label>
        <input
          id="scanner-typed"
          ref="typedInput"
          v-model="typed"
          class="scanner__type-input"
          inputmode="numeric"
          autocomplete="off"
          maxlength="20"
          :placeholder="$t('grocery-scan.type-placeholder')"
        >
        <p v-if="typedError" class="scanner__type-error" role="alert">
          {{ typedError }}
        </p>
        <v-btn type="submit" color="white" variant="flat" class="mt-4" :disabled="!typed.trim()">
          {{ $t('grocery-scan.type-submit') }}
        </v-btn>
      </form>

      <footer class="scanner__bottom">
        <p class="scanner__hint" aria-live="polite">
          {{ hint }}
        </p>
        <div class="scanner__controls">
          <button type="button" class="scanner__side" @click="pickPhoto">
            <v-icon :icon="$globals.icons.photos" />
            <span>{{ $t('grocery-scan.choose-photo') }}</span>
          </button>
          <button
            type="button"
            class="scanner__shutter"
            :disabled="!cameraReady || busy"
            :aria-label="photos ? $t('grocery-scan.snap-package') : $t('grocery-scan.snap-barcode')"
            @click="snap"
          >
            <v-progress-circular v-if="busy" indeterminate color="white" size="28" width="3" />
          </button>
          <button type="button" class="scanner__side" :aria-pressed="typing" @click="toggleTyping">
            <v-icon :icon="typing ? $globals.icons.barcodeScan : $globals.icons.keyboard" />
            <span>{{ typing ? $t('grocery-scan.use-camera') : $t('grocery-scan.type-it') }}</span>
          </button>
        </div>
      </footer>

      <input
        ref="fileInput"
        type="file"
        accept="image/*"
        class="d-none"
        @change="onPhotoPicked"
      >
    </div>
  </v-dialog>
</template>

<script setup lang="ts">
import { looksLikeBarcode, preparePhoto, preloadBarcodeReader, readBarcode, type ScannedBarcode } from "~/composables/groceries/use-barcodes";

export interface ScannerResult {
  barcode: ScannedBarcode | null;
  /** A photo, when one was taken or chosen: of the package, for AI to read */
  photo: Blob | null;
}

const props = withDefaults(defineProps<{
  /** The household's AI can read photos, so a photo of the front of a package is worth taking */
  photos?: boolean;
  /** What the scan is for, as the scanner's title */
  title: string;
  /** Instead of the usual hint, e.g. to ask for the front of the package */
  prompt?: string;
  /**
   * A photo is what's wanted, of a package whose barcode is already known, so barcodes aren't read as
   * the camera looks: the one still in view would be read again instead of waiting for the photo
   */
  photoOnly?: boolean;
}>(), {
  photos: false,
  prompt: "",
  photoOnly: false,
});

const emit = defineEmits<{ result: [ScannerResult] }>();
const open = defineModel<boolean>({ default: false });

const i18n = useI18n();
const video = ref<HTMLVideoElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const typedInput = ref<HTMLInputElement | null>(null);

const starting = ref(false);
const cameraReady = ref(false);
const cameraProblem = ref<"denied" | "unavailable" | null>(null);
const torchAvailable = ref(false);
const torchOn = ref(false);
const found = ref(false);
const busy = ref(false);
const typing = ref(false);
const typed = ref("");
const typedError = ref("");
const notice = ref("");

const hint = computed(() => {
  if (notice.value) return notice.value;
  if (props.prompt) return props.prompt;
  if (typing.value) return i18n.t("grocery-scan.type-hint");
  if (cameraProblem.value) return props.photos ? i18n.t("grocery-scan.no-camera-photos") : i18n.t("grocery-scan.no-camera");
  return props.photos ? i18n.t("grocery-scan.hint-photos") : i18n.t("grocery-scan.hint");
});

// =========================================================
// The camera

let stream: MediaStream | null = null;
/** Bumped whenever the camera stops, so a frame that was being read when it did is ignored */
let session = 0;

async function startCamera() {
  stopCamera();
  const current = session;
  cameraProblem.value = null;
  found.value = false;
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraProblem.value = "unavailable";
    return;
  }

  starting.value = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
    });
  }
  catch (error) {
    cameraProblem.value = (error as DOMException)?.name === "NotAllowedError" ? "denied" : "unavailable";
    return;
  }
  finally {
    starting.value = false;
  }

  // closed while the browser asked for the camera
  if (current !== session || !open.value || !video.value) {
    stopCamera();
    return;
  }
  video.value.srcObject = stream;
  await video.value.play().catch(() => undefined);
  cameraReady.value = true;

  const [track] = stream.getVideoTracks();
  const capabilities = (track?.getCapabilities?.() ?? {}) as { torch?: boolean };
  torchAvailable.value = !!capabilities.torch;
  if (!props.photoOnly) keepReading(current);
}

function stopCamera() {
  session++;
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  if (video.value) video.value.srcObject = null;
  cameraReady.value = false;
  torchAvailable.value = false;
  torchOn.value = false;
}

async function toggleTorch() {
  const [track] = stream?.getVideoTracks() ?? [];
  if (!track) return;
  try {
    await track.applyConstraints({ advanced: [{ torch: !torchOn.value } as MediaTrackConstraintSet] });
    torchOn.value = !torchOn.value;
  }
  catch {
    torchAvailable.value = false;
  }
}

// =========================================================
// Reading barcodes from what the camera sees

const READ_EVERY_MS = 120;
let canvas: HTMLCanvasElement | null = null;

/** The middle of the frame, where the guide is, at a size that reads quickly */
function grabFrame(source: HTMLVideoElement): ImageData | null {
  const width = source.videoWidth;
  const height = source.videoHeight;
  if (!width || !height) return null;
  const crop = { x: width * 0.05, y: height * 0.2, width: width * 0.9, height: height * 0.6 };
  const scale = Math.min(1, 1280 / crop.width);
  canvas ??= document.createElement("canvas");
  canvas.width = Math.round(crop.width * scale);
  canvas.height = Math.round(crop.height * scale);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(source, crop.x, crop.y, crop.width, crop.height, 0, 0, canvas.width, canvas.height);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

function keepReading(current: number) {
  setTimeout(async () => {
    if (current !== session || found.value) return;
    const frame = video.value && video.value.readyState >= 2 && !busy.value ? grabFrame(video.value) : null;
    const barcode = frame ? await readBarcode(frame).catch(() => null) : null;
    if (current !== session) return;
    if (barcode && looksLikeBarcode(barcode.text)) {
      finish({ barcode, photo: null });
      return;
    }
    keepReading(current);
  }, READ_EVERY_MS);
}

function finish(result: ScannerResult) {
  found.value = true;
  navigator.vibrate?.(60);
  // long enough to see the guide turn green
  setTimeout(() => {
    emit("result", result);
    open.value = false;
  }, result.barcode && !result.photo ? 350 : 0);
}

// =========================================================
// Photos

/** Takes a photo of what the camera sees: for AI to read the package, and for any barcode in it */
async function snap() {
  const source = video.value;
  if (!source?.videoWidth) return;
  busy.value = true;
  try {
    const full = document.createElement("canvas");
    full.width = source.videoWidth;
    full.height = source.videoHeight;
    full.getContext("2d")?.drawImage(source, 0, 0);
    const blob = await new Promise<Blob | null>(resolve => full.toBlob(resolve, "image/jpeg", 0.92));
    if (blob) await usePhoto(blob);
  }
  finally {
    busy.value = false;
  }
}

function pickPhoto() {
  fileInput.value?.click();
}

async function onPhotoPicked(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  busy.value = true;
  try {
    await usePhoto(file);
  }
  finally {
    busy.value = false;
  }
}

async function usePhoto(photo: Blob) {
  notice.value = "";
  const prepared = await preparePhoto(photo);
  if (!prepared.barcode && !props.photos) {
    // without AI to read the package, a photo is only worth something for its barcode
    notice.value = i18n.t("grocery-scan.no-barcode-in-photo");
    return;
  }
  finish({ barcode: prepared.barcode, photo: props.photos ? prepared.photo : null });
}

// =========================================================
// Typing the barcode

function toggleTyping() {
  typing.value = !typing.value;
  typedError.value = "";
  if (typing.value) nextTick(() => typedInput.value?.focus());
}

function submitTyped() {
  const digits = typed.value.replace(/[\s-]/g, "");
  if (!looksLikeBarcode(digits)) {
    typedError.value = i18n.t("grocery-scan.type-invalid");
    return;
  }
  finish({ barcode: { text: digits, format: null }, photo: null });
}

// =========================================================
// Opening and closing

function onVisibility() {
  // a phone's camera is released while the app is in the background, and picked up again after
  if (document.hidden) stopCamera();
  else if (open.value && !typing.value) void startCamera();
}

watch(open, (value) => {
  if (value) {
    found.value = false;
    typing.value = false;
    typed.value = "";
    typedError.value = "";
    notice.value = "";
    preloadBarcodeReader();
    document.addEventListener("visibilitychange", onVisibility);
    nextTick(() => void startCamera());
  }
  else {
    document.removeEventListener("visibilitychange", onVisibility);
    stopCamera();
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onVisibility);
  stopCamera();
});
</script>

<style scoped>
.scanner {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #0d0b09;
  color: #fff;
}

.scanner__video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.25s ease;
}

.scanner__video--ready {
  opacity: 1;
}

.scanner__top {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: calc(env(safe-area-inset-top) + 8px) 8px 8px;
  background: linear-gradient(rgba(0, 0, 0, 0.55), transparent);
}

.scanner__title {
  font-weight: 600;
  text-align: center;
}

.scanner__top-spacer {
  width: 48px;
}

/* A barcode-shaped window, with everything around it dimmed */
.scanner__guide {
  position: absolute;
  top: 46%;
  left: 50%;
  z-index: 1;
  width: min(82vw, 440px);
  height: min(30vh, 220px);
  border: 2px solid rgba(255, 255, 255, 0.92);
  border-radius: 16px;
  box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.45);
  transform: translate(-50%, -50%);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

/* framing a whole package rather than a barcode */
.scanner__guide--photo {
  width: min(78vw, 420px);
  height: min(52vh, 460px);
  border-style: dashed;
}

.scanner__guide--found {
  border-color: #8fd18b;
  box-shadow:
    0 0 0 100vmax rgba(0, 0, 0, 0.45),
    inset 0 0 0 3px #8fd18b;
}

.scanner__line {
  position: absolute;
  left: 8%;
  right: 8%;
  top: 50%;
  height: 2px;
  border-radius: 2px;
  background: #e57b5d;
  box-shadow: 0 0 12px #e57b5d;
  animation: scanner-line 1.8s ease-in-out infinite;
}

@keyframes scanner-line {
  0%,
  100% {
    transform: translateY(-60px);
  }
  50% {
    transform: translateY(60px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .scanner__line {
    animation: none;
  }
}

.scanner__message {
  position: absolute;
  top: 42%;
  left: 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: min(84vw, 380px);
  text-align: center;
  transform: translate(-50%, -50%);
}

.scanner__message p {
  margin: 0;
  line-height: 1.45;
}

.scanner__type {
  position: absolute;
  top: 36%;
  left: 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: min(84vw, 380px);
  transform: translate(-50%, -50%);
}

.scanner__type-label {
  margin-bottom: 8px;
  font-weight: 600;
}

.scanner__type-input {
  padding: 14px 16px;
  border: 0;
  border-radius: 12px;
  outline: none;
  background: rgba(255, 255, 255, 0.95);
  color: #211c16;
  font-size: 1.375rem;
  letter-spacing: 0.08em;
  font-variant-numeric: tabular-nums;
}

.scanner__type-error {
  margin: 8px 0 0;
  color: #ffb4a2;
}

.scanner__bottom {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2;
  padding: 16px 16px calc(env(safe-area-inset-bottom) + 20px);
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65) 30%);
}

.scanner__hint {
  max-width: 420px;
  margin: 0 auto 18px;
  font-size: 0.9375rem;
  line-height: 1.4;
  text-align: center;
}

.scanner__controls {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  max-width: 420px;
  margin: 0 auto;
}

.scanner__side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px 4px;
  border: 0;
  background: none;
  color: #fff;
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}

.scanner__shutter {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  border: 4px solid #fff;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  cursor: pointer;
  transition:
    transform 0.1s ease,
    background-color 0.1s ease;
}

.scanner__shutter:active:not(:disabled) {
  transform: scale(0.94);
  background: rgba(255, 255, 255, 0.45);
}

.scanner__shutter:disabled {
  opacity: 0.4;
  cursor: default;
}

.scanner__side:focus-visible,
.scanner__shutter:focus-visible {
  outline: 2px solid #e57b5d;
  outline-offset: 3px;
}
</style>
