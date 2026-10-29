// Profile, friends and family pages. (The "Copy" buttons are handled for every page in app.js.) Everything else on these pages is plain forms.

// "Join with a code": the code the person types becomes part of the address (the invite page then asks them to confirm).
const joinForm = document.getElementById("join-form");
if (joinForm) joinForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const code = document.getElementById("fcode").value.trim().toUpperCase().replace(/\s+/g, "");
  if (code) location.href = "/family/join/" + encodeURIComponent(code);
});

// the family dashboard's bars: widths are set here (the page's security policy does not allow style attributes in the markup)
document.querySelectorAll(".avgbar i[data-w]").forEach((i) => { i.style.width = Math.max(0, Math.min(100, +i.dataset.w || 0)) + "%"; });
