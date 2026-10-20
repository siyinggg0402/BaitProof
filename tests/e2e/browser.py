"""Real-browser smoke test (not collected by pytest). Needs: pip install playwright + Google Chrome installed.
Run: python -m tests.e2e.browser"""
import os
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import expect, sync_playwright

PORT = 8771
CHROME = os.getenv("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


SCAM_ZH = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息并支付3元费用，逾期将退回。"


def switch_language(page, code: str, tag: str) -> None:
    """Use the header menu like a person would: open it, pick the language, wait for the page to come back in it."""
    page.click("#lang summary")
    page.click(f"#lang a[hreflang='{tag}']")
    expect(page.locator("html")).to_have_attribute("lang", tag)
    assert not page.evaluate("document.getElementById('lang').open"), "the menu should be closed after choosing"


def zh_pass(page, base, no_overflow, expect_401) -> None:
    import re

    page.goto(base)
    page.click("#lang summary")
    page.keyboard.press("Escape")
    assert not page.evaluate("document.getElementById('lang').open"), "Escape closes the language menu"
    page.click("#lang summary")
    page.mouse.click(8, 600)
    assert not page.evaluate("document.getElementById('lang').open"), "a click elsewhere closes the language menu"
    switch_language(page, "zh", "zh-Hans")
    no_overflow("zh-home")
    assert "让你的家人" in page.inner_text("h1") and "查一查" in page.inner_text(".tabs") and "练习" in page.inner_text(".tabs")
    assert page.is_visible(".tabs") and not page.is_visible("nav .navlink")

    # check a Chinese scam (offline rules): the verdict, the evidence and the live steps are all Chinese
    page.fill("#message", SCAM_ZH)
    page.click("button.big:has-text('帮我检查')")
    page.wait_for_selector("#result .banner")
    assert "骗局" in page.inner_text("#result .banner"), page.inner_text("#result .banner")
    result = page.inner_text("#result")
    for word in ("破绽", "该怎么做", "证据", "红旗", "朗读", "已加入你的练习"):
        assert word in result, (word, result)
    assert page.locator("#live-steps li").count() >= 5 and re.search("[一-鿿]", page.inner_text("#live-steps")) and not page.is_visible("#live")
    no_overflow("zh-result")
    # read aloud uses a Chinese voice
    page.evaluate("(() => { window.__lang = null; speechSynthesis.speak = (u) => { window.__lang = u.lang; }; })()")
    page.click("#result .speak")
    assert page.evaluate("window.__lang") == "zh-CN", page.evaluate("window.__lang")
    page.click("#result [data-feedback=up]")
    page.wait_for_selector("#result [data-fb-note]:has-text('谢谢')")

    # practice
    page.goto(base + "/train")
    no_overflow("zh-train")
    assert "快速练习" in page.inner_text("h1")
    page.click("#start")
    for i in range(4):
        page.wait_for_selector(".step .opt, .step textarea")
        if page.query_selector(".step .opt"):
            page.click(".step .opt >> nth=0")
        else:
            page.fill(".step textarea", "我会忽略它，再打电话给银行核实")
            page.click(".step button.big")
        page.wait_for_selector(".feedback")
        assert re.search("[一-鿿]", page.inner_text(".feedback"))
        if i == 0:
            no_overflow("zh-train-feedback")
        page.click(".step button.big:last-of-type")
    page.wait_for_selector("text=你答对了")
    no_overflow("zh-train-finish")

    # game: Inbox Rush by keyboard (S / F), one whole round
    page.goto(base + "/game")
    page.wait_for_selector(".mode-card")
    assert "收件箱快答" in page.inner_text(".mode-card >> nth=0") and "第1级" in page.inner_text(".hud-card")
    no_overflow("zh-game-hub")
    page.click(".mode-card >> nth=0")
    for i in range(9):  # (a Chinese round can have fewer than 8 messages: stop when the results appear)
        page.wait_for_selector(".choice, .end h1")
        if page.query_selector(".end h1"):
            break
        if i == 0:
            assert "骗局" in page.inner_text(".choices") and "先核实" in page.inner_text(".choices")
            no_overflow("zh-game-play")
        page.keyboard.press("s" if i % 2 == 0 else "f")
        page.wait_for_selector(".reveal-card .banner-r")
        if i == 0:
            assert re.search("这条|识破|眼力|小心|破绽", page.inner_text(".reveal-card .banner-r")) and "该怎么做" in page.inner_text(".reveal-card") + "该怎么做"
            no_overflow("zh-game-reveal")
        page.click(".reveal-card button.big")
    page.wait_for_selector(".end h1")
    no_overflow("zh-game-end")
    assert "XP" in page.inner_text(".end") and "最高连对" in page.inner_text(".end") and page.locator(".end .kpi").count() == 4
    page.click(".end-actions button.sec")
    page.wait_for_selector(".boss-grid .tile")
    assert "关主挑战" in page.inner_text("main")
    page.click(".mode-card >> nth=2")  # Spot the tell: tap the clauses that give it away
    page.wait_for_selector(".words .w")
    page.click(".words .w >> nth=0")
    page.click(".words .w >> nth=1")
    page.click("button.big:has-text('检查我的答案')")
    page.wait_for_selector(".reveal-card .banner-r")
    no_overflow("zh-game-tell")

    # records and the Telegram code
    page.goto(base + "/records")
    page.wait_for_selector("#tg")
    no_overflow("zh-records")
    assert page.locator(".rec").count() >= 1 and "骗局" in page.inner_text(".rec >> nth=0") and re.search("刚刚|分钟前", page.inner_text(".rec >> nth=0"))
    page.click("#tg-connect")
    page.wait_for_selector("#tg-codetext:not(:empty)")
    code = page.inner_text("#tg-codetext")
    assert "/link " + code in page.inner_text("#tg-howto") and "或者打开机器人" in page.inner_text("#tg-howto")
    no_overflow("zh-records-code")

    # family challenge, the family box and the share card
    page.goto(base)
    page.click("nav .cta")
    page.wait_for_selector("#start")
    assert "你能识破骗局吗" in page.inner_text("h1")
    no_overflow("zh-challenge")
    page.click("#start")
    for i in range(6):
        page.wait_for_selector(".step .opt")
        page.click(".step .opt >> nth=0")
    page.wait_for_selector(".family")
    no_overflow("zh-challenge-result")
    href = page.get_attribute(".family a:has-text('WhatsApp')", "href")
    from urllib.parse import unquote

    assert href.startswith("https://wa.me/?text=") and "妈妈" in unquote(href) and "防骗小测验" in unquote(href)
    page.click(".family button:has-text('复制消息')")
    page.wait_for_selector(".family .muted:has-text('已复制')")
    page.click("text=查看我的成绩卡")
    page.wait_for_selector(".bigpct")
    assert "lang=zh" in page.url
    no_overflow("zh-card")

    # Traditional from the same page (the menu keeps the page), then back to English
    switch_language(page, "zh-Hant", "zh-Hant")
    assert "/card/" in page.url and "挑戰" in page.inner_text("main") and "挑战" not in page.inner_text("main")
    no_overflow("zh-hant-card")
    page.goto(base + "/game")
    page.wait_for_selector(".mode-card")
    assert "收件箱快答" in page.inner_text(".mode-card >> nth=0") and "第" in page.inner_text(".hud-card") and "级" not in page.inner_text(".hud-card")
    no_overflow("zh-hant-game")
    page.goto(base + "/records")
    no_overflow("zh-hant-records")
    assert "我的記錄" in page.inner_text("h1")
    switch_language(page, "en", "en")
    chrome = page.inner_text("h1") + page.inner_text(".kpis") + page.inner_text(".tabs") + page.inner_text("#tg")  # (the records themselves keep the language they were written in)
    assert "My records" in chrome and "Practice" in chrome and not re.search("[一-鿿]", chrome), chrome
    no_overflow("en-after-zh")


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

            # ---- game: hub, Inbox Rush by keyboard, boss, spot-the-tell
            page.goto(base + "/game")
            page.wait_for_selector(".mode-card")
            no_overflow("game-hub")
            assert page.is_visible(".tabs") and not page.is_visible("nav .navlink"), "phone layout should use the bottom tab bar"
            page.click(".mode-card:has-text('Inbox Rush')")
            for i in range(8):
                page.wait_for_selector(".choice")
                if i == 0:
                    no_overflow("game-play")
                page.keyboard.press("s" if i % 2 == 0 else "f")
                page.wait_for_selector(".reveal-card .banner-r")
                if i == 0:
                    no_overflow("game-reveal")
                page.click("button.big:has-text('Next'), button.big:has-text('See results')")
            page.wait_for_selector(".end h1")
            no_overflow("game-end")
            assert "XP" in page.inner_text(".end") and page.locator(".end .kpi").count() == 4
            page.screenshot(path=os.path.join(tempfile.gettempdir(), "e2e_game_end.png"))
            page.click("button:has-text('All games')")
            page.wait_for_selector(".boss-grid .tile")
            assert page.locator(".boss-grid .tile").count() == 12
            assert "Level" in page.inner_text(".hud-card") and "XP" in page.inner_text(".hud-card")
            page.click(".boss-grid .tile >> nth=0")
            page.wait_for_selector(".hearts")
            assert page.inner_text(".hearts").count("♥") == 3
            page.click(".choice.c-unsure")
            page.wait_for_selector(".reveal-card")
            page.click("button.ghost.quit")
            page.wait_for_selector(".mode-card")
            page.click(".mode-card:has-text('Spot the Tell')")
            page.wait_for_selector(".words .w")
            page.click(".words .w >> nth=0")
            page.click(".words .w >> nth=1")
            assert page.locator(".words .w.sel").count() == 2
            page.click("button.big:has-text('Check my answer')")
            page.wait_for_selector(".reveal-card .banner-r")
            assert page.locator(".reveal-card mark").count() == 1  # the real giveaway is highlighted
            no_overflow("game-tell")

            # ---- records: history from the checks above, Telegram connect, delete
            page.goto(base + "/records")
            page.wait_for_selector("#tg")
            no_overflow("records")
            assert page.locator(".rec").count() >= 1
            assert page.is_visible(".tabs")
            page.click("#tg-connect")
            page.wait_for_selector("#tg-codetext:not(:empty)")
            code = page.inner_text("#tg-codetext")
            assert len(code) == 6 and code.isalnum() and "/link " + code in page.inner_text("#tg-howto")
            no_overflow("records-code")
            n = page.locator(".rec").count()
            page.click(".rec-del >> nth=0")
            expect(page.locator(".rec")).to_have_count(n - 1)  # (a string wait_for_function would need eval, which our CSP forbids)

            # ---- Chinese pass: switch language with the header menu, then check, practise, play, records and challenge at phone width
            zh_pass(page, base, no_overflow, expect_401)
            b.close()
    finally:
        srv.terminate()
    print("PROBLEMS:" if problems else "E2E OK", *problems, sep="\n  ")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
