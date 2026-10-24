// The Telegram card (Records and My profile). With a bot set up, the page asks for a one-time code as soon as it opens and puts it in the "Open Telegram to connect" link
// (t.me/<bot>?start=<code>): one tap, then Start in Telegram, and the bot connects the chat. This page notices by itself. The code stays available under "Show a code instead".
// Without a bot name there is no link to build, so the button shows the code to send to the bot instead.
(() => {
  const card = document.getElementById("tg");
  if (!card) return;
  const $ = (id) => document.getElementById(id);
  const post = (url) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); });
  const haveBot = !!card.dataset.bot;
  let tick = 0, poll = 0, left = 0, fresh = 0;
  const stop = () => { clearInterval(tick); clearInterval(poll); tick = poll = 0; };

  function showState(isLinked) {
    $("tg-badge").textContent = isLinked ? t("Connected") : t("Not connected");
    $("tg-badge").classList.toggle("ok", isLinked);
    $("tg-idle").hidden = isLinked || (!haveBot && !$("tg-code").hidden);
    $("tg-done").hidden = !isLinked;
    if (isLinked) { stop(); if (!haveBot) $("tg-code").hidden = true; }
  }
  async function isLinked() {
    try { return (await (await fetch("/api/telegram/status")).json()).linked > 0; } catch (e) { return false; }
  }
  async function check() {
    if (await isLinked()) { showState(true); setTimeout(() => location.reload(), 900); }
  }

  function show(r) {
    $("tg-codetext").textContent = r.code;
    $("tg-botname").textContent = r.bot ? "@" + r.bot : t("(your Baitproof bot)");
    $("tg-howto").textContent = t("Or open the bot and send:  /link {code}", { code: r.code });
    const open = $("tg-open");
    if (open && r.deep_link) { open.href = r.deep_link; open.classList.remove("wait"); }
    left = r.expires_in;
    stop();
    tick = setInterval(() => {
      left -= 1;
      $("tg-timer").textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
      if (left > 0) return;
      stop();
      if (haveBot && fresh < 5 && !document.hidden) fetchCode();                 // the link ran out while the page was open: a new one, quietly
      else if (haveBot) open?.classList.add("wait");                            // (a tab left alone: ask again when the person comes back)
      else { $("tg-code").hidden = true; $("tg-idle").hidden = false; }
    }, 1000);
    poll = setInterval(() => { if (!document.hidden) check(); }, 2500);
  }
  async function fetchCode() {
    fresh += 1;
    try { show(await post("/api/telegram/code")); } catch (e) { /* busy or offline: the link keeps opening the bot, and /link works with a code from later */ $("tg-open")?.classList.remove("wait"); }
  }

  if (haveBot && card.dataset.linked === "0") fetchCode();
  $("tg-connect")?.addEventListener("click", async () => {
    try { const r = await post("/api/telegram/code"); $("tg-idle").hidden = true; $("tg-code").hidden = false; show(r); } catch (e) { /* try again in a moment */ }
  });
  $("tg-unlink")?.addEventListener("click", async () => { await post("/api/telegram/unlink"); showState(false); if (haveBot) { fresh = 0; fetchCode(); } });
  // coming back from Telegram (a phone switches apps): look at once instead of waiting for the next tick, and get a fresh link if the old one ran out
  document.addEventListener("visibilitychange", () => {
    if (document.hidden || $("tg-done").hidden === false) return;
    check();
    if (haveBot && left <= 0 && !tick) { fresh = 0; fetchCode(); }
  });
})();
