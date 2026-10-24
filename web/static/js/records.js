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
  if (e.target.dataset.sure !== "1") { e.target.dataset.sure = "1"; e.target.textContent = t("Really delete everything? Click again"); return; }
  await post("/api/records/clear");
  location.reload();
});
$("pv")?.addEventListener("change", (e) => post("/api/settings/previews", { on: e.target.checked }).then(() => { if (!e.target.checked) document.querySelectorAll(".rec-preview").forEach((n) => n.remove()); }));
