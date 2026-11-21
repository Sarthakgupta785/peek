// Peek service worker: shows push notifications and opens the app when tapped.

const SHELL_CACHE = "peek-shell-v1";
const SHELL_FILES = ["/offline", "/welcome", "/static/style.css", "/static/offline.js", "/static/icons/peek.svg",
                     "/static/icons/icon-180.png", "/static/icons/icon-192.png"];
const SKIP_NOTICE = { "ngrok-skip-browser-warning": "1" };
// ngrok's "can't reach the PC" answers. Anything else (including its access-denied page) passes through.
const OFFLINE_CODES = new Set(["ERR_NGROK_3200", "ERR_NGROK_3004", "ERR_NGROK_8012"]);

async function cacheShell() {
  const cache = await caches.open(SHELL_CACHE);
  await Promise.all(SHELL_FILES.map(async (path) => {
    try {
      const res = await fetch(path, { cache: "no-store", headers: SKIP_NOTICE });
      if (res.ok && res.headers.get("X-Peek")) await cache.put(path, res);
    } catch { /* offline right now: keep any older copy */ }
  }));
}

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(cacheShell());
});
self.addEventListener("activate", (event) => event.waitUntil((async () => {
  for (const name of await caches.keys()) {
    if (name.startsWith("peek-shell-") && name !== SHELL_CACHE) await caches.delete(name);
  }
  await self.clients.claim();
})()));

async function offlinePage() {
  const page = await caches.match("/offline");
  return page || new Response("<!doctype html><meta name=viewport content='width=device-width'>" +
    "<title>Peek</title><body style='background:#0B1120;color:#e5e9f2;font:16px system-ui;padding:32px'>" +
    "<h1>peek</h1><p>Your PC is offline. Try again in a moment.</p>",
    { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

// /api/login-info sits behind Google sign-in, so a redirect here means Google is needed.
// (A redirect on "/" alone could also just be Peek sending you to its own login page.)
async function needsGoogle() {
  try {
    const res = await fetch("/api/login-info", { headers: SKIP_NOTICE, credentials: "include",
                                                 redirect: "manual", cache: "no-store" });
    return res.type === "opaqueredirect";
  } catch {
    return false;
  }
}

async function openPage(request) {
  const url = new URL(request.url);
  if (url.searchParams.has("signin")) {          // "Continue with Google": the browser's normal route
    try {
      const direct = await fetch(request);
      return OFFLINE_CODES.has(direct.headers.get("ngrok-error-code")) ? offlinePage() : direct;
    } catch {
      return offlinePage();
    }
  }
  let res;
  try {
    // Signed-in visits skip ngrok's "You are about to visit" notice.
    res = await fetch(request.url, { headers: SKIP_NOTICE, credentials: "include", redirect: "manual" });
  } catch {
    return offlinePage();
  }
  if (OFFLINE_CODES.has(res.headers.get("ngrok-error-code"))) return offlinePage();
  if (res.type === "opaqueredirect") {
    if ((url.pathname === "/" || url.pathname === "/login") && !url.search && await needsGoogle()) {
      const welcome = await caches.match("/welcome");
      if (welcome) return welcome;
    }
    return fetch(request);                       // any other redirect: follow it normally
  }
  return res;
}

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

// The offline screen's own files: use the latest copy, or the saved one while the PC is unreachable.
async function shellFile(request, path) {
  try {
    const res = await fetch(request.url, { headers: SKIP_NOTICE, cache: "no-cache" });
    if (res.ok && res.headers.get("X-Peek")) {
      (await caches.open(SHELL_CACHE)).put(path, res.clone());
      return res;
    }
    if (!OFFLINE_CODES.has(res.headers.get("ngrok-error-code"))) return res;
  } catch { /* unreachable: fall through to the saved copy */ }
  return (await caches.match(path)) || new Response("", { status: 503 });
}

// Page loads go through openPage so ngrok's error pages become Peek's own offline screen.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (event.request.mode === "navigate") event.respondWith(openPage(event.request));
  else if (SHELL_FILES.includes(url.pathname)) event.respondWith(shellFile(event.request, url.pathname));
});
