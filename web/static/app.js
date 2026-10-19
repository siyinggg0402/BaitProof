// Shared helpers (loaded before fx.js; animateNumber/reduce come from fx.js and are only used after load).
document.querySelectorAll(".speak").forEach((b) =>
  b.addEventListener("click", () => {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(b.dataset.say));
  })
);

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
  return el("button", { className: "speak", textContent: "🔊 Read aloud", onclick: () => {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  } });
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
