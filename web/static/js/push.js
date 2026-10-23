// Notifications: ask this browser for permission, hand the server the address it can reach us on, and show whether it is on. Only runs where the site
// has push keys (the page only includes this file then) and the browser can do push at all; otherwise the card stays hidden.
(async () => {
  const box = document.getElementById("push-box");
  if (!box || !("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return;
  const $ = (id) => document.getElementById(id);
  let cfg;
  try { cfg = await (await fetch("/api/push/config")).json(); } catch (_) { return; }
  if (!cfg.enabled) return;
  const reg = await navigator.serviceWorker.ready.catch(() => null);
  if (!reg) return;
  box.hidden = false;
  const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const key = Uint8Array.from(atob(cfg.key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (cfg.key.length % 4)) % 4)), (c) => c.charCodeAt(0));

  async function paint() {
    const sub = await reg.pushManager.getSubscription();
    const on = !!sub && Notification.permission === "granted";
    $("push-on").hidden = on; $("push-off").hidden = !on; $("push-test").hidden = !on;
    $("push-on").disabled = Notification.permission === "denied";
    $("push-status").textContent = Notification.permission === "denied" ? t("Notifications are blocked in your browser's settings for this site.") : on ? t("Notifications are on for this device.") : "";
  }
  $("push-on").addEventListener("click", async () => {
    try {
      if ((await Notification.requestPermission()) !== "granted") return paint();
      const sub = (await reg.pushManager.getSubscription()) || (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key }));
      const j = sub.toJSON();
      const r = await post("/api/push/subscribe", { endpoint: j.endpoint, keys: j.keys });
      if (!r.ok) { await sub.unsubscribe(); $("push-status").textContent = t("That didn't work. Try again later."); return; }
    } catch (_) { $("push-status").textContent = t("That didn't work. Try again later."); return; }
    paint();
  });
  $("push-off").addEventListener("click", async () => {
    const sub = await reg.pushManager.getSubscription();
    if (sub) { await post("/api/push/unsubscribe", { endpoint: sub.endpoint }); await sub.unsubscribe(); }
    paint();
  });
  $("push-test").addEventListener("click", async () => {
    const r = await post("/api/push/test").then((x) => x.json()).catch(() => ({ sent: 0 }));
    $("push-status").textContent = r.sent ? t("Test sent. Look for the notification.") : t("That didn't work. Try again later.");
  });
  paint();
})();
