import { createSharedComposable } from "@vueuse/core";
import { useUserApi } from "~/composables/api";
import { groceryError } from "~/composables/groceries/grocery-utils";

/**
 * - `unsupported`: this browser can't, or the app's service worker isn't running (as in development)
 * - `needs-install`: an iPhone or iPad in Safari; push only works once the app is on the Home Screen
 * - `denied`: the user said no, which only the device's settings can undo
 * - `off` / `on`: whether this device gets notifications
 */
export type WebPushState = "checking" | "unsupported" | "needs-install" | "denied" | "off" | "on";

export function isAppleMobile() {
  const nav = navigator as Navigator & { standalone?: boolean };
  // iPads ask for desktop sites, so they look like a Mac with a touch screen
  return /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === "MacIntel" && nav.maxTouchPoints > 1);
}

export function isInstalled() {
  const nav = navigator as Navigator & { standalone?: boolean };
  return window.matchMedia("(display-mode: standalone)").matches || nav.standalone === true;
}

const SW_WAIT = 5_000;

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** A VAPID key, base64url as the server sends it, in the form `pushManager.subscribe` takes */
export function applicationServerKey(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const key = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index++) key[index] = raw.charCodeAt(index);
  return key;
}

function sameKey(subscription: PushSubscription, key: Uint8Array) {
  const current = subscription.options?.applicationServerKey;
  if (!current) return true; // Not every browser says; assume it's ours
  const bytes = new Uint8Array(current);
  return bytes.length === key.length && bytes.every((byte, index) => byte === key[index]);
}

/**
 * Notifications for household messages on this device. Every launch re-sends the device's subscription,
 * since iOS can drop or replace one without telling the app, and the server forgets those push services
 * report gone.
 */
export const useWebPush = createSharedComposable(() => {
  const api = useUserApi();
  const state = ref<WebPushState>("checking");
  const busy = ref(false);
  const error = ref("");
  let serverKey: Uint8Array<ArrayBuffer> | null = null;

  /** The app's service worker, waiting a little on a first visit while it installs; none in development */
  async function registration() {
    const timeout = new Promise<undefined>(resolve => setTimeout(() => resolve(undefined), SW_WAIT));
    return await Promise.race([navigator.serviceWorker.ready, timeout]);
  }

  async function loadKey() {
    if (serverKey) return serverKey;
    const { data } = await api.messages.pushConfig();
    serverKey = data ? applicationServerKey(data.publicKey) : null;
    return serverKey;
  }

  async function save(subscription: PushSubscription) {
    const json = subscription.toJSON();
    if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) throw new Error("The browser gave an incomplete subscription.");
    const { data, error: failure } = await api.messages.subscribe({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    });
    if (!data) throw failure;
  }

  async function refresh() {
    if (!import.meta.client) return;
    if (!pushSupported()) {
      state.value = isAppleMobile() && !isInstalled() ? "needs-install" : "unsupported";
      return;
    }
    if (Notification.permission === "denied") {
      state.value = "denied";
      return;
    }
    const reg = await registration();
    if (!reg) {
      state.value = "unsupported";
      return;
    }
    const key = await loadKey();
    try {
      let subscription = await reg.pushManager.getSubscription();
      if (subscription && key && !sameKey(subscription, key)) {
        // The server's key changed, so this subscription can't be sent to any more
        await subscription.unsubscribe();
        subscription = Notification.permission === "granted" && key
          ? await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
          : null;
      }
      if (!subscription || Notification.permission !== "granted") {
        state.value = "off";
        return;
      }
      await save(subscription);
      state.value = "on";
    }
    catch (cause) {
      state.value = "off";
      error.value = groceryError(cause);
    }
  }

  /** Call straight from a tap: iOS only asks for permission in response to one */
  async function enable() {
    if (busy.value) return;
    busy.value = true;
    error.value = "";
    try {
      // Ask first, before anything else is awaited, so the tap still counts
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        state.value = permission === "denied" ? "denied" : "off";
        return;
      }
      const reg = await registration();
      const key = await loadKey();
      if (!reg || !key) {
        state.value = "unsupported";
        return;
      }
      const subscription = (await reg.pushManager.getSubscription())
        ?? await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
      await save(subscription);
      state.value = "on";
    }
    catch (cause) {
      error.value = groceryError(cause);
    }
    finally {
      busy.value = false;
    }
  }

  async function disable() {
    if (busy.value) return;
    busy.value = true;
    error.value = "";
    try {
      const subscription = await (await registration())?.pushManager.getSubscription();
      if (subscription) {
        await api.messages.unsubscribe(subscription.endpoint);
        await subscription.unsubscribe();
      }
      state.value = "off";
    }
    catch (cause) {
      error.value = groceryError(cause);
    }
    finally {
      busy.value = false;
    }
  }

  /** Send a notification to this user's own devices; resolves to how many it went to */
  async function test() {
    error.value = "";
    const { data, error: failure } = await api.messages.sendTest();
    if (!data) error.value = groceryError(failure);
    return data?.sent ?? 0;
  }

  return { state, busy, error, refresh, enable, disable, test };
});
