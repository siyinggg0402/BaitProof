// Live view: stream each gate as it runs, then swap in the finished result. Falls back to a normal form post if anything fails.
const form = document.getElementById("check-form");
const LABEL = {
  ingest: "Reading the message", triage: "Checking how you're doing", intent: "Working out what it asks of you", tools: "Checking links and numbers",
  analysis: "AI review", grounding: "Verifying claims against the message", arbiter: "Weighing the evidence", loop: "Investigating further",
  "second-look": "Taking a second look", sufficiency: "Confidence check", critic: "Second reviewer", output: "Final safety checks",
  flywheel: "Adding to your practice", guard: "Safety net",
};
const ICON = { pass: "✓", flag: "!", skip: "–", block: "✕" };

if (form && window.fetch && window.ReadableStream) {
  form.addEventListener("submit", async (e) => {
    const msg = document.getElementById("message").value.trim();
    if (!msg) return;
    e.preventDefault();
    const live = document.getElementById("live"), list = document.getElementById("live-steps"), slot = document.getElementById("result-slot");
    const btn = form.querySelector("button.big");
    btn.disabled = true; slot.replaceChildren(); list.replaceChildren(); live.hidden = false;
    live.scrollIntoView({ behavior: "smooth", block: "nearest" });
    const fallback = () => { btn.disabled = false; live.hidden = true; form.submit(); };
    try {
      const res = await fetch("/api/check/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg }) });
      if (!res.ok || !res.body) return fallback();
      const reader = res.body.getReader(), dec = new TextDecoder();
      let buf = "", doneId = null;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, i).replace(/^data: /, ""); buf = buf.slice(i + 2);
          const ev = JSON.parse(line);
          if (ev.type === "step") {
            const s = ev.data;
            list.append(el("li", { className: "rise st-" + s.status },
              el("span", { className: "dot", textContent: ICON[s.status] || "•" }),
              el("span", { className: "lbl" }, el("strong", { textContent: LABEL[s.stage] || s.stage }), el("small", { textContent: s.detail }))));
          } else if (ev.type === "done") doneId = ev.data;
          else if (ev.type === "error") return fallback();
        }
      }
      if (!doneId) return fallback();
      const html = await (await fetch("/result/" + doneId)).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      slot.replaceChildren(...doc.body.childNodes);
      live.hidden = true; btn.disabled = false;
      slot.scrollIntoView({ behavior: "smooth", block: "start" });
      fetch("/api/map").then((r) => r.json()).then(renderMap);
    } catch (_) { fallback(); }
  });
}
