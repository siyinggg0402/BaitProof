// The little service worker that lets a phone treat Baitproof as an app (and list it in the Share menu, where the browser allows that).
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch
