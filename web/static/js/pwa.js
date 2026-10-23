// Install Baitproof as an app (the Share menu then lists it) and register the little service worker that lets the phone do that.
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => { /* an older browser, or private mode: the site works the same */ });
(() => {
  const btn = document.getElementById("install-btn");
  if (!btn) return;
  let offer = null;
  addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); offer = e; btn.hidden = false; });
  btn.addEventListener("click", async () => { if (!offer) return; btn.hidden = true; offer.prompt(); try { await offer.userChoice; } catch (e) { /* closed */ } offer = null; });
  addEventListener("appinstalled", () => { btn.hidden = true; });
})();
