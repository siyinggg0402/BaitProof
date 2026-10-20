const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }).then((r) => r.json());
const $ = (id) => document.getElementById(id);

// ---- delete / clear / previews
document.querySelectorAll(".rec-del").forEach((b) => b.addEventListener("click", async () => {
  const li = b.closest(".rec");
  b.disabled = true;
  await post("/api/records/delete", { id: li.dataset.id });
  li.remove();
}));
$("clear")?.addEventListener("click", async (e) => {
  if (e.target.dataset.sure !== "1") { e.target.dataset.sure = "1"; e.target.textContent = "Really delete everything? Click again"; return; }
  await post("/api/records/clear");
  location.reload();
});
$("pv")?.addEventListener("change", (e) => post("/api/settings/previews", { on: e.target.checked }).then(() => { if (!e.target.checked) document.querySelectorAll(".rec-preview").forEach((n) => n.remove()); }));

// ---- Telegram link
let poll = null, tick = null;
function showState(linked) {
  $("tg-badge").textContent = linked ? "Connected" : "Not connected";
  $("tg-badge").classList.toggle("ok", linked);
  $("tg-idle").hidden = linked || !$("tg-code").hidden;
  $("tg-done").hidden = !linked;
  if (linked) $("tg-code").hidden = true;
}
$("tg-connect")?.addEventListener("click", async () => {
  const r = await post("/api/telegram/code");
  $("tg-idle").hidden = true; $("tg-code").hidden = false;
  $("tg-codetext").textContent = r.code;
  $("tg-botname").textContent = r.bot ? "@" + r.bot : "(your Baitproof bot)";
  const open = $("tg-open");
  if (r.deep_link) { open.href = r.deep_link; open.hidden = false; }
  $("tg-howto").textContent = `Or open the bot and send:  /link ${r.code}`;
  let left = r.expires_in;
  clearInterval(tick); clearInterval(poll);
  tick = setInterval(() => {
    left -= 1;
    $("tg-timer").textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    if (left <= 0) { clearInterval(tick); clearInterval(poll); $("tg-code").hidden = true; $("tg-idle").hidden = false; }
  }, 1000);
  poll = setInterval(async () => {
    const s = await (await fetch("/api/telegram/status")).json();
    if (s.linked) { clearInterval(tick); clearInterval(poll); showState(true); setTimeout(() => location.reload(), 900); }
  }, 3000);
});
$("tg-unlink")?.addEventListener("click", async () => { await post("/api/telegram/unlink"); showState(false); });
