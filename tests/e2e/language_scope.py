"""A real-browser check of one rule: the language of the site decides what a person is shown, never the language of a message they once checked.
For each site language it makes a new visitor, puts scams in French, German, Spanish, English, Chinese, Malay and Tamil into that visitor's own library (the way a
Spanish scam got into a friend's Scam Road), then plays: Scam Road in Chrome, and Scam Road, Inbox Rush and "Your circle" through their APIs. A message the visitor
planted must show only on the site in its language, nothing may carry a foreign marker word, and the explanation after a wrong turn must be in the site's language.
Usage: python -m tests.e2e.language_scope [--base https://your.site] [--runs 6] [--shots DIR]
Without --base it starts its own public-mode copy on a scratch database (no model credit is spent). With --base it checks a running site: it can only plant by
checking Spanish, French and German scams, which a site without the fix keeps and a site with it refuses to keep."""
import argparse
import os
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

from core.lang.text import in_language
from tests.e2e.browser import CHROME, SOFTWARE_GL, switch_language, wait_until_up

PORT = 8774
SITES = [("en", "en"), ("zh", "zh-Hans"), ("zh-Hant", "zh-Hant"), ("ms", "ms"), ("ta", "ta")]  # (language, tag in the header menu)
FOREIGN = {
    "es": "Banco Santander: su cuenta ha sido bloqueada. Verifique ahora en http://santander-seguro.top/verificar o su cuenta será cerrada en 24 horas.",
    "fr": "Votre colis est bloqué à la douane. Payez les frais de livraison sur http://colis-frais.top avant demain, sinon il sera renvoyé à l'expéditeur.",
    "de": "Ihr Paket wurde angehalten und ist nicht zugestellt worden. Bitte zahlen Sie die Gebühr sofort unter http://paket-gebuehr.top oder es geht zurück.",
}
OWN = {
    "en": "Your parcel is held at the depot. Pay the small fee today at http://parcel-fee-now.top or it will be sent back to the sender.",
    "zh": "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。",
    "ms": "Pos Laju: bungkusan anda ditahan. Sila bayar yuran di http://poslaju-bayar.top sekarang atau ia akan dikembalikan.",
    "ta": "உங்கள் பார்சல் நிறுத்தப்பட்டுள்ளது. இன்றே http://parcel-fee-now.top இல் கட்டணம் செலுத்துங்கள், இல்லையெனில் திருப்பி அனுப்பப்படும்.",
}
MARKERS = ("santander", "su cuenta", "votre colis", "frais de livraison", "ihr paket", "bitte zahlen")
CJK_RANGE, TAMIL_RANGE = ("一", "鿿"), ("஀", "௿")


def has(text: str, span: tuple[str, str]) -> bool:
    return any(span[0] <= c <= span[1] for c in text)


def group(lang: str) -> str:
    return "zh" if lang in ("zh", "zh-Hant") else lang


def wrong_language(text: str, site: str) -> str:
    """Why this explanation is in the wrong language for the site (or '')."""
    if site in ("zh", "zh-Hant"):
        return "" if has(text, CJK_RANGE) else "no Chinese"
    if site == "ta":
        return "" if has(text, TAMIL_RANGE) else "no Tamil"
    return "Chinese" if has(text, CJK_RANGE) else ("Tamil" if has(text, TAMIL_RANGE) else "")


def plant(ctx, base: str, local: bool, pace: float) -> None:
    """Give this visitor foreign scams (and one in each supported language) in their own library."""
    if local:
        from core.storage import db, library
        pid = next(c["value"] for c in ctx.cookies() if c["name"] == "bp")
        db.set_profile(pid)
        for text in [*FOREIGN.values(), *OWN.values()]:
            library.add_user_example(text, ["urgency-pressure"], "", "A real company gives you time to check.", "Stop and check it a second way.")
        planted = len(library.user_examples())
        db.set_profile(None)
        assert planted == len(FOREIGN) + len(OWN), f"the scams were not planted ({planted})"
    else:
        for text in FOREIGN.values():  # the same thing a friend did: check a message in another language
            ctx.request.post(base + "/check", form={"message": text})
            time.sleep(pace)


def drive_ui(page, base: str, runs: int, shots: str, tag: str) -> tuple[list[dict], list[str], list[str]]:
    """Scam Road in the real browser, the way a person plays: read the message, take a lane (often the wrong one), read the explanation."""
    seen, why, errors = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)[:120]))
    for n in range(runs):
        page.goto(base + "/road")
        page.wait_for_selector("#go")
        page.wait_for_function("() => window.__road && window.__road.state", timeout=60000)  # the game script (with the 3D library) is large: on a slow link it arrives after the button
        page.click("#go")
        for _ in range(60):
            if page.evaluate("() => window.__road.state") == "driving":
                break
            page.wait_for_timeout(250)
        for turn in range(8):
            text = page.evaluate("() => window.__road.text")
            seen.append({"text": text, "yours": page.is_visible("#msg-from"), "from": page.inner_text("#msg-from") if page.is_visible("#msg-from") else ""})
            if n == 0 and turn == 0:
                page.screenshot(path=os.path.join(shots, f"road-{tag}.png"))
            if any(k in text.lower() for k in MARKERS) and not os.path.exists(os.path.join(shots, f"foreign-{tag}.png")):  # a message in another language: keep what the visitor saw
                try:
                    page.wait_for_selector("#msg:not([hidden])", timeout=4000)
                    page.evaluate("() => window.__road.advance(Math.max(0, window.__road.gateAhead - 30))")
                    page.wait_for_timeout(600)
                except Exception:
                    pass
                page.screenshot(path=os.path.join(shots, f"foreign-{tag}.png"))
            page.keyboard.press("13"[turn % 2])  # scam lane, then looks-fine lane: about half of them are wrong
            page.wait_for_timeout(250)
            page.evaluate("() => window.__road.advance(window.__road.gateAhead + 2)")
            page.wait_for_timeout(900)
            if page.is_visible("#why:not([hidden])"):
                why.append(page.inner_text("#why"))
                page.click("#why-go")
            if page.locator("#end:not([hidden])").count():
                break
    return seen, why, errors


