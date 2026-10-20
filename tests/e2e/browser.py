"""Real-browser smoke test (not collected by pytest). Needs: pip install playwright + Google Chrome installed.
Run: python -m tests.e2e.browser"""
import os
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

PORT = 8771
CHROME = os.getenv("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def main() -> int:
    # NEBIUS_API_KEY="" forces offline rules: the e2e test must never spend model credit (dotenv does not override set vars)
    env = {**os.environ, "BAITPROOF_DB": tempfile.mkdtemp() + "/e2e.sqlite", "BAITPROOF_LOG_DIR": tempfile.mkdtemp(), "NEBIUS_API_KEY": "", "BAITPROOF_ADMIN_TOKEN": "e2e-token"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.main:app", "--port", str(PORT)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    base, problems = f"http://127.0.0.1:{PORT}", []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True)
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                                permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            expect_401 = {"n": 0}  # the wrong-token login attempt deliberately returns 401

            def on_console(m):
                if m.type in ("error", "warning") and not (expect_401["n"] and "401" in m.text):
                    problems.append(f"console {m.type}: {m.text}")
            page.on("console", on_console)
            page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

            W = 390  # fixed viewport width; innerWidth can't be used because mobile emulation widens it to fit overflow

            def no_overflow(label):
                bad = page.evaluate("""(W) => {
                    const bar = document.querySelector('.bar'), br = bar ? bar.getBoundingClientRect().right : W;
                    const out = [];
                    for (const e of document.querySelectorAll('body *')) {
                        if (e.closest('.glow, .tbl-wrap') || !e.getClientRects().length) continue;  // tables scroll inside their own container
                        const r = e.getBoundingClientRect().right;
                        if (r > W + 1 || (bar && bar.contains(e) && r > br + 1)) out.push(e.tagName.toLowerCase() + '.' + (e.className || '') + '@' + Math.round(r));
                    }
                    return [document.documentElement.scrollWidth, ...out.slice(0, 5)];
                }""", W)
                if bad[0] > W or len(bad) > 1:
                    problems.append(f"{label}: overflow/clipping {bad}")

            # Check flow
            page.goto(base)
            no_overflow("home")
            page.click("text=Parcel fee")
            assert "dhl-fee-pay" in page.input_value("#message")
            page.click("button.big:has-text('Check it')")
            page.wait_for_selector("#result .banner")
            assert "SCAM" in page.inner_text("#result .banner"), page.inner_text("#result .banner")
            assert "Added to your practice" in page.inner_text("#result")
            no_overflow("result")
            steps = page.locator("#live-steps li").count()
            assert steps >= 5 and not page.is_visible("#live"), steps  # the live view showed the gates, then got out of the way
            res = page.inner_text("#result").lower()  # inner_text applies CSS text-transform
            assert "the evidence" in res and "red flag" in res
            page.click("#result [data-feedback=up]")
            page.wait_for_selector("#result [data-fb-note]:has-text('Thanks')")
            assert page.is_disabled("#result [data-feedback=down]")

            # operator dashboard: login, then numbers without any message text
            page.goto(base + "/admin")
            assert page.url.endswith("/admin/login")
            expect_401["n"] = 1
            page.fill("#token", "wrong")
            page.click("button.big")
            page.wait_for_selector(".err")
            expect_401["n"] = 0
            page.fill("#token", "e2e-token")
            page.click("button.big")
            page.wait_for_selector("text=Is it running OK?")
            no_overflow("admin")
            body = page.inner_text("body")
            assert "Recent checks" in body and "gift" not in body.lower().split("recent checks")[1][:2000]
            assert page.locator("table.tbl tbody tr").count() >= 1 and "👍 1" in body
            page.goto(base)

            # text size toggle persists
            page.click("#textsize")
            assert page.evaluate("document.documentElement.classList.contains('big')")
            page.reload()
            assert page.evaluate("document.documentElement.classList.contains('big')")
            page.click("#textsize")

            # Practice flow
            page.goto(base + "/train")
            no_overflow("train")
            before = int(page.inner_text("#score"))
            page.click("#start")
            for i in range(4):
                page.wait_for_selector(".step .opt, .step textarea")
                if page.query_selector(".step .opt"):
                    page.click(".step .opt >> nth=0")
                else:
                    page.fill(".step textarea", "I would ignore it and call the real bank")
                    page.click("text=Check my answer")
                page.wait_for_selector(".feedback")
                page.click("button.big:has-text('Next'), button.big:has-text('Finish')")
            page.wait_for_selector("text=You got")
            no_overflow("train-finish")
            page.wait_for_timeout(1200)
            print(f"practice: score {before} -> {page.inner_text('#score')}")

            # Challenge flow + family box
            page.goto(base)
            page.click("nav .cta")
            page.wait_for_selector("#start")
            no_overflow("challenge")
            page.click("#start")
            for i in range(6):
                page.wait_for_selector(".step .opt")
                page.click(".step .opt >> nth=0")
            page.wait_for_selector(".family")
            no_overflow("challenge-result")
            href = page.get_attribute(".family a:has-text('WhatsApp')", "href")
            assert href.startswith("https://wa.me/?text=") and "Mum" in href
            page.fill(".family input", "Dad")
            assert "Dad" in page.get_attribute(".family a:has-text('WhatsApp')", "href")
            page.click(".family button:has-text('Copy message')")
            page.wait_for_selector(".family .muted:has-text('Copied')")
            page.click("text=Open my result card")
            page.wait_for_selector(".bigpct")
            no_overflow("card")
            page.screenshot(path=os.path.join(tempfile.gettempdir(), "e2e_card.png"))
            b.close()
    finally:
        srv.terminate()
    print("PROBLEMS:" if problems else "E2E OK", *problems, sep="\n  ")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
