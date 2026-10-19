document.querySelectorAll(".speak").forEach((b) =>
  b.addEventListener("click", () => {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(b.dataset.say));
  })
);
function renderMap(m) {
  const ul = document.getElementById("map");
  if (!ul) return;
  document.getElementById("score").textContent = m.score;
  ul.replaceChildren(...m.tactics.map((t) => {
    const li = document.createElement("li");
    const n = Object.assign(document.createElement("span"), { className: "tname", textContent: t.label });
    const bars = Object.assign(document.createElement("span"), { className: "bars" });
    for (let i = 0; i < 5; i++) bars.append(Object.assign(document.createElement("i"), { className: (i < t.bars ? "on " : "") + t.level }));
    const l = Object.assign(document.createElement("span"), { className: "lvl " + t.level, textContent: t.level_text });
    li.append(n, bars, l);
    return li;
  }));
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