def sample_api(ctx, base: str, runs: int, pace: float) -> tuple[list[dict], list[str]]:
    """Scam Road runs, Inbox Rush rounds and "Your circle" through the same endpoints the pages use: many more messages than a person would read."""
    items, why = [], []
    for i in range(runs):
        run = ctx.request.post(base + "/api/road/start", data={"mode": "road"}).json()
        time.sleep(pace)
        queue = list(run["items"])
        for turn in range(10):
            if not queue:
                break
            g = queue.pop(0)
            items.append(g)
            r = ctx.request.post(base + "/api/road/answer", data={"run": run["run"], "gate": g["id"], "lane": 0 if turn % 2 else 2}).json()
            why += [r[k] for k in ("tell", "action") if r.get(k)]  # the explanation shown after a turn (tell_phrase quotes the message itself, so it is left out)
            queue += r.get("next", [])
    for mode in ("rush", "rush", "yours"):
        r = ctx.request.post(base + "/api/game/start", data={"mode": mode})
        time.sleep(pace)
        if r.ok:
            items += r.json()["items"]
    return items, why


def check_site(p, base: str, local: bool, runs: int, shots: str, pace: float) -> list[str]:
    problems = []
    print(f"{'site':8} {'UI gates':>8} {'API msgs':>8} {'own scams shown':>34}  explanations  result")
    for site, tag in SITES:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=SOFTWARE_GL)
        ctx = b.new_context(viewport={"width": 1100, "height": 800})
        page = ctx.new_page()
        page.goto(base)
        switch_language(page, site, tag)
        plant(ctx, base, local, pace)
        ui, ui_why, errors = drive_ui(page, base, max(2, runs // 2), shots, site)
        api, api_why = sample_api(ctx, base, runs, pace)
        mine = sorted({m["text"][:14] for m in api if m.get("yours") or m.get("family")})  # (the pages tell us which messages are the visitor's own)
        bad = []
        for m in [*ui, *api]:
            low = m["text"].lower()
            if any(k in low for k in MARKERS):
                bad.append(f"foreign message shown: {m['text'][:50]!r}")
            if m.get("yours") or m.get("family"):  # one of the visitor's own scams: it must be in this site's language
                if not in_language(m["text"], site):
                    bad.append(f"own scam in another language: {m['text'][:50]!r}")
        bad += [f"explanation in the wrong language ({wrong_language(w, site)}): {w[:60]!r}" for w in [*ui_why, *api_why] if wrong_language(w, site)]
        bad += [f"page error: {e}" for e in errors]
        print(f"{site:8} {len(ui):8} {len(api):8} {', '.join(mine)[:34]:>34}  {len(ui_why) + len(api_why):12}  " + ("ok" if not bad else f"{len(bad)} PROBLEM(S)"))
        for line in sorted(set(bad))[:6]:
            print("         -", line)
        problems += [f"{site}: {x}" for x in bad]
        b.close()
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--shots", default=tempfile.mkdtemp(prefix="langscope-"))
    a = ap.parse_args()
    srv = None
    if a.base:
        base, local, pace = a.base.rstrip("/"), False, 2.3  # the live site limits how fast one visitor may start games
    else:
        scratch = tempfile.mkdtemp()
        env = {**os.environ, "BAITPROOF_DB": scratch + "/scope.sqlite", "BAITPROOF_LOG_DIR": scratch + "/logs", "BAITPROOF_CACHE_DIR": scratch + "/cache", "BAITPROOF_MULTIUSER": "1",
               "NEBIUS_API_KEY": "", "TAVILY_API_KEY": "", "BAITPROOF_BLOCKLIST": "0", "BAITPROOF_NET_TOOLS": "0", "BAITPROOF_RATE": "100000", "BAITPROOF_STT": "0",
               "VAPID_PRIVATE_KEY": "", "VAPID_PUBLIC_KEY": ""}
        os.environ.update({k: env[k] for k in ("BAITPROOF_DB", "BAITPROOF_MULTIUSER", "NEBIUS_API_KEY")})  # this process writes to the same database as the server
        srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.main:app", "--port", str(PORT)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base, local, pace = f"http://127.0.0.1:{PORT}", True, 0.0
        wait_until_up(base)
    try:
        with sync_playwright() as p:
            problems = check_site(p, base, local, a.runs, a.shots, pace)
    finally:
        if srv:
            srv.terminate()
    print(f"\nscreenshots: {a.shots}")
    print("LANGUAGE SCOPE OK" if not problems else f"LANGUAGE SCOPE FAILED: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
