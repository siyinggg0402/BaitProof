// Baitproof's service worker. It exists so the phone offers to install the site as an app, lists it in the Share menu, and can show the "a friend just passed you"
// notifications people asked for. It caches nothing on purpose: a scam checker must always show the live answer, never an old one.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => { /* every request goes straight to the network */ });

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) { data = {}; }
  const title = String(data.title || "Baitproof").slice(0, 120);
  event.waitUntil(self.registration.showNotification(title, {
    body: String(data.body || "").slice(0, 240), icon: "/static/img/icon-192.png", badge: "/static/img/icon-192.png",
    tag: String(data.tag || "baitproof"), renotify: true, data: { url: /^\/(?!\/)/.test(String(data.url || "")) ? String(data.url) : "/" },   // only a path on this site (a "//host" address is not one)
  }));
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
