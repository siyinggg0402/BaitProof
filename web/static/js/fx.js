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
    { text: "DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz", tags: ["Rushing you", "Fake website address"], v: "Scam. Don't pay, don't tap the link.", ok: false },
    { text: "Hi grandma, it's me. I'm in trouble. Please buy four gift cards and send me the numbers. Don't tell Mom.", tags: ["Playing on your feelings", "Gift cards"], v: "Scam. Call them on a number you know.", ok: false },
    { text: "Reminder: your appointment is tomorrow at 10:30am. Call the number on your card to reschedule.", tags: [], v: "Looks fine, but verify first.", ok: true },
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
