// Shared helpers (loaded before fx.js; animateNumber/reduce come from fx.js and are only used after load).
// Delegated, so buttons inside a result swapped in by the live view work too.
document.addEventListener("click", (e) => {
  const sp = e.target.closest(".speak[data-say]");
  if (sp) say(sp.dataset.say);
  const fb = e.target.closest("[data-feedback]");
  if (fb) {
    const row = fb.closest(".feedback-row"), id = fb.closest("[data-check]")?.dataset.check;
    if (!id) return;
    row.querySelectorAll("button").forEach((b) => (b.disabled = true));
    fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ check_id: id, rating: fb.dataset.feedback }) })
      .then(() => { row.querySelector("[data-fb-note]").textContent = t("Thanks. I only keep your thumb, never your message."); })
      .catch(() => row.querySelectorAll("button").forEach((b) => (b.disabled = false)));
  }
});

let mapFilter = "all";
function applyFilter() {
  document.querySelectorAll("#map li").forEach((li) => {
    const lv = li.dataset.level;
    li.hidden = !(mapFilter === "all" || (mapFilter === "weak" ? lv === "weak" || lv === "untested" : lv === mapFilter));
  });
}
document.querySelectorAll(".filters button").forEach((b) =>
  b.addEventListener("click", () => {
    mapFilter = b.dataset.filter;
    document.querySelectorAll(".filters button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    applyFilter();
  })
);

function renderMap(m) {
  const ul = document.getElementById("map");
  if (!ul) return;
  animateNumber(document.getElementById("score"), m.score, 800);
  document.getElementById("ring")?.setAttribute("stroke-dasharray", `${m.score} 100`);
  ul.replaceChildren(...m.tactics.map((t) => {
    const li = el("li", { className: "tick" });
    li.dataset.level = t.level;
    const bars = el("span", { className: "bars" });
    for (let i = 0; i < 5; i++) bars.append(el("i", { className: (i < t.bars ? "on " : "") + t.level }));
    li.append(el("span", { className: "tname", textContent: t.label }), bars, el("span", { className: "lvl " + t.level, textContent: t.level_text }));
    return li;
  }));
  applyFilter();
}
function el(tag, props, ...kids) {
  const e = Object.assign(document.createElement(tag), props || {});
  e.append(...kids);
  return e;
}
function speakBtn(text) {
  return el("button", { className: "speak", textContent: "🔊 " + t("Read aloud"), onclick: () => say(text) });
}
function progress(done, total) {
  const bar = el("div", { className: "progress", ariaHidden: "true" });
  for (let i = 0; i < total; i++) bar.append(el("i", { className: i < done ? "done" : i === done ? "now" : "" }));
  return bar;
}
const LETTERS = "ABCD";
function option(text, i, onclick) {
  return el("button", { className: "opt", onclick }, el("kbd", { textContent: LETTERS[i] }), el("span", { textContent: text }));
}

// text size toggle (remembered in this browser only)
document.getElementById("textsize")?.addEventListener("click", (e) => {
  const on = document.documentElement.classList.toggle("big");
  e.currentTarget.setAttribute("aria-pressed", String(on));
  try { localStorage.setItem("bp-big", on ? "1" : "0"); } catch (_) {}
});
document.getElementById("textsize")?.setAttribute("aria-pressed", String(document.documentElement.classList.contains("big")));

// "Send it to Mum": pre-written, personalised share links (WhatsApp / SMS / email / copy).
function familyBox(pct, link) {
  const msg = (name) => t("Hi {name}, I just tried a quick 2-minute quiz on spotting scam messages and got {pct}%. Scammers target families like ours, so could you try it too? {link}", { name: name || t("there"), pct, link });
  const name = el("input", { value: t("Mum"), maxLength: 30, ariaLabel: t("Who is this for?") });
  const wa = el("a", { className: "btn sec", target: "_blank", rel: "noopener", textContent: t("WhatsApp") });
  const sms = el("a", { className: "btn sec", textContent: t("Text message") });
  const mail = el("a", { className: "btn sec", textContent: t("Email") });
  const note = el("p", { className: "muted", ariaLive: "polite" });
  const copy = el("button", { type: "button", className: "btn sec", textContent: t("Copy message"), onclick: async () => {
    try { await navigator.clipboard.writeText(msg(name.value)); note.textContent = t("Copied! Paste it into any chat."); }
    catch (_) { note.textContent = msg(name.value); }
  } });
  const update = () => {
    const x = encodeURIComponent(msg(name.value));
    wa.href = `https://wa.me/?text=${x}`;
    sms.href = `sms:?&body=${x}`;
    mail.href = `mailto:?subject=${encodeURIComponent(t("Can you try this scam quiz?"))}&body=${x}`;
  };
  name.addEventListener("input", update);
  update();
  return el("div", { className: "panel family" },
    el("b", { textContent: t("Send it to someone you want to protect") }),
    el("label", { textContent: t("Who is it for?") }), name,
    el("div", { className: "famrow" }, wa, sms, mail, copy), note);
}

// language menu (a <details>): Escape or a click anywhere else closes it
const langMenu = document.getElementById("lang");
if (langMenu) {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && langMenu.open) { langMenu.open = false; langMenu.querySelector("summary").focus(); }
  });
  document.addEventListener("click", (e) => { if (langMenu.open && !langMenu.contains(e.target)) langMenu.open = false; });
}
