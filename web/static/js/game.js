// Baitproof game: hub -> play -> reveal -> results. All answers are checked on the server; this file only draws.
(() => {
  const root = document.getElementById("game");
  const store = { get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (_) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} } };
  let sound = store.get("bp-sound", "0") === "1", timed = store.get("bp-timed", "0") === "1";
  let S = null, R = null, idx = 0, phase = "hub", t0 = 0, timer = null, picked = new Set(), lastMode = null, lastTrick = "";

  const api = async (url, body) => {
    const r = await fetch(url, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || t("Something went wrong. Please try again."));
    return j;
  };

  // ---- tiny sound effects (WebAudio, off by default)
  let ac;
  function beep(f, ms = 120, type = "sine") {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!sound || !AC) return;
    ac = ac || new AC();
    const o = ac.createOscillator(), g = ac.createGain();
    o.type = type; o.frequency.value = f; g.gain.value = 0.05; o.connect(g); g.connect(ac.destination); o.start(); o.stop(ac.currentTime + ms / 1000);
  }
  const sfx = { good() { beep(660, 90); setTimeout(() => beep(880, 140), 90); }, ok() { beep(520, 160); }, bad() { beep(240, 220, "triangle"); },
    level() { [523, 659, 784, 1046].forEach((f, i) => setTimeout(() => beep(f, 170), i * 120)); } };

  const show = (...nodes) => root.replaceChildren(...nodes);
  const chip = (text, cls = "") => el("span", { className: "chip " + cls, textContent: text });
  const bars = (n, lvl) => { const b = el("span", { className: "bars" }); for (let i = 0; i < 5; i++) b.append(el("i", { className: (i < n ? "on " : "") + lvl })); return b; };

  function confetti() {
    const c = el("div", { className: "confetti", ariaHidden: "true" });
    for (let i = 0; i < 18; i++) c.append(el("i"));
    document.body.append(c);
    setTimeout(() => c.remove(), 2600);
  }
  function floatXp(n, host) {
    if (!n) return;
    const f = el("span", { className: "xp-float", textContent: t("+{n} XP", { n }) });
    host.append(f);
    f.addEventListener("animationend", () => f.remove());
  }

  // ------------------------------------------------------------------ hub
  async function hub() {
    phase = "hub"; clearInterval(timer);
    S = await api("/api/game/state");
    const lvl = el("section", { className: "card hud-card rise" },
      el("div", { className: "hud-top" },
        el("div", { className: "avatar", ariaHidden: "true", textContent: "🛡️" }),
        el("div", { className: "hud-id" }, el("h1", { textContent: t("Level {n} · {title}", { n: S.level, title: S.title }) }),
          el("progress", { className: "xpbar", max: S.xp_for_level, value: S.xp_into_level, ariaLabel: t("Progress to the next level") }),
          el("p", { className: "muted", textContent: t("{a} / {b} XP to level {n}", { a: S.xp_into_level, b: S.xp_for_level, n: S.level + 1 }) }))),
      el("div", { className: "hud-stats" }, chip("🔥 " + t("{n}-day streak", { n: S.streak }), S.streak ? "hot" : ""), chip("🛡️ " + t("Baitproof score {n}", { n: S.resilience })), chip("🎮 " + t("{n} rounds", { n: S.rounds }))),
      el("div", { className: "toggles" },
        toggle("🔊 " + t("Sound effects"), sound, (v) => { sound = v; store.set("bp-sound", v ? "1" : "0"); if (v) sfx.ok(); }),
        toggle("⏱️ " + t("Beat the clock (+5 XP for quick answers)"), timed, (v) => { timed = v; store.set("bp-timed", v ? "1" : "0"); })));

    const mode = (emoji, title, desc, onclick, opts = {}) => el("button", { className: "mode-card" + (opts.hot ? " hot" : ""), disabled: !!opts.disabled, onclick },
      el("span", { className: "mode-emoji", textContent: emoji }), el("span", { className: "mode-title", textContent: title }),
      el("span", { className: "mode-desc", textContent: desc }), opts.tag ? el("span", { className: "mode-tag", textContent: opts.tag }) : "");
    const modes = el("section", { className: "mode-grid rise d1", ariaLabel: t("Game modes") },
      mode("📥", t("Inbox Rush"), t("8 messages. Scam, fine, or check first? Aimed at the tricks you find hardest."), () => play("rush"), { hot: true, tag: t("Quick play") }),
      mode("📅", t("Daily Challenge"), S.daily_done ? t("Done today ✓. You can replay it for fun.") : t("The same 6 messages for everyone today. +50 XP the first time."), () => play("daily"), { tag: S.daily_done ? t("Completed") : t("+50 XP") }),
      mode("🔍", t("Spot the Tell"), t("Tap the exact words that give a scam away."), () => play("tell")),
      mode("👪", t("Your circle"), S.yours_available ? (S.yours_available > 1 ? t("{n} scams that reached your own family.", { n: S.yours_available }) : t("{n} scam that reached your own family.", { n: S.yours_available })) : t("Scams you check or forward will appear here to practise on."),
        () => play("yours"), { disabled: !S.yours_available }));

    const bossGrid = el("div", { className: "boss-grid" }, ...S.tricks.map((k) => el("button", { className: "tile" + (k.won ? " won" : ""), onclick: () => play("boss", k.id), title: k.blurb },
      el("span", { className: "tile-top" }, el("span", { className: "tile-name", textContent: k.label }), el("span", { className: "tile-trophy", textContent: k.won ? "🏆" : "⚔️", ariaHidden: "true" })),
      bars(k.bars, k.level), el("span", { className: "tile-sub", textContent: k.won ? t("Boss beaten") : t("{n} messages · 3 lives", { n: k.messages }) }))));
    const bosses = el("section", { className: "card rise d2" }, el("h2", { textContent: t("Boss battles") }),
      el("p", { className: "muted", textContent: t("One boss per trick. Beat all of its messages with lives to spare to earn a badge and raise that trick in your resilience map.") }), bossGrid);

    const earned = S.badges.length ? S.badges.map((b) => el("span", { className: "badge-chip", title: b.desc, textContent: "🏅 " + b.title })) : [el("span", { className: "muted", textContent: t("No badges yet. Finish a round to earn your first.") })];
    const badges = el("section", { className: "card rise d3" }, el("h2", { textContent: t("Badges ({n}/{m})", { n: S.badges.length, m: S.badges_total }) }), el("div", { className: "badge-row" }, ...earned));
    show(lvl, modes, bosses, badges);
  }

  function toggle(label, on, cb) {
    const input = el("input", { type: "checkbox", checked: on });
    input.addEventListener("change", () => cb(input.checked));
    return el("label", { className: "switch" }, input, " " + label);
  }

  // ------------------------------------------------------------------ playing
  async function play(mode, trick = "") {
    try {
      lastMode = mode; lastTrick = trick;
      R = await api("/api/game/start", { mode, trick });
      idx = 0; R.combo = 0; R.lives_now = R.lives; R.xp = 0;
      item();
    } catch (e) { alert_(e.message); }
  }
  const alert_ = (msg) => { const n = el("p", { className: "card err", role: "alert", textContent: msg }); root.prepend(n); setTimeout(() => n.remove(), 5000); };

  function hud() {
    const left = el("div", { className: "hud-left" });
    if (R.mode === "boss") left.append(el("span", { className: "hearts", ariaLabel: t("{n} lives left", { n: R.lives_now }), textContent: "♥".repeat(Math.max(0, R.lives_now)) + "♡".repeat(Math.max(0, R.lives - R.lives_now)) }));
    left.append(el("span", { className: "combo" + (R.combo >= 2 ? " hot" : ""), textContent: R.combo >= 2 ? `🔥 ×${R.combo}` : "" }));
    return el("div", { className: "play-hud" }, left,
      el("span", { className: "muted", textContent: (R.mode === "boss" ? t("{trick} boss · ", { trick: R.trick_label }) : "") + `${Math.min(idx + 1, R.total)} / ${R.total}` }),
      el("button", { className: "ghost quit", onclick: hub, textContent: t("Quit") }));
  }

  function bubble(it, highlight) {
    const body = el("div", { className: "msg" });
    if (highlight) {
      const [a, b] = highlight;
      body.append(it.text.slice(0, a), el("mark", { textContent: it.text.slice(a, b) }), it.text.slice(b));
    } else body.textContent = it.text;
    return el("div", { className: "phone" }, el("div", { className: "phone-top" }, el("span", { textContent: t("New message") }), it.yours ? chip(t("From your circle"), "yours") : ""), body);
  }

  function item() {
    phase = "choose"; picked = new Set(); clearInterval(timer);
    if (idx >= R.total) return end();
    const it = R.items[idx];
    const prog = el("progress", { className: "round-prog", max: R.total, value: idx, ariaHidden: "true" });
    const card = el("section", { className: "card play rise" }, prog);
    card.append(bubble(it));
    if (R.mode === "tell") {
      card.append(el("h2", { textContent: t("Tap the words that give this scam away") }));
      const box = el("div", { className: "words", role: "group", ariaLabel: t("Words of the message") });
      it.words.forEach((w, i) => box.append(el("button", { className: "w", type: "button", textContent: w, "aria-pressed": "false",
        onclick: (e) => { picked.has(i) ? picked.delete(i) : picked.add(i); e.currentTarget.classList.toggle("sel"); e.currentTarget.setAttribute("aria-pressed", String(picked.has(i))); } })));
      card.append(box, el("button", { className: "big", textContent: t("Check my answer"), onclick: () => submit(null) }));
    } else {
      card.append(el("h2", { textContent: t("What is this message?") }), el("div", { className: "choices", role: "group", ariaLabel: t("Your answer") },
        choice("scam", "🚨", t("Scam"), "S"), choice("safe", "✅", t("Looks fine"), "F"), choice("unsure", "🤔", t("Check first"), "C")),
        el("p", { className: "muted hint", textContent: t("Keys: S, F and C. “Check first” means you'd phone the sender on a number you already trust.") }));
    }
    if (timed) {
      const bar = el("progress", { className: "clock", max: 12, value: 12, ariaLabel: t("Time left") });
      card.append(bar);
      let left = 12; t0 = Date.now();
      timer = setInterval(() => { left -= 0.25; bar.value = Math.max(0, left); if (left <= 0) clearInterval(timer); }, 250);
    } else t0 = Date.now();
    show(hud(), card);
  }

  function choice(v, emoji, label, key) {
    return el("button", { className: "choice c-" + v, onclick: () => submit(v) }, el("span", { className: "c-emoji", textContent: emoji }), el("span", { textContent: label }), el("kbd", { textContent: key }));
  }

  async function submit(c) {
    if (phase !== "choose") return;
    phase = "wait"; clearInterval(timer);
    const it = R.items[idx];
    document.querySelectorAll(".choice, .w, .big").forEach((b) => (b.disabled = true));
    let res;
    try {
      res = await api("/api/game/answer", { round: R.round, item_id: it.id, choice: c, picked: c === null ? [...picked] : null, fast: timed && (Date.now() - t0) / 1000 <= 7 });
    } catch (e) { phase = "choose"; document.querySelectorAll(".choice, .w, .big").forEach((b) => (b.disabled = false)); return alert_(e.message); }
    R.combo = res.combo; R.lives_now = res.lives; R.xp += res.xp;
    reveal(it, res);
  }

  function reveal(it, res) {
    phase = "reveal";
    const good = res.outcome === "correct", ok = res.outcome === "partial";
    const title = good ? (R.mode === "tell" ? t("🎯 Great eye!") : t("✅ Nice catch!")) : ok ? t("🟡 Careful is good!") : (res.false_alarm ? t("💡 That one was genuine") : t("💡 Here's the tell"));
    const truth = { scam: t("This one is a scam."), safe: t("This one is genuine."), unsure: t("This one is worth checking first: it could be real or fake.") }[res.truth];
    (good ? sfx.good : ok ? sfx.ok : sfx.bad)();
    const banner = el("div", { className: "banner-r " + res.outcome, role: "status" }, el("strong", { textContent: title }), el("span", { textContent: truth }));
    floatXp(res.xp, banner);
    const card = el("section", { className: "card play reveal-card" }, el("progress", { className: "round-prog", max: R.total, value: idx + 1, ariaHidden: "true" }), banner,
      bubble(it, res.highlight), res.tell ? el("div", { className: "panel" }, el("b", { textContent: res.truth === "safe" ? t("Why it's fine") : t("The giveaway") }), res.tell) : "",
      res.tricks.length ? el("div", { className: "chips-row" }, ...res.tricks.map((t) => chip(t))) : "",
      res.action && res.truth !== "safe" ? el("div", { className: "panel" }, el("b", { textContent: t("What to do") }), res.action) : "");
    const last = res.over;
    const next = el("button", { className: "big", textContent: last ? t("See results") : t("Next →"), onclick: () => { idx++; last ? end() : item(); } });
    card.append(next);
    show(hud(), card);
    next.focus();
    if (R.mode === "boss" && res.lives <= 0) banner.append(el("span", { textContent: " " + t("The boss got you this time. You can try again.") }));
  }

  // ------------------------------------------------------------------ results
  async function end() {
    phase = "end";
    let sum;
    try { sum = await api("/api/game/finish", { round: R.round }); } catch (e) { return alert_(e.message); }
    const win = sum.won_boss, lost = sum.defeated;
    const title = win ? "🏆 " + t("{trick} boss beaten!", { trick: sum.trick_label }) : lost ? t("💥 The boss won this time") : sum.perfect ? t("🌟 Flawless round!") : t("🎉 Round complete!");
    const st = sum.state;
    const xpbar = el("progress", { className: "xpbar", max: st.xp_for_level, value: 0, ariaLabel: t("Experience") });
    setTimeout(() => (xpbar.value = st.xp_into_level), 150);
    const stats = el("div", { className: "kpis" },
      kpi(`${sum.correct}/${sum.total}`, t("right")), kpi(sum.best_combo, t("best combo")), kpi(`+${sum.xp_gained}`, t("XP earned")), kpi(sum.resilience, t("Baitproof score")));
    const card = el("section", { className: "card end rise" }, el("h1", { textContent: title }),
      el("p", { className: "lead", textContent: lost ? t("Every slip shows you a tell. Have another go.") : sum.perfect ? t("Not one slip. Your family is lucky to have you.") : t("Nice work. Each round makes the next scam easier to spot.") }), stats);
    if (sum.level_up) { card.append(el("div", { className: "levelup", role: "status", textContent: "⬆️ " + t("Level up! You're now level {n}: {title}", { n: st.level, title: st.title }) })); sfx.level(); confetti(); }
    else if (win || sum.perfect) confetti();
    card.append(el("div", { className: "end-xp" }, el("strong", { textContent: t("Level {n} · {title}", { n: st.level, title: st.title }) }), xpbar, el("span", { className: "muted", textContent: t("{a} / {b} XP", { a: st.xp_into_level, b: st.xp_for_level }) })));
    if (sum.daily_bonus) card.append(el("p", { className: "added", textContent: "📅 " + t("Daily Challenge complete: +50 XP bonus!") }));
    if (sum.badges_new.length) card.append(el("div", { className: "new-badges" }, el("h2", { textContent: t("New badges") }),
      ...sum.badges_new.map((b, i) => el("div", { className: "badge-pop", title: b.desc }, el("span", { textContent: "🏅" }), el("span", {}, el("b", { textContent: b.title }), el("small", { textContent: b.desc }))))));
    card.append(el("div", { className: "end-actions" }, el("button", { className: "big", textContent: lost ? t("Try again") : t("Play again"), onclick: () => play(lastMode, lastTrick) }),
      el("button", { className: "big sec", textContent: t("All games"), onclick: hub }), el("a", { className: "big sec", href: "/train", textContent: t("Practise my weak tricks") })));
    show(card);
  }
  const kpi = (v, label) => el("div", { className: "kpi" }, el("b", { textContent: String(v) }), el("span", { textContent: label }));

  // ------------------------------------------------------------------ keyboard
  document.addEventListener("keydown", (e) => {
    if (e.target.closest && e.target.closest("input, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (phase === "choose" && R && R.mode !== "tell") { if (k === "s") submit("scam"); else if (k === "f") submit("safe"); else if (k === "c") submit("unsure"); }
  });

  // The Train page links straight into a mode (/game#rush, #daily, #tell); the hub still loads first, so Quit lands on it.
  const direct = { "#rush": "rush", "#daily": "daily", "#tell": "tell" }[location.hash];
  hub().then(() => direct && play(direct)).catch(() => show(el("p", { className: "card err", textContent: t("Couldn't load the game. Please refresh.") })));
})();
