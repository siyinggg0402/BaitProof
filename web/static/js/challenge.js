const stage = document.getElementById("stage");
const items = JSON.parse(stage.dataset.items), cid = stage.dataset.cid;
let idx = 0; const answers = [];
document.getElementById("start").onclick = show;

function show() {
  const d = items[idx];
  stage.replaceChildren(el("div", { className: "step" },
    progress(idx, items.length),
    el("span", { className: "chip", textContent: `${idx + 1} of ${items.length}` }),
    el("blockquote", { textContent: d.text }), speakBtn(d.text),
    el("h2", { textContent: "Scam or fine?" }),
    el("div", { className: "opts" }, option("Scam", 0, () => next(true)), option("Looks fine", 1, () => next(false)))));
}
async function next(v) {
  answers.push(v);
  if (++idx < items.length) return show();
  const r = await (await fetch(`/api/challenge/${cid}/submit`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }),
  })).json();
  const link = location.origin + r.card_url;
  stage.replaceChildren(el("div", { className: "step" },
    el("h2", { textContent: `I'm ${r.pct}% Baitproof 🛡️ (${r.right} of ${r.total})` }),
    ...r.review.map((x, i) => el("p", { className: "feedback " + (x.correct ? "correct" : "incorrect"),
      textContent: `${i + 1}. ${x.correct ? "✅" : "💡"} ${x.is_scam ? "Scam" : "Fine"}. ${x.tell}` })),
    familyBox(r.pct, link),
    el("a", { className: "big", href: link, textContent: "Open my result card" })));
}
