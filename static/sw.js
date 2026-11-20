// Peek service worker: shows push notifications and opens the app when tapped.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "Peek", body: event.data && event.data.text() }; }
  const title = data.title || "Peek";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    timestamp: (data.ts || Date.now() / 1000) * 1000,
    data: { url: data.url || "/#timeline" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of all) {
      if ("focus" in client) {
        await client.focus();
        if ("navigate" in client) client.navigate(url).catch(() => {});
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});

// A fetch handler (network only) so browsers treat this as an installable app.
self.addEventListener("fetch", () => {});
