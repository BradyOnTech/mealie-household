/// <reference lib="webworker" />
/**
 * The app's service worker. It precaches the build the way the generated one did, and adds Web Push:
 * household messages arrive as notifications, set the count on the app's icon, and open the conversation
 * when tapped.
 *
 * It lives outside app/ because it's typed for a worker, not a page; vite-plugin-pwa builds it to /sw.js.
 */
import { clientsClaim } from "workbox-core";
import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching";

declare const self: ServiceWorkerGlobalScope;

void self.skipWaiting();
clientsClaim();

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();
// No app-shell route for navigation: index.html isn't precached (see nuxt.config.ts), so binding one to "/"
// throws. The generated worker tried, and lost only that route because its loader swallowed the error.

interface PushData {
  title?: string;
  body?: string;
  url?: string;
  tag?: string;
  /** The number to show on the app's icon */
  badge?: number;
}

/** Messages to the app's open windows; use-service-worker-notices.ts reads them */
type ServiceWorkerNotice
  = | { type: "household-message" }
    | { type: "open"; url: string };

type BadgingNavigator = WorkerNavigator & {
  setAppBadge?: (count?: number) => Promise<void>;
  clearAppBadge?: () => Promise<void>;
};

async function setBadge(count: number | undefined) {
  if (count === undefined) return;
  const nav = self.navigator as BadgingNavigator;
  try {
    await (count > 0 ? nav.setAppBadge?.(count) : nav.clearAppBadge?.());
  }
  catch {
    // Badges are a nicety; not every browser allows them
  }
}

function readPush(event: PushEvent): PushData {
  try {
    return (event.data?.json() as PushData | undefined) ?? {};
  }
  catch {
    return { body: event.data?.text() };
  }
}

async function windows() {
  return await self.clients.matchAll({ type: "window", includeUncontrolled: true });
}

self.addEventListener("push", (event) => {
  const data = readPush(event);
  // iOS takes notifications away from apps that receive a push without showing one, so always show it
  event.waitUntil(Promise.all([
    self.registration.showNotification(data.title || "Mealie", {
      body: data.body,
      tag: data.tag,
      icon: "/icons/android-chrome-192x192.png",
      data: { url: data.url || "/" },
    }),
    setBadge(data.badge),
    // An open app fetches the new message right away instead of on its next poll
    windows().then(clients => clients.forEach(client => client.postMessage({ type: "household-message" } satisfies ServiceWorkerNotice))),
  ]));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data?.url as string | undefined) || "/", self.location.origin);

  event.waitUntil((async () => {
    const [client] = await windows();
    if (client) {
      // The app routes itself, which keeps its state instead of reloading the page
      await client.focus();
      client.postMessage({ type: "open", url: url.pathname + url.search } satisfies ServiceWorkerNotice);
      return;
    }
    await self.clients.openWindow(url.href);
  })());
});
