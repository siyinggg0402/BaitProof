// Other ways to add a message: a screenshot (a button, drag and drop, or paste) and a voice note (our server's speech-to-text, or the browser's own).
// Whatever is read goes into the text box first, so the person sees exactly what will be checked and can fix it. Needs app.js (t, el, I18N) and check.js.
(() => {
  const form = document.getElementById("check-form"), area = document.getElementById("message"), box = document.getElementById("inputs");
  const status = document.getElementById("input-status"), source = document.getElementById("source"), fileInput = document.getElementById("shot-file");
  const shotBtn = document.getElementById("shot-btn"), speakBtn = document.getElementById("speak-btn"), langSel = document.getElementById("speak-lang");
  if (!form || !area || !box || !status || !source || !window.fetch || !window.FormData) return;

  const AUTO_CHECK = { screenshot: true, voice: false }; // a mis-heard voice note can lose the scary part, so for voice the person presses Check it themselves
  const MAX_SECONDS = 45, SHRINK_OVER = 3.5e6, SHRINK_TO = 2000, GIVE_UP = 25e6;
  let busy = false, preview = "", session = null; // session: a recording or a listening in progress, { stop(), cancel() }

  // ---- what is on screen under the buttons
  const deco = (cls) => { const s = el("span", { className: cls }); s.setAttribute("aria-hidden", "true"); return s; };
  const show = (...kids) => status.replaceChildren(...kids);
  function dropPreview() { if (preview) { URL.revokeObjectURL(preview); preview = ""; } }
  function clear() { dropPreview(); show(); }
  const thumb = () => (preview ? el("img", { className: "in-thumb", src: preview, alt: t("The screenshot you chose") }) : "");
  function working(text) { show(el("div", { className: "in-busy" }, deco("spin"), el("span", { textContent: text }), thumb())); }
  function notice(lines) {
    show(el("div", { className: "in-notice" }, thumb(), el("div", {}, ...lines.map((x, i) => el("p", { className: i ? "in-extra" : "in-main", textContent: x })))));
  }
  function fail(text) { show(el("p", { className: "in-err", textContent: text })); }
  function lock(on) { busy = on; [shotBtn, speakBtn].forEach((b) => { if (b) b.disabled = on; }); }
  function setText(text, kind) { // the whole text is shown, so the person can read all of it against the picture
    area.value = text.slice(0, 4000);
    source.value = kind;
    area.rows = 3;
    while (area.scrollHeight > area.clientHeight && area.rows < 10) area.rows += 1;
  }
  const origin = { channel: document.getElementById("origin-channel"), app: document.getElementById("origin-app"), sender: document.getElementById("origin-sender") };
  function setOrigin(d) { origin.channel.value = d.channel || ""; origin.app.value = d.app || ""; origin.sender.value = d.sender || ""; } // what the screenshot showed: where the message seems to come from
  function reset() { source.value = "text"; setOrigin({}); area.rows = 3; clear(); }
  const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const startCheck = () => (form.requestSubmit ? form.requestSubmit() : form.querySelector("button.big").click()); // the live view in check.js takes it from here
  const generic = () => t("Something went wrong. Please try again, or paste the text instead.");

  // ---- talking to our server
  async function post(url, fd) {
    let res;
    try { res = await fetch(url, { method: "POST", body: fd }); }
    catch (_) { throw new Error(t("I couldn't reach the server. Check your connection and try again.")); }
    let data = null;
    try { data = await res.json(); } catch (_) { /* not JSON: a proxy's error page */ }
    if (!res.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || generic());
    return data || {};
  }

  // ---- a screenshot
  async function shrink(file) { // a big photo is slow on a phone connection: send a smaller copy (the original if anything goes wrong)
    try {
      const bmp = await createImageBitmap(file), scale = Math.min(1, SHRINK_TO / Math.max(bmp.width, bmp.height));
      const c = document.createElement("canvas");
      c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale);
      c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
      return await new Promise((done) => c.toBlob(done, "image/jpeg", 0.9));
    } catch (_) { return null; }
  }
  async function sendImage(file) {
    if (busy || session) return;
    dropPreview();
    if (file.size > GIVE_UP) return fail(t("That picture is too big. Please try a smaller screenshot."));
    lock(true);
    preview = URL.createObjectURL(file);
    working(t("Reading your screenshot…"));
    let go = false;
    try {
      const blob = file.size > SHRINK_OVER ? (await shrink(file)) || file : file;
      const fd = new FormData();
      fd.append("file", blob, "screenshot");
      const data = await post("/api/read/image", fd);
      const text = String(data.text || "").trim();
      if (!text) throw new Error(t("I couldn't find a message in that. Try again, or paste the text instead."));
      const codes = data.qr_urls || [], missing = codes.filter((u) => !text.includes(u)); // our reader already adds a decoded QR address to the text; make sure it is there
      setText(missing.length ? text + "\n\n" + missing.join("\n") : text, "screenshot");
      setOrigin(data);
      const readable = data.legible !== false;
      const lines = [readable ? t("I read this from your screenshot. Check it matches, fix anything wrong, then check it again.")
        : t("The picture was hard to read, so I haven't checked it yet. Please look at the text, fix anything wrong, then press “Check it”.")];
      if (codes.length) lines.push(t("There is a QR code in the picture. I added its web address to the text so it is checked too. Don't scan it."));
      if (data.note) lines.push(String(data.note));
      notice(lines);
      go = readable && AUTO_CHECK.screenshot;
      if (!go) area.focus();
    } catch (e) {
      dropPreview();
      fail(e.message || generic());
    } finally { lock(false); }
    if (go) startCheck();
  }

  // ---- a voice note
  const hasSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  const secure = window.isSecureContext !== false;
  const canRecord = !!(secure && window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  const mode = box.dataset.audio === "1" && canRecord ? "server" : hasSpeech && secure ? "browser" : "none";

  const speechCode = () => (langSel ? langSel.value : I18N.speech); // en-US or ms-MY on an English page, zh-CN / zh-TW on a Chinese one
  const hint = () => speechCode().split("-")[0]; // en | ms | zh, for our server
  function listening() {
    const time = el("span", { className: "in-time", textContent: "0:00" });
    time.setAttribute("aria-hidden", "true");
    show(el("div", { className: "in-rec" }, deco("rec-dot"), el("span", { textContent: t("Listening… tap Stop when you are done.") }), time));
    return time;
  }
  function recording(on) {
    speakBtn.classList.toggle("rec", on);
    speakBtn.querySelector(".ico").replaceChildren(icon(on ? "stop" : "mic"));
    speakBtn.querySelector(".lbl").textContent = on ? t("Stop") : t("Speak");
    if (shotBtn) shotBtn.disabled = on;
    if (langSel) langSel.disabled = on;
  }
  function heard(text) {
    setText(text, "voice");
    notice([t("I heard this. Check it matches, fix anything wrong, then press “Check it”.")]);
    if (AUTO_CHECK.voice) startCheck();
    else form.querySelector("button.big").focus();
  }
  function micProblem(code) {
    if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") return t("I couldn't use the microphone. Allow it in your browser, or type the message instead.");
    if (code === "no-speech") return t("I didn't hear anything. Tap Speak and try again.");
    if (code === "network") return t("The speech service can't be reached right now. Please type the message instead.");
    return generic();
  }

  function listenInBrowser() { // the browser's own speech service; we only ever get the words
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition, rec = new Speech(), before = area.value;
    let words = "", problem = "", cancelled = false;
    rec.lang = speechCode(); rec.interimResults = true; rec.continuous = true; rec.maxAlternatives = 1;
    const glue = rec.lang.startsWith("zh") ? "" : " ", time = listening();
    const started = Date.now(), tick = setInterval(() => { time.textContent = mmss((Date.now() - started) / 1000); }, 500);
    const limit = setTimeout(() => rec.stop(), MAX_SECONDS * 1000);
    rec.onresult = (e) => {
      words = Array.from(e.results).map((r) => r[0].transcript).join(glue).replace(/\s+/g, " ").trim();
      area.value = words.slice(0, 4000); // the words appear as they are spoken
    };
    rec.onerror = (e) => { if (e.error !== "aborted") problem = micProblem(e.error); };
    rec.onend = () => {
      clearInterval(tick); clearTimeout(limit); session = null; recording(false);
      if (cancelled) { area.value = before; return clear(); }
      if (problem || !words) { area.value = before; return fail(problem || micProblem("no-speech")); }
      heard(words);
    };
    session = { stop: () => rec.stop(), cancel: () => { cancelled = true; rec.abort(); } };
    recording(true);
    try { rec.start(); } catch (_) { clearInterval(tick); clearTimeout(limit); session = null; recording(false); fail(generic()); }
  }

  async function recordForServer() { // MediaRecorder, then our server turns it into words
    lock(true);
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (_) { lock(false); return fail(micProblem("not-allowed")); }
    lock(false);
    const kinds = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"], kind = kinds.find((k) => MediaRecorder.isTypeSupported(k)) || "";
    const release = () => stream.getTracks().forEach((track) => track.stop()); // the microphone light goes off
    let rec;
    try { rec = new MediaRecorder(stream, kind ? { mimeType: kind } : undefined); } catch (_) { release(); return fail(generic()); }
    const chunks = [];
    let cancelled = false;
    const time = listening(), started = Date.now(), tick = setInterval(() => { time.textContent = mmss((Date.now() - started) / 1000); }, 500);
    const limit = setTimeout(() => rec.stop(), MAX_SECONDS * 1000);
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = async () => {
      clearInterval(tick); clearTimeout(limit); release(); session = null; recording(false);
      if (cancelled) return clear();
      if (!chunks.length) return fail(micProblem("no-speech"));
      const blob = new Blob(chunks, { type: rec.mimeType || kind || "audio/webm" });
      lock(true);
      working(t("Turning your voice into text…"));
      try {
        const fd = new FormData();
        fd.append("file", blob, "voice." + (blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm"));
        fd.append("lang", hint());
        const data = await post("/api/read/audio", fd);
        const text = String(data.text || "").trim();
        if (!text) throw new Error(micProblem("no-speech"));
        heard(text);
      } catch (e) { fail(e.message || generic()); } finally { lock(false); }
    };
    session = { stop: () => rec.stop(), cancel: () => { cancelled = true; rec.stop(); } };
    recording(true);
    rec.start();
  }

  // ---- wiring
  if (shotBtn) shotBtn.addEventListener("click", () => { if (!busy && !session) fileInput.click(); });
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    fileInput.value = ""; // so choosing the same picture again still counts
    if (file) sendImage(file);
  });
  const imageIn = (files) => Array.from(files || []).find((f) => f.type.startsWith("image/")) || (files && files[0]);
  const hasFiles = (e) => !!e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
  document.addEventListener("dragover", (e) => { if (hasFiles(e)) { e.preventDefault(); form.classList.add("drop"); } });
  document.addEventListener("dragleave", (e) => { if (!e.relatedTarget) form.classList.remove("drop"); });
  document.addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault(); // otherwise the browser would leave this page to open the picture
    form.classList.remove("drop");
    const file = imageIn(e.dataTransfer.files);
    if (file) sendImage(file);
  });
  document.addEventListener("paste", (e) => { // a copied picture (not copied words) is a screenshot to read
    const cb = e.clipboardData;
    if (!cb || cb.getData("text/plain")) return;
    const file = Array.from(cb.files || []).find((f) => f.type.startsWith("image/"));
    if (file) { e.preventDefault(); sendImage(file); }
  });

  if (mode !== "none") {
    speakBtn.hidden = false;
    if (langSel) {
      langSel.hidden = false;
      try { const saved = localStorage.getItem("bp-speak-lang"); if (saved && Array.from(langSel.options).some((o) => o.value === saved)) langSel.value = saved; } catch (_) { /* private mode */ }
      langSel.addEventListener("change", () => { try { localStorage.setItem("bp-speak-lang", langSel.value); } catch (_) { /* private mode */ } });
    }
    const line = document.getElementById(mode === "server" ? "priv-server" : "priv-browser");
    if (line) line.hidden = false;
    speakBtn.addEventListener("click", () => {
      if (session) return session.stop();
      if (busy) return;
      dropPreview();
      return mode === "server" ? recordForServer() : listenInBrowser();
    });
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && session) session.cancel(); });
  window.addEventListener("pagehide", () => { if (session) session.cancel(); });
  area.addEventListener("input", () => { if (!area.value.trim()) reset(); });
  area.addEventListener("paste", (e) => { // pasting words over everything that was read means the message is typed text again
    if (source.value !== "text" && e.clipboardData && e.clipboardData.getData("text/plain") && area.selectionStart === 0 && area.selectionEnd === area.value.length) reset();
  });
  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", reset));
  if (shotBtn || mode !== "none") box.hidden = false;
})();
