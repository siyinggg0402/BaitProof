const stage = document.getElementById("stage");
const items = JSON.parse(stage.dataset.items), cid = stage.dataset.cid;
let idx = 0; const answers = [];
document.getElementById("start").onclick = show;

function show() {
  const d = items[idx];
  stage.replaceChildren(el("div", { className: "step" },
    progress(idx, items.length),
    el("span", { className: "chip", textContent: t("{i} of {n}", { i: idx + 1, n: items.length }) }),
    el("blockquote", { textContent: d.text }), speakBtn(d.text),
    el("h2", { textContent: t("Scam or fine?") }),
    el("div", { className: "opts" }, option(t("Scam"), 0, () => next(true)), option(t("Looks fine"), 1, () => next(false)))));
}
async function next(v) {
  answers.push(v);
  if (++idx < items.length) return show();
  const r = await (await fetch(`/api/challenge/${cid}/submit`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }),
  })).json();
  const link = location.origin + r.card_url;
  stage.replaceChildren(el("div", { className: "step" },
    el("h2", { textContent: t("I'm {pct}% Baitproof ({right} of {total})", { pct: r.pct, right: r.right, total: r.total }) }),
    ...r.review.map((x, i) => el("p", { className: "feedback " + (x.correct ? "correct" : "incorrect") },
      `${i + 1}. `, icon(x.correct ? "check-circle" : "bulb"), ` ${x.is_scam ? t("Scam. {tell}", { tell: x.tell }) : t("Fine. {tell}", { tell: x.tell })}`)),
    familyBox(r.pct, link),
    el("a", { className: "big", href: link, textContent: t("Open my result card") })));
}
