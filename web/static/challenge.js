const stage = document.getElementById("stage");
const items = JSON.parse(stage.dataset.items), cid = stage.dataset.cid;
let idx = 0; const answers = [];
document.getElementById("start").onclick = show;

function show() {
  const d = items[idx];
  stage.replaceChildren(
    el("p", { className: "chip", textContent: `${idx + 1} of ${items.length}` }),
    el("blockquote", { textContent: d.text }), speakBtn(d.text),
    el("h2", { textContent: "Scam or fine?" }),
    el("div", { className: "opts" },
      el("button", { className: "opt", textContent: "🚨 Scam", onclick: () => next(true) }),
      el("button", { className: "opt", textContent: "✅ Looks fine", onclick: () => next(false) }))
  );
}
async function next(v) {
  answers.push(v);
  if (++idx < items.length) return show();
  const r = await (await fetch(`/api/challenge/${cid}/submit`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }),
  })).json();
  const link = location.origin + r.card_url;
  stage.replaceChildren(
    el("h2", { textContent: `I'm ${r.pct}% Baitproof 🛡️ (${r.right} of ${r.total})` }),
    ...r.review.map((x, i) => el("p", { className: "feedback " + (x.correct ? "correct" : "incorrect"),
      textContent: `${i + 1}. ${x.correct ? "✅" : "💡"} ${x.is_scam ? "Scam" : "Fine"}. ${x.tell}` })),
    el("p", {}, "Send this to someone you want to protect:"),
    el("input", { value: link, readOnly: true, size: 40, ariaLabel: "Share link", onfocus: (e) => e.target.select() }),
    el("p", {}, el("a", { className: "big", href: link, textContent: "Open my result card" }))
  );
}
