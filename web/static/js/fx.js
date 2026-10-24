const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

function animateNumber(el, to, ms = 900) {
  const from = parseInt(el.textContent, 10) || 0;
  if (reduce || from === to) { el.textContent = to; return; }
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
function setRing(score) {
  document.getElementById("ring")?.setAttribute("stroke-dasharray", `${score} 100`);
}

// reveal on scroll
const io = "IntersectionObserver" in window
  ? new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.12 })
  : null;
document.querySelectorAll(".reveal").forEach((n) => (io ? io.observe(n) : n.classList.add("in")));

// score ring fills + counts up on load
const scoreEl = document.getElementById("score");
if (scoreEl) {
  const target = parseInt(scoreEl.textContent, 10) || 0;
  scoreEl.textContent = "0"; setRing(0);
  requestAnimationFrame(() => requestAnimationFrame(() => { setRing(target); animateNumber(scoreEl, target, 1100); }));
}

// hero demo: a decorative, looped example (not live engine output)
const bubble = document.getElementById("demo-bubble");
if (bubble) {
  const tags = document.getElementById("demo-tags"), verdict = document.getElementById("demo-verdict"), label = document.getElementById("demo-label");
  const DEMOS = [
    { text: t("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz"), tags: [t("Rushing you"), t("Fake website address")], v: t("Scam. Don't pay, don't tap the link."), ok: false },
    { text: t("Hi grandma, it's me. I'm in trouble. Please buy four gift cards and send me the numbers. Don't tell Mom."), tags: [t("Playing on your feelings"), t("Gift cards")], v: t("Scam. Call them on a number you know."), ok: false },
    { text: t("Reminder: your appointment is tomorrow at 10:30am. Call the number on your card to reschedule."), tags: [], v: t("Looks fine, but verify first."), ok: true },
  ];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const show = (d) => { bubble.textContent = d.text; bubble.classList.remove("caret"); tags.replaceChildren(...d.tags.map((t) => Object.assign(document.createElement("span"), { textContent: t }))); verdict.textContent = d.v; verdict.classList.toggle("ok", d.ok); verdict.classList.add("show"); };
  if (reduce) show(DEMOS[0]);
  else (async () => {
    for (let i = 0; ; i = (i + 1) % DEMOS.length) {
      const d = DEMOS[i];
      verdict.classList.remove("show"); tags.replaceChildren(); bubble.textContent = ""; bubble.classList.add("caret");
      for (const ch of d.text) { bubble.textContent += ch; await sleep(22); }
      bubble.classList.remove("caret"); await sleep(500);
      for (const t of d.tags) { tags.append(Object.assign(document.createElement("span"), { textContent: t })); await sleep(380); }
      verdict.textContent = d.v; verdict.classList.toggle("ok", d.ok); verdict.classList.add("show");
      await sleep(3200);
    }
  })();
}

// ---- a soft light under the pointer, and a tilt toward it; a ripple where a button is pressed
(() => {
  const LIT = ".card,.mode-card,.tile,.mock,.kpi", TILT = ".mode-card,.tile,.mock", PRESS = ".btn,button.big,a.big,.ghost,.speak,.inbtn,.choice,nav .cta";
  let cur = null, ev = null, queued = 0;
  const rest = (el) => { if (el) { el.style.removeProperty("--rx"); el.style.removeProperty("--ry"); } };
  function apply() {
    queued = 0;
    const e = ev, el = e.target.closest ? e.target.closest(LIT) : null;
    if (el !== cur) { rest(cur); cur = el; }
    if (!el) return;
    const r = el.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    el.style.setProperty("--mx", x + "px"); el.style.setProperty("--my", y + "px");
    if (!reduce && el.matches(TILT) && r.width < 760) { // big panels stay still; small cards lean toward the pointer
      el.style.setProperty("--ry", ((x / r.width - 0.5) * 5).toFixed(2) + "deg");
      el.style.setProperty("--rx", ((0.5 - y / r.height) * 5).toFixed(2) + "deg");
    }
  }
  document.addEventListener("pointermove", (e) => { if (e.pointerType !== "mouse") return; ev = e; if (!queued) queued = requestAnimationFrame(apply); }, { passive: true });
  document.addEventListener("pointerout", (e) => { if (!e.relatedTarget) { rest(cur); cur = null; } }, { passive: true }); // the pointer left the window
  if (reduce) return;
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest ? e.target.closest(PRESS) : null;
    if (!b || b.disabled) return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2, s = document.createElement("span");
    s.className = "rip";
    s.style.width = s.style.height = d + "px"; s.style.left = (e.clientX - r.left - d / 2) + "px"; s.style.top = (e.clientY - r.top - d / 2) + "px";
    b.append(s);
    s.addEventListener("animationend", () => s.remove());
  }, { passive: true });
  // when a verdict arrives, a ripple spreads from it
  const slot = document.getElementById("result-slot");
  if (slot && window.MutationObserver) {
    new MutationObserver(() => {
      const card = document.getElementById("result");
      if (!card || card.dataset.splashed) return;
      card.dataset.splashed = "1";
      const b = card.getBoundingClientRect();
      if (window.bpSplash) window.bpSplash(b.left + b.width / 2, Math.min(Math.max(b.top + 70, 90), innerHeight - 90), 0.8);
    }).observe(slot, { childList: true, subtree: true });
  }
})();
