const stage = document.getElementById("stage");
let items = [], idx = 0, session = "", startScore = null, results = [];

document.getElementById("start").onclick = async () => {
  const r = await (await fetch("/api/train/start", { method: "POST" })).json();
  items = r.items; session = r.session; idx = 0; results = []; startScore = r.map.score;
  items.length ? show() : stage.replaceChildren(el("p", {}, "Nothing to practise yet."));
};

function show() {
  const d = items[idx];
  const box = el("div", { className: "opts" });
  if (d.options.length) {
    d.options.forEach((o, i) => box.append(option(o, i, (e) => { e.currentTarget.classList.add("picked"); answer(d, { choice: i }); })));
  } else {
    const ta = el("textarea", { rows: 3, ariaLabel: "Your reply" });
    box.append(ta, el("button", { className: "big", textContent: "Check my answer", onclick: () => answer(d, { text: ta.value }) }));
  }
  stage.replaceChildren(el("div", { className: "step" },
    progress(idx, items.length),
    el("span", { className: "chip", textContent: `${idx + 1} of ${items.length} · ${d.reason}` }),
    el("blockquote", { textContent: d.scenario }), speakBtn(d.scenario),
    el("h2", { textContent: d.question }), box));
}

async function answer(d, body) {
  const step = stage.querySelector(".step");
  step.querySelectorAll("button").forEach((b) => (b.disabled = true));
  const r = await (await fetch("/api/train/answer", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session, item_id: d.id, ...body }),
  })).json();
  if (r.map) renderMap(r.map);
  results.push(r.result);
  if (r.correct_index != null) step.querySelectorAll(".opt").forEach((b, i) => { if (i === r.correct_index) b.classList.add("right"); });
  const last = idx === items.length - 1;
  const mark = r.result === "correct" ? "✅" : r.result === "partial" ? "🟡" : "💡";
  step.append(
    el("p", { className: "feedback " + r.result, textContent: `${mark} ${r.note}` }),
    el("button", { className: "big", textContent: last ? "Finish" : "Next →", onclick: () => (last ? finish(r.map.score) : (idx++, show())) })
  );
}

function finish(score) {
  const good = results.filter((x) => x === "correct").length;
  const diff = score - startScore;
  stage.replaceChildren(el("div", { className: "step" },
    el("h2", { textContent: `You got ${good} of ${results.length} right.` }),
    el("p", { className: "lead", textContent: `Baitproof score: ${score}${diff ? ` (${diff > 0 ? "+" : ""}${diff})` : ""}. See your updated map below.` }),
    el("button", { className: "big", textContent: "Practise again", onclick: () => location.reload() })));
}
