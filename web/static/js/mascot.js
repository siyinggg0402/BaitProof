// Finn, the Baitproof fish: a little scam-spotting friend. He swims in when you first arrive, floats about, watches your pointer, can be picked up and moved
// anywhere (mouse, finger or keyboard), reacts to what you check or answer, and tells a tip when you tap him. A switch in the footer sends him away.
// He is decoration with a voice: nothing on the page depends on him, he never takes focus, and "reduce motion" keeps him still.
(() => {
  if (document.body && document.body.dataset.game) return; // a game page (the 3D road) draws its own scene: no second WebGL canvas, no flying fish over the play area
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const KEY = "bpm";
  const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; } };
  const save = (patch) => { try { localStorage.setItem(KEY, JSON.stringify({ ...read(), ...patch })); } catch (e) { /* private mode: he just forgets */ } };
  const prefs = read();
  const toggle = document.getElementById("mascot-toggle");
  if (toggle) {
    toggle.hidden = false; toggle.setAttribute("aria-pressed", String(!prefs.hidden));
    toggle.addEventListener("click", () => { save({ hidden: !prefs.hidden }); location.reload(); });
  }
  if (prefs.hidden || !document.body) return;

  // ---- the drawing (viewBox 170 x 124, facing right). Only plain attributes and classes: the stylesheet colours and animates it.
  const SVG = `<svg class="finn" viewBox="0 0 170 124" focusable="false" aria-hidden="true"><g class="f-all">
    <g class="f-bubs"><circle class="f-bub" cx="158" cy="74" r="4"/><circle class="f-bub" cx="164" cy="64" r="2.6"/><circle class="f-bub" cx="155" cy="60" r="3"/></g>
    <g class="f-tail"><path class="f-fin" d="M52 64 C36 48 16 46 5 28 C25 24 45 36 60 54 Z"/><path class="f-fin" d="M52 64 C36 80 16 82 5 100 C25 104 45 92 60 74 Z"/></g>
    <path class="f-fin" d="M72 30 C78 8 104 4 120 24 C104 22 88 24 72 30 Z"/>
    <path class="f-body" d="M42 64 C42 34 70 20 98 22 C130 24 152 42 152 66 C152 90 128 108 98 108 C66 108 42 92 42 64 Z"/>
    <ellipse class="f-belly" cx="84" cy="93" rx="27" ry="9.5" opacity=".92"/>
    <g class="f-pec"><path class="f-fin" d="M92 74 C80 72 72 82 76 94 C86 93 95 86 96 76 Z"/></g>
    <g transform="translate(70 62)"><path class="f-badge" d="M0 -11 L11 -7 V3 C11 10 5 15 0 17 C-5 15 -11 10 -11 3 V-7 Z"/><path class="f-check" d="M-5 3 L-1.5 6.5 L5.5 -2.5"/></g>
    <circle class="f-blush" cx="103" cy="75" r="7"/><circle class="f-blush" cx="142" cy="75" r="7"/>
    <g class="f-eyeset off-happy">
      <circle class="f-white" cx="106" cy="52" r="12"/><g class="f-look"><g class="f-pupil"><circle class="f-ink" cx="108" cy="53" r="6.8"/><circle class="f-white" cx="110.6" cy="50" r="2.4"/></g></g>
      <circle class="f-white" cx="132" cy="52" r="13"/><g class="f-look"><g class="f-pupil"><circle class="f-ink" cx="134" cy="53" r="7.4"/><circle class="f-white" cx="136.7" cy="49.6" r="2.6"/></g></g>
    </g>
    <g class="on-happy"><path class="f-line" d="M95 55 Q106 40 117 55"/><path class="f-line" d="M120 55 Q132 39 145 55"/></g>
    <path class="f-line on-idle" d="M113 72 Q119 79 125 72"/>
    <g class="on-happy"><path class="f-ink" d="M108 69 Q119 91 130 69 Z"/><path d="M113 79 Q119 74 125 79 Q119 87 113 79 Z" fill="#F58BB5"/></g>
    <g class="on-alert"><ellipse class="f-ink" cx="119" cy="77" rx="5" ry="6.5"/><path class="f-line" d="M93 36 L113 42"/><path class="f-line" d="M146 36 L126 42"/>
      <g class="f-mark"><rect x="115" y="-16" width="9" height="19" rx="4.5" fill="#EF5F6B"/><circle cx="119.5" cy="11" r="4.8" fill="#EF5F6B"/></g></g>
    <g class="on-think"><path class="f-line" d="M112 77 H126"/><path class="f-line" d="M95 39 Q106 33 117 39"/>
      <g><circle class="f-lens" cx="146" cy="88" r="14"/><path class="f-handle" d="M156 98 L167 110"/></g></g>
    <g class="on-grab"><ellipse class="f-ink" cx="119" cy="77" rx="4.6" ry="5.8"/></g>
    <g class="on-care"><path class="f-line" d="M113 79 Q119 72 125 79"/><path class="f-line" d="M95 41 L116 37"/><path class="f-line" d="M145 41 L124 37"/>
      <path d="M119 12 C112 4 100 10 108 20 L119 30 L130 20 C138 10 126 4 119 12 Z" fill="#F58BB5"/></g>
    <g class="f-sparks on-happy"><g transform="translate(88 14)"><path class="f-spark" d="M0 -8 Q1 -1 8 0 Q1 1 0 8 Q-1 1 -8 0 Q-1 -1 0 -8 Z"/></g><g transform="translate(158 24)"><path class="f-spark" d="M0 -7 Q1 -1 7 0 Q1 1 0 7 Q-1 1 -7 0 Q-1 -1 0 -7 Z"/></g><g transform="translate(160 104)"><path class="f-spark" d="M0 -6 Q1 -1 6 0 Q1 1 0 6 Q-1 1 -6 0 Q-1 -1 0 -6 Z"/></g></g>
  </g></svg>`;

  const root = document.createElement("div");
  root.className = "finn-root m-idle";
  root.setAttribute("role", "button"); root.tabIndex = 0;
  root.setAttribute("aria-label", t("Finn the fish, your scam-spotting helper. Press Enter for a tip, and use the arrow keys to move him."));
  const body = document.createElement("div"); body.className = "finn-body"; body.innerHTML = SVG; root.append(body);
  const bubble = document.createElement("div"); bubble.className = "finn-bubble"; bubble.setAttribute("aria-hidden", "true");
  const live = document.createElement("div"); live.className = "sr-only"; live.setAttribute("role", "status"); live.setAttribute("aria-live", "polite");
  document.body.append(root, bubble, live);
  const pupils = [...root.querySelectorAll(".f-look")];

  // ---- where he is
  let W = 128, H = 93, p = { x: 0, y: 0 }, dir = 1, rot = 0, anim = 0, dragging = false, say_t = 0, mood_t = 0, wander_t = 0;
  const small = () => matchMedia("(max-width: 560px)").matches;
  function measure() {
    W = small() ? 96 : 128; H = Math.round(W * 124 / 170);
    root.style.setProperty("--fw", W + "px"); root.style.setProperty("--fh", H + "px");
  }
  const bounds = () => ({ x0: 6, x1: Math.max(6, innerWidth - W - 6), y0: 6, y1: Math.max(6, innerHeight - H - (small() ? 78 : 6)) }); // above the phone tab bar
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const keep = (q) => { const b = bounds(); return { x: clamp(q.x, b.x0, b.x1), y: clamp(q.y, b.y0, b.y1) }; };
  const home = () => { const b = bounds(); return { x: b.x1 - 20, y: b.y1 - 24 }; };
  const centre = () => ({ x: p.x + W / 2, y: p.y + H / 2 });
  function paint() {
    root.style.transform = "translate3d(" + p.x.toFixed(1) + "px," + p.y.toFixed(1) + "px,0)";
    body.style.transform = "rotate(" + rot.toFixed(1) + "deg) scaleX(" + dir + ")";
    if (bubble.classList.contains("on")) place();
  }
  const remember = () => { const b = bounds(); save({ fx: b.x1 > b.x0 ? (p.x - b.x0) / (b.x1 - b.x0) : 1, fy: b.y1 > b.y0 ? (p.y - b.y0) / (b.y1 - b.y0) : 1 }); };
  const restored = () => { const b = bounds(); const r = read(); return typeof r.fx === "number" ? { x: b.x0 + r.fx * (b.x1 - b.x0), y: b.y0 + r.fy * (b.y1 - b.y0) } : home(); };
  function face(dx, dy) { // turn toward where he is going, and tilt his nose a little with the climb
    if (Math.abs(dx) > 0.35) dir = dx > 0 ? 1 : -1;
    const want = clamp(dir * Math.atan2(dy, Math.max(Math.abs(dx), 0.5)) * 57.3 * 0.5, -22, 22);
    rot += (want - rot) * 0.15;
  }

  // ---- moods and speech
  function mood(m, ms) {
    root.className = root.className.replace(/\bm-\w+/g, "").trim() + " m-" + m;
    clearTimeout(mood_t);
    if (ms) mood_t = setTimeout(() => mood("idle"), ms);
    look();
  }
  function place() {
    const c = centre(), bw = bubble.offsetWidth, bh = bubble.offsetHeight, below = p.y < bh + 24;
    const left = clamp(c.x - bw * (c.x > innerWidth / 2 ? 0.78 : 0.22), 8, innerWidth - bw - 8);
    const top = below ? p.y + H + 14 : p.y - bh - 14;
    bubble.classList.toggle("below", below);
    bubble.style.setProperty("--tail", clamp(c.x - left - 7, 14, bw - 28) + "px");
    bubble.style.transform = "translate3d(" + left.toFixed(1) + "px," + top.toFixed(1) + "px,0)";
  }
  function say(text, ms = 7000) {
    bubble.textContent = text; live.textContent = ""; setTimeout(() => { live.textContent = text; }, 50);
    bubble.classList.add("on"); place();
    clearTimeout(say_t); say_t = setTimeout(() => bubble.classList.remove("on"), ms);
  }
  const shush = () => { clearTimeout(say_t); bubble.classList.remove("on"); };
  const TIPS = [
    t("Real banks never ask for your PIN or a code by message."),
    t("Gift cards are for gifts. If someone asks you to pay with them, it's a scam."),
    t("A rush is a red flag. Scammers hate it when you stop to think."),
    t("Got a link? Don't tap it. Go to the website yourself."),
    t("Hi grandma, it's me. Before you send money, call them on a number you know."),
    t("Never share a code you get by message, not even with someone who says they work for the company."),
    t("That's phishing: a scammer fishing for your details. This fish never bites!"),
    t("Short links hide where they lead. I can peek without clicking."),
    t("A prize you never entered for? You can't win a game you didn't play."),
    t("Check a company yourself: use the number on your card or the official app."),
    t("Fooled by a scam? You're not silly. They trick smart people every day."),
    t("Tell your family about the tricks you spot. Try the family challenge!"),
    t("Paste any message and I'll show you the giveaway."),
    t("Agree a family safe word. If someone asks for money in a hurry, ask for it. No word, no money."),
    t("On Android, install Baitproof, then use Share in WhatsApp to send me a message to check."),
  ];
  let tipAt = Math.floor(Math.random() * TIPS.length);
  const tip = () => { tipAt = (tipAt + 1) % TIPS.length; mood("happy", 4500); say(TIPS[tipAt]); };

  // ---- his eyes follow your pointer
  let ptr = null, lookQueued = 0;
  function look() {
    lookQueued = 0;
    let ox = 0, oy = 0;
    if (root.classList.contains("m-think")) { ox = 3.4 * dir; oy = 2.4; } // at his magnifying glass
    else if (ptr && !root.classList.contains("m-grab")) {
      const c = centre(), dx = ptr.x - c.x, dy = ptr.y - c.y, d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 260);
      ox = (dx / d) * 4 * k * dir; oy = (dy / d) * 3.6 * k;
    }
    for (const el of pupils) el.setAttribute("transform", "translate(" + ox.toFixed(2) + " " + oy.toFixed(2) + ")");
  }
  addEventListener("pointermove", (e) => { if (e.pointerType === "touch") return; ptr = { x: e.clientX, y: e.clientY }; if (!lookQueued) lookQueued = requestAnimationFrame(look); }, { passive: true });

  // ---- swimming
  const stop = () => { if (anim) cancelAnimationFrame(anim); anim = 0; root.classList.remove("moving"); };
  const sine = (u) => 0.5 - 0.5 * Math.cos(Math.PI * u), cubic = (u) => 1 - Math.pow(1 - u, 3);
  function fly(points, ms, ease, done) { // along a smooth curve through the points
    stop(); root.classList.add("moving");
    const P = [points[0], ...points, points[points.length - 1]], seg = points.length - 1, t0 = performance.now();
    let last = { x: p.x, y: p.y }, splashed = 0;
    const at = (u) => {
      const f = Math.min(seg - 1e-6, u * seg), i = Math.floor(f), s = f - i, a = P[i], b = P[i + 1], c = P[i + 2], d = P[i + 3];
      const cr = (k) => 0.5 * (2 * b[k] + (-a[k] + c[k]) * s + (2 * a[k] - 5 * b[k] + 4 * c[k] - d[k]) * s * s + (-a[k] + 3 * b[k] - 3 * c[k] + d[k]) * s * s * s);
      return { x: cr("x"), y: cr("y") };
    };
    const step = (now) => {
      const u = clamp((now - t0) / ms, 0, 1), q = at(clamp(ease(u), 0, 1)); // a frame's timestamp can come just before our start time
      face(q.x - last.x, q.y - last.y); last = p = q; paint(); look();
      if (window.bpSplash && now - splashed > 420) { splashed = now; const c = centre(); window.bpSplash(c.x, c.y, 0.3); } // he stirs the water as he goes
      if (u < 1) anim = requestAnimationFrame(step); else { anim = 0; root.classList.remove("moving"); rot = 0; paint(); if (done) done(); }
    };
    anim = requestAnimationFrame(step);
  }
  function glide(vx, vy) { // let go while moving: slide to a stop, bouncing softly off the edges
    stop(); root.classList.add("moving");
    let last = performance.now();
    const step = (now) => {
      const dt = Math.min(48, now - last); last = now; const b = bounds();
      p = { x: p.x + vx * dt, y: p.y + vy * dt };
      if (p.x < b.x0 || p.x > b.x1) { vx *= -0.45; p.x = clamp(p.x, b.x0, b.x1); }
      if (p.y < b.y0 || p.y > b.y1) { vy *= -0.45; p.y = clamp(p.y, b.y0, b.y1); }
      const f = Math.pow(0.93, dt / 16); vx *= f; vy *= f;
      face(vx * 16, vy * 16); paint(); look();
      if (Math.hypot(vx, vy) > 0.025) anim = requestAnimationFrame(step); else { anim = 0; root.classList.remove("moving"); rot = 0; paint(); remember(); }
    };
    anim = requestAnimationFrame(step);
  }
  const wander = () => {
    clearTimeout(wander_t);
    wander_t = setTimeout(() => {
      const a = document.activeElement, typing = a && /^(TEXTAREA|INPUT|SELECT)$/.test(a.tagName);
      if (!reduce && !dragging && !document.hidden && !typing && !bubble.classList.contains("on") && !root.matches(":hover")) {
        const to = keep({ x: p.x + (Math.random() - 0.5) * 300, y: p.y + (Math.random() - 0.5) * 190 });
        fly([{ ...p }, { x: (p.x + to.x) / 2 + (Math.random() - 0.5) * 60, y: (p.y + to.y) / 2 - 30 }, to], 2200, sine, remember);
      }
      wander();
    }, 16000 + Math.random() * 14000);
  };

  // ---- picking him up
  let grab = null, samples = [];
  root.addEventListener("pointerdown", (e) => {
    if (e.button > 0) return;
    stop(); dragging = true; grab = { dx: e.clientX - p.x, dy: e.clientY - p.y, x: e.clientX, y: e.clientY, t: performance.now(), moved: false };
    samples = [{ x: p.x, y: p.y, t: grab.t }];
    root.setPointerCapture(e.pointerId); root.classList.add("grabbed"); mood("grab"); shush();
  });
  let splashT = 0;
  root.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    if (Math.hypot(e.clientX - grab.x, e.clientY - grab.y) > 5) grab.moved = true;
    const q = keep({ x: e.clientX - grab.dx, y: e.clientY - grab.dy });
    face(q.x - p.x, q.y - p.y); p = q; paint(); look();
    const now = performance.now(); samples.push({ x: p.x, y: p.y, t: now }); if (samples.length > 6) samples.shift();
    if (window.bpSplash && now - splashT > 150 && grab.moved) { splashT = now; const c = centre(); window.bpSplash(c.x, c.y, 0.28); }
  });
  const drop = (e) => {
    if (!dragging) return;
    dragging = false; root.classList.remove("grabbed");
    try { root.releasePointerCapture(e.pointerId); } catch (err) { /* already released */ }
    mood("idle");
    if (!grab.moved && performance.now() - grab.t < 500) { rot = 0; paint(); root.classList.add("hop"); setTimeout(() => root.classList.remove("hop"), 600); tip(); remember(); return; }
    const a = samples[0], b = samples[samples.length - 1], dt = Math.max(1, b.t - a.t);
    let vx = (b.x - a.x) / dt, vy = (b.y - a.y) / dt; const sp = Math.hypot(vx, vy);
    if (sp > 2.4) { vx *= 2.4 / sp; vy *= 2.4 / sp; }
    if (!reduce && performance.now() - b.t < 90 && sp > 0.12) glide(vx, vy); else { rot = 0; paint(); remember(); }
  };
  root.addEventListener("pointerup", drop); root.addEventListener("pointercancel", drop);
  root.addEventListener("keydown", (e) => {
    const s = e.shiftKey ? 80 : 28, mv = { ArrowLeft: [-s, 0], ArrowRight: [s, 0], ArrowUp: [0, -s], ArrowDown: [0, s] }[e.key];
    if (mv) { e.preventDefault(); stop(); const q = keep({ x: p.x + mv[0], y: p.y + mv[1] }); face(q.x - p.x, q.y - p.y); p = q; rot = 0; paint(); remember(); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tip(); }
    else if (e.key === "Escape") shush();
    else if (e.key === "Home") { e.preventDefault(); stop(); p = home(); rot = 0; paint(); remember(); }
  });
  addEventListener("resize", () => { measure(); p = keep(p); paint(); remember(); }, { passive: true });

  // ---- what he notices on the page
  const SAYS = {
    scam: ["alert", t("Don't tap that link! I spotted the giveaway.")],
    likely_scam: ["alert", t("Hmm, this looks fishy. Don't act on it yet.")],
    safe: ["happy", t("Looks okay to me! But if it asks for money, check with the real company first.")],
    unsure: ["think", t("I'm not sure about this one. Check with someone you trust.")],
    victim_support: ["care", t("It's not your fault. Please call your bank first. I'm right here with you.")],
  };
  let checking = false, queued = 0;
  function notice() {
    queued = 0;
    const live_box = document.getElementById("live");
    if (live_box && !live_box.hidden) { if (!checking) { checking = true; mood("think", 60000); say(t("Let me take a closer look…"), 9000); } }
    else checking = false;
    const r = document.getElementById("result");
    if (r && !r.dataset.finn) {
      r.dataset.finn = "1"; checking = false;
      const m = /\bv-([a-z_]+)/.exec(r.className), s = m && SAYS[m[1]];
      if (s) { mood(s[0], 9000); say(s[1], 9000); }
    }
    for (const b of document.querySelectorAll(".banner-r:not([data-finn])")) { // in the games: right, nearly, or not quite
      b.dataset.finn = "1";
      if (b.classList.contains("correct")) { mood("happy", 3500); say(t("Nice catch! You spotted the trick."), 4500); }
      else if (b.classList.contains("partial")) { mood("think", 3500); say(t("So close! Look again at the giveaway."), 4500); }
      else if (b.classList.contains("wrong")) { mood("care", 3500); say(t("Good try! Now you know the tell."), 4500); }
    }
  }
  new MutationObserver(() => { if (!queued) queued = requestAnimationFrame(notice); }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });

  // ---- arriving
  measure();
  const first = !prefs.seen;
  save({ seen: true });
  p = restored(); rot = 0;
  if (reduce) { paint(); if (first) setTimeout(() => say(t("Hi! I'm Finn. I sniff out scam messages. Paste one and I'll show you the giveaway. You can pick me up and move me, too!"), 9000), 600); }
  else if (first) { // a proper entrance: in from the left, a few swoops across the page, then settle
    const h = home(), w = innerWidth, v = innerHeight;
    p = { x: -W - 30, y: v * 0.3 };
    paint(); root.classList.add("popin");
    fly([{ ...p }, keep({ x: w * 0.2, y: v * 0.12 }), keep({ x: w * 0.44, y: v * 0.5 }), keep({ x: w * 0.66, y: v * 0.16 }), keep({ x: w * 0.5, y: v * 0.62 }), h], 7200, sine, () => {
      mood("happy", 5000); say(t("Hi! I'm Finn. I sniff out scam messages. Paste one and I'll show you the giveaway. You can pick me up and move me, too!"), 10000); remember();
    });
  } else { // coming back: a quick swim in from the side
    const to = p; p = { x: innerWidth + 20, y: to.y - 60 };
    paint(); root.classList.add("popin");
    fly([{ ...p }, { x: (p.x + to.x) / 2, y: to.y - 30 }, to], 1500, cubic, remember);
  }
  paint(); look(); wander();
  queued = requestAnimationFrame(notice); // a result that came with the page (no script, or a reload)
  window.bpFinn = { mood, say, tip, hide: shush }; // for tests and for other scripts that want him to react
})();
