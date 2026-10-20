const fam = document.getElementById("family");
if (fam) fam.append(familyBox(fam.dataset.pct, fam.dataset.url));
document.getElementById("share").addEventListener("click", async (e) => {
  const { url, text } = e.target.dataset, note = document.getElementById("shared");
  try {
    if (navigator.share) return await navigator.share({ title: "Baitproof", text, url });
    await navigator.clipboard.writeText(`${text} ${url}`);
    note.textContent = t("Copied! Paste it into a message to your family.");
  } catch (_) {
    note.textContent = t("Copy this link:") + " " + url;
  }
});
