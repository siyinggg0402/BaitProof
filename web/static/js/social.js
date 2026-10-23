// Profile and friends pages: "Copy" buttons (an invite link, a friend code, a sign-in key). Everything else on these pages is plain forms.
document.querySelectorAll("[data-copy]").forEach((b) => {
  const label = b.textContent;
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); }
    catch (_) {
      const ta = document.createElement("textarea");  // an older browser, or no permission: select it and copy by hand
      ta.value = b.dataset.copy; document.body.append(ta); ta.select();
      try { document.execCommand("copy"); } catch (__) { /* nothing more to try */ }
      ta.remove();
    }
    b.textContent = b.dataset.done || label;
    setTimeout(() => { b.textContent = label; }, 1800);
  });
});

// "Join with a code": the code the person types becomes part of the address (the invite page then asks them to confirm).
const joinForm = document.getElementById("join-form");
if (joinForm) joinForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const code = document.getElementById("fcode").value.trim().toUpperCase().replace(/\s+/g, "");
  if (code) location.href = "/family/join/" + encodeURIComponent(code);
});

// the family dashboard's bars: widths are set here (the page's security policy does not allow style attributes in the markup)
document.querySelectorAll(".avgbar i[data-w]").forEach((i) => { i.style.width = Math.max(0, Math.min(100, +i.dataset.w || 0)) + "%"; });
