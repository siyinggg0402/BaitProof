// Link Hunt: four links, one fake. The server makes the questions, keeps the answers and does the scoring; this file shows them.
const $ = (id) => document.getElementById(id);
const S = { hunt: "", q: null, lives: 3, score: 0, combo: 0, busy: false, answered: false };
const show = (id) => { for (const x of ["lh-intro", "lh-play", "lh-end", "lh-lost"]) $(x).hidden = x !== id; };

async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) throw new Error("http " + r.status);
  return r.json();
}
function paint() {
  $("lh-hearts").textContent = "❤️".repeat(Math.max(0, S.lives)) + "🖤".repeat(Math.max(0, 3 - S.lives));
  $("lh-hearts").setAttribute("aria-label", t("{n} lives left", { n: S.lives }));
  $("lh-score").textContent = t("{n} points", { n: S.score });
  $("lh-combo").hidden = S.combo < 2; $("lh-combo").textContent = t("Combo x{n}", { n: S.combo });
}
function ask(q) {
  S.q = q; S.answered = false;
  $("lh-feedback").hidden = true;
  $("lh-opts").replaceChildren(...q.options.map((o, i) => {
    const b = el("button", { type: "button", className: "lh-opt" }, el("small", { textContent: o.brand }), el("code", { textContent: o.host }), el("kbd", { textContent: String(i + 1) }));
    b.setAttribute("aria-label", `${o.brand}: ${o.host}`); b.dataset.i = String(i);
    b.addEventListener("click", () => pick(i));
    return b;
  }));
  paint();
}
async function begin() {
  $("lh-start").disabled = true;
  try {
    const r = await api("/api/link/start");
    S.hunt = r.hunt; S.lives = r.lives; S.score = 0; S.combo = 0;
    show("lh-play"); ask(r.question);
  } catch (_) { show("lh-lost"); } finally { $("lh-start").disabled = false; }
}
async function pick(i) {
  if (S.busy || S.answered || !S.q) return;
  S.busy = true; S.answered = true;
  try {
    const r = await api("/api/link/answer", { hunt: S.hunt, question: S.q.id, choice: i });
    S.lives = r.lives; S.score = r.score; S.combo = r.combo; S.next = r.next; S.over = r.over;
    const btns = [...$("lh-opts").children];
    btns.forEach((b, k) => { b.disabled = true; if (k === r.fake) b.classList.add("fake"); if (k === i && !r.correct) b.classList.add("wrong"); });
    btns[r.fake].append(el("span", { className: "flag", textContent: "🚩 " + t("fake") }));
    $("lh-verdict").textContent = r.correct ? "✅ " + t("Yes, that one is fake!") : "❌ " + t("Not that one. The fake was marked with a flag.");
    $("lh-verdict").className = "lh-verdict " + (r.correct ? "good" : "bad");
    $("lh-tell").textContent = r.tell;
    $("lh-next").textContent = r.over ? t("See my result") : t("Next link");
    $("lh-feedback").hidden = false; $("lh-next").focus(); paint();
  } catch (_) { show("lh-lost"); } finally { S.busy = false; }
}
async function done() {
  try {
    const s = await api("/api/link/finish", { hunt: S.hunt });
    $("lh-final").textContent = t("{n} points", { n: s.score });
    $("lh-newbest").hidden = !s.new_best;
    $("lh-stats").replaceChildren(...[t("{n} right", { n: s.correct }), t("Best combo x{n}", { n: s.best_combo }), t("+{n} XP", { n: s.xp_gained })].map((x) => el("li", { textContent: x })));
    $("lh-badges").replaceChildren(...s.badges_new.map((b) => el("span", { className: "chip", textContent: "🏅 " + b.title })));
    $("lh-board").hidden = !s.board.length;
    $("lh-board").replaceChildren(...s.board.map((r) => {
      const li = el("li", { className: (r.you ? "you" : "") + (r.runs ? "" : " idle") });
      li.append(el("span", { className: "rank", textContent: r.rank === 1 ? "🥇" : r.rank === 2 ? "🥈" : r.rank === 3 ? "🥉" : r.rank ? String(r.rank) : "–" }),
        el("span", { className: "who", textContent: `${r.avatar} ${r.nickname}` }), el("span", { className: "far", textContent: r.runs ? t("{n} points", { n: r.best }) : "–" }));
      return li;
    }));
    $("lh-login").hidden = s.account;
    show("lh-end"); $("lh-again").focus();
  } catch (_) { show("lh-lost"); }
}
$("lh-start").addEventListener("click", begin);
$("lh-again").addEventListener("click", begin);
$("lh-retry").addEventListener("click", () => show("lh-intro"));
$("lh-next").addEventListener("click", () => { if (S.over) done(); else ask(S.next); });
addEventListener("keydown", (e) => {
  if ($("lh-play").hidden) return;
  if (["1", "2", "3", "4"].includes(e.key) && !S.answered) { pick(+e.key - 1); e.preventDefault(); }
  else if ((e.key === "Enter" || e.key === " ") && S.answered && document.activeElement !== $("lh-next")) { $("lh-next").click(); e.preventDefault(); }
});
