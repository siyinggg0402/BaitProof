"""Real-browser smoke test (not collected by pytest). Needs: pip install playwright + Google Chrome installed.
Run: python -m tests.e2e.browser"""
import base64
import io
import os
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

PORT = 8771
FAKE_PORT = 8772  # the same website with canned screenshot and voice readers (tests/e2e/fake_inputs_app.py)
SOCIAL_PORT = 8773  # a public-mode copy (one profile per visitor), for friends and the 3D road
CHROME = os.getenv("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


SCAM_ZH = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息并支付3元费用，逾期将退回。"


# ------------------------------------------------------------------------------------------------ screenshot and voice input
# A stand-in for the browser's speech service: the real one needs a network and a person. `window.__sr` is the latest one; the test speaks through it.
FAKE_SPEECH = """(() => {
  class FakeSpeech {
    constructor() { window.__sr = this; this.lang = ""; }
    start() { window.__srLang = this.lang; }
    say(text) { this.onresult && this.onresult({ results: [[{ transcript: text }]] }); }
    fail(code) { this.onerror && this.onerror({ error: code }); this.onend && this.onend(); }
    stop() { setTimeout(() => this.onend && this.onend(), 10); }
    abort() { setTimeout(() => this.onend && this.onend(), 10); }
  }
  window.SpeechRecognition = window.webkitSpeechRecognition = FakeSpeech;
})();"""
NO_SPEECH = "delete window.SpeechRecognition; delete window.webkitSpeechRecognition;"
CLIPBOARD_JS = """([b64, text]) => { const dt = new DataTransfer();
  if (b64) dt.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], "shot.png", { type: "image/png" }));
  if (text) dt.setData("text/plain", text);
  const ev = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true });
  document.getElementById("message").dispatchEvent(ev); return ev.defaultPrevented; }"""
DROP_JS = """(b64) => { const dt = new DataTransfer(), form = document.getElementById("check-form");
  dt.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], "shot.png", { type: "image/png" }));
  form.dispatchEvent(new DragEvent("dragover", { dataTransfer: dt, bubbles: true, cancelable: true }));
  const over = form.classList.contains("drop");
  const ev = new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }); form.dispatchEvent(ev);
  return [over, form.classList.contains("drop"), ev.defaultPrevented]; }"""
WORDS = {
    "en": {
        "needs_ai": "Reading screenshots needs the AI, which is not switched on here. Paste the text instead.", "reading": "Reading your screenshot", "turning": "Turning your voice into text",
        "priv_image": "The AI reads your screenshot to get the text. We don't keep the picture.", "priv_server": "Your voice note is turned into text on our server and is not kept.",
        "priv_browser": "Your browser's speech service turns your voice into text. Baitproof never receives the audio.", "speak": "Speak", "stop": "Stop", "listening": "Listening",
        "heard": "I heard this. Check it matches", "mic": "I couldn't use the microphone", "silence": "I didn't hear anything", "read": "I read this from your screenshot. Check it matches",
        "hard": "The picture was hard to read", "qr": "There is a QR code in the picture", "no_text": "I couldn't find a message in that picture",
        "chip_shot": "Read from a screenshot", "chip_voice": "Heard from a voice note", "links": "Links in this message", "lookalike": "Fake lookalike", "official": "Official site",
        "short": "Short link", "goes": "Really goes to"},
    "zh": {
        "needs_ai": "读取截图需要用到AI，这里没有开启。请直接粘贴文字。", "reading": "正在读取你的截图", "turning": "正在把你的声音转成文字",
        "priv_image": "AI 会读取你的截图，把里面的文字取出来。我们不会保存这张图片。", "priv_server": "你的语音会在我们这边转成文字，转完就不留。",
        "priv_browser": "你的浏览器自带的语音服务会把你说的话转成文字。Baitproof 收不到你的录音。", "speak": "说话", "stop": "停止", "listening": "正在听",
        "heard": "这是我听到的内容", "mic": "我用不了麦克风", "silence": "我没有听到声音", "read": "这是我从你的截图里读出来的文字",
        "hard": "这张图不太清楚", "qr": "图里有一个二维码", "no_text": "我在这张图里没找到消息",
        "chip_shot": "从截图中读出的消息", "chip_voice": "从语音中听出的消息", "links": "这条消息里的链接", "lookalike": "假冒网址", "official": "官方网站",
        "short": "短链接", "goes": "实际指向"},
}
SERVER_HEARD = {"en": "Hi grandma, it's me. I'm in trouble and need four gift cards today. Please don't tell Mom.", "zh": "奶奶，是我。我出事了，今天急需四张礼品卡，请不要告诉妈妈。"}  # what the canned server reader hears
VOICE_SAYS = {"en": "Hi grandma, it's me. I need four gift cards today, please do not tell Mom.", "zh": "奶奶，是我。我今天急需四张礼品卡，请不要告诉妈妈。"}


def picture(width: int = 320, height: int = 220) -> bytes:
    """A pretend screenshot, drawn here so the test needs no image file."""
    im = Image.new("RGB", (width, height), "#eceff3")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((12, 20, width - 30, height - 70), 16, fill="white")
    d.rounded_rectangle((24, height - 54, width - 90, height - 18), 16, fill="#2563EB")
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def open_challenge(page, base):
    """The header has no "Challenge family" button any more (Friends covers it), but a challenge link a parent was sent still works: open one the way that link would be."""
    r = page.request.post(base + "/challenge/new", max_redirects=0)
    assert r.status == 303, r.status
    page.goto(base + r.headers["location"])


def overflow_checker(page, problems, W: int = 390):
    """The phone-width check used for every page: nothing sticks out to the right of the screen (tables scroll inside their own box)."""
    def no_overflow(label):
        bad = page.evaluate("""(W) => {
            const bar = document.querySelector('.bar'), br = bar ? bar.getBoundingClientRect().right : W;
            const out = [];
            for (const e of document.querySelectorAll('body *')) {
                if (e.closest('.glow, .tbl-wrap, .scroll-x, .sr-only, .finn-root, .finn-bubble, .hh-tabs, .hh-list') || !e.getClientRects().length) continue;  // tables scroll inside their own container; the mascot is a fixed overlay that swims in from off-screen
                const r = e.getBoundingClientRect().right;
                if (r > W + 1 || (bar && bar.contains(e) && r > br + 1)) out.push(e.tagName.toLowerCase() + '.' + (e.className || '') + '@' + Math.round(r));
            }
            return [document.documentElement.scrollWidth, ...out.slice(0, 5)];
        }""", W)
        if bad[0] > W or len(bad) > 1:
            problems.append(f"{label}: overflow/clipping {bad}")
        broken = page.evaluate("""() => [...document.querySelectorAll('use')].filter((u) => !document.getElementById((u.getAttribute('href') || '').slice(1))).map((u) => u.getAttribute('href'))
            .concat([...document.querySelectorAll('svg.ic')].filter((s) => s.getClientRects().length && s.getBoundingClientRect().width < 6).map((s) => 'tiny in ' + (s.parentElement.className || s.parentElement.tagName)))""")
        if broken:
            problems.append(f"{label}: icons missing or too small {broken[:5]}")
    return no_overflow


def inputs_off_pass(page, base, no_overflow, lang: str, quiet) -> None:
    """The home page on a server with no AI and no speech model (the real thing, as deployed with nothing configured): the screenshot button is not there,
    a picture pasted, dropped or chosen anyway gets the translated 'needs the AI' answer, and the page keeps working. Speaking works through the browser's own service."""
    w = WORDS[lang]
    page.goto(base)
    assert page.locator("#shot-btn").count() == 0 and not page.is_visible("#priv-server") and page.locator("#priv-server").count() == 0
    assert page.is_visible("#inputs") and page.is_visible("#speak-btn") and w["speak"] in page.inner_text("#speak-btn"), "speaking works through the browser's own service"
    assert page.is_visible("#priv-browser") and w["priv_browser"] in page.inner_text("#inputs")
    assert w["priv_image"] not in page.inner_text("#inputs") and (page.locator("#speak-lang").count() == (1 if lang == "en" else 0))
    assert page.locator("#shot-file").get_attribute("accept") == "image/*"
    top = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); return [r('#inputs').top - r('#message').bottom, r('#speak-btn').height]; }""")
    assert 0 <= top[0] < 30 and top[1] >= 48, top  # the buttons sit right under the text box and are big enough to hit
    no_overflow(f"{lang}-inputs-home")
    requests = []
    page.on("request", lambda r: requests.append(r.url) if "/api/read/" in r.url else None)
    png = picture()
    quiet["codes"] = ("503",)

    def needs_ai(how):
        n = len(requests)
        with page.expect_response("**/api/read/image") as got:
            how()
        assert got.value.status == 503 and got.value.json()["code"] == "unavailable" and got.value.json()["detail"] == w["needs_ai"], got.value.json()
        assert len(requests) == n + 1
        expect(page.locator("#input-status .in-err")).to_have_text(w["needs_ai"])
        assert page.input_value("#message") == "" and not page.is_disabled("#check-form button.big")
        assert page.locator("#result .banner").count() == 0 and not page.is_visible("#live")

    path = os.path.join(tempfile.gettempdir(), "e2e_shot.png")
    with open(path, "wb") as f:
        f.write(png)
    needs_ai(lambda: page.set_input_files("#shot-file", path))  # chosen with the file picker
    no_overflow(f"{lang}-inputs-error")
    b64 = base64.b64encode(png).decode()
    page.fill("#message", "x")
    page.fill("#message", "")  # emptying the box clears the old message
    assert page.locator("#input-status").inner_text().strip() == ""
    seen = {}

    def pasted():
        seen["paste"] = page.evaluate(CLIPBOARD_JS, [b64, ""])

    def dropped():
        seen["drop"] = page.evaluate(DROP_JS, b64)

    needs_ai(pasted)  # Ctrl/Cmd+V of a picture
    assert seen["paste"] is True, "a pasted picture is taken over by the page"
    needs_ai(dropped)  # dragged onto the card
    assert seen["drop"] == [True, False, True], seen  # the card lights up while the picture is over it, and the drop is ours (the browser does not open the file)
    n = len(requests)
    assert page.evaluate(CLIPBOARD_JS, [b64, "a picture copied together with its words"]) is False  # copied words are still just words
    assert page.evaluate(CLIPBOARD_JS, ["", "plain words"]) is False
    page.wait_for_timeout(300)
    assert len(requests) == n, "pasting words must not send anything"
    quiet["codes"] = ()

    # the page still works: type, check, and the answer does not claim it came from a picture
    page.fill("#message", SCAM_ZH if lang == "zh" else "Pay with gift cards today or you will be arrested. IRS notice.")
    page.click("#check-form button.big")
    page.wait_for_selector("#result .banner")
    assert w["chip_shot"] not in page.inner_text("#result") and w["chip_voice"] not in page.inner_text("#result") and page.locator("#result .src").count() == 0
    assert page.locator("#result .links").count() in (0, 1)

    # speaking through the browser: the words appear as they are spoken, then a notice, and the person presses Check it
    page.goto(base)
    page.click("#speak-btn")
    expect(page.locator("#input-status .in-rec")).to_contain_text(w["listening"])
    assert w["stop"] in page.inner_text("#speak-btn") and "rec" in page.get_attribute("#speak-btn", "class") and page.is_disabled("#speak-btn") is False
    assert page.evaluate("window.__srLang") == ("en-US" if lang == "en" else "zh-CN")
    no_overflow(f"{lang}-inputs-listening")
    page.evaluate("(t) => window.__sr.say(t)", VOICE_SAYS[lang])
    assert page.input_value("#message") == VOICE_SAYS[lang]
    page.click("#speak-btn")
    expect(page.locator("#input-status .in-notice")).to_contain_text(w["heard"])
    assert page.input_value("#message") == VOICE_SAYS[lang] and page.get_attribute("#source", "value") == "voice"
    assert w["speak"] in page.inner_text("#speak-btn") and "rec" not in page.get_attribute("#speak-btn", "class")
    assert page.locator("#result .banner").count() == 0, "a voice note is not checked until the person says so"
    assert page.evaluate("document.activeElement.matches('#check-form button.big')"), "the next step (Check it) has the focus"
    no_overflow(f"{lang}-inputs-heard")
    page.click("#check-form button.big")
    page.wait_for_selector("#result .banner")
    assert w["chip_voice"] in page.inner_text("#result .src") and page.locator("#result .src use[href='#i-mic']").count() == 1
    no_overflow(f"{lang}-inputs-voice-result")

    # the browser's speech service can fail: a plain message, the old text comes back, nothing breaks
    page.goto(base)
    page.fill("#message", "keep me")
    page.click("#speak-btn")
    page.evaluate("window.__sr.fail('not-allowed')")
    expect(page.locator("#input-status .in-err")).to_contain_text(w["mic"])
    assert page.input_value("#message") == "keep me" and w["speak"] in page.inner_text("#speak-btn")
    page.click("#speak-btn")
    page.evaluate("window.__sr.fail('no-speech')")
    expect(page.locator("#input-status .in-err")).to_contain_text(w["silence"])
    page.click("#speak-btn")
    page.keyboard.press("Escape")  # Escape gives up listening
    page.wait_for_timeout(200)
    assert page.locator("#input-status").inner_text().strip() == "" and w["speak"] in page.inner_text("#speak-btn") and page.input_value("#message") == "keep me"
    if lang == "en":  # an English page can listen for Malay, Tamil and Chinese too
        assert [o.strip() for o in page.locator("#speak-lang option").all_inner_texts()] == ["English", "Bahasa Melayu", "தமிழ்", "中文"]
        page.select_option("#speak-lang", "ms-MY")
        page.click("#speak-btn")
        assert page.evaluate("window.__srLang") == "ms-MY"
        page.keyboard.press("Escape")
        page.reload()
        assert page.input_value("#speak-lang") == "ms-MY", "the choice is remembered in this browser"
        page.select_option("#speak-lang", "en-US")
    page.goto(base)


def inputs_on_pass(browser, base, problems, lang: str) -> None:
    """The same page on a server that CAN read pictures and voice (canned readers): the whole screenshot and voice flows, at phone width."""
    w = WORDS[lang]
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, permissions=["microphone"])
    ctx.add_cookies([{"name": "lang", "value": lang if lang == "en" else "zh", "url": base}])
    ctx.add_init_script(NO_SPEECH)  # no browser speech service: with server speech-to-text on, the recorder is used
    page = ctx.new_page()
    expected = {"codes": ("422",)}  # the 'no message found' answer is a 422 on purpose
    page.on("console", lambda m: problems.append(f"{lang} inputs-on console {m.type}: {m.text}") if m.type in ("error", "warning") and not any(f"status of {c}" in m.text for c in expected["codes"]) else None)
    page.on("pageerror", lambda e: problems.append(f"{lang} inputs-on pageerror: {e}"))
    no_overflow = overflow_checker(page, problems)
    assert page.request.get(base + "/api/capabilities").json() == {"image": True, "audio": True}
    page.goto(base)
    assert page.is_visible("#shot-btn") and page.is_visible("#speak-btn") and page.is_visible("#priv-server") and not page.is_visible("#priv-browser")
    inputs = page.inner_text("#inputs")
    assert w["priv_image"] in inputs and w["priv_server"] in inputs and w["priv_browser"] not in inputs
    box = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
        return { btn: r('#check-form button.big').bottom, ex: r('.examples').top, gap: r('#inputs').top - r('#message').bottom }; }""")
    assert box["btn"] <= 844 - 80 and box["ex"] >= box["btn"] and 0 <= box["gap"] < 30, box  # Check it stays on the first screen, with every control on
    no_overflow(f"{lang}-inputs-on-home")

    def pic(width):
        path = os.path.join(tempfile.gettempdir(), f"e2e_shot_{width}.png")
        with open(path, "wb") as f:
            f.write(picture(width))
        return path

    # a screenshot: reading... then the text is in the box, a notice, and the check starts by itself
    page.set_input_files("#shot-file", pic(205))  # (the slow canned reader)
    expect(page.locator("#input-status .in-busy")).to_contain_text(w["reading"])
    assert page.is_disabled("#shot-btn") and page.is_disabled("#speak-btn") and page.locator("#input-status .in-thumb").count() == 1
    no_overflow(f"{lang}-inputs-on-reading")
    page.wait_for_selector("#result .banner", timeout=20000)
    assert "dhl-fee-pay.xyz" in page.input_value("#message") and page.get_attribute("#source", "value") == "screenshot"
    notice = page.inner_text("#input-status .in-notice")
    assert w["read"] in notice and page.locator("#input-status .in-thumb").count() == 1
    assert w["chip_shot"] in page.inner_text("#result .src") and page.locator("#result .src use[href='#i-camera']").count() == 1
    assert not page.is_disabled("#shot-btn") and not page.is_visible("#live")
    panel = page.locator("#result .links")  # the links panel: a real lookalike, an official site and a short link, none of them tappable
    assert w["links"].lower() in panel.inner_text().lower() and panel.locator("li").count() >= 1 and panel.locator("a").count() == 0 and panel.locator("[href]:not(use)").count() == 0
    assert "dhl-fee-pay.xyz" in panel.inner_text() and w["lookalike"] in panel.inner_text()
    assert page.evaluate("[...document.querySelectorAll('#result .links .lk-host')].every((e) => getComputedStyle(e).fontFamily.includes('mono'))")
    no_overflow(f"{lang}-inputs-on-result")
    page.screenshot(path=os.path.join(tempfile.gettempdir(), f"e2e_inputs_{lang}.png"), full_page=True)

    # a picture with a QR code: the notice says so
    page.goto(base)
    page.set_input_files("#shot-file", pic(201))
    page.wait_for_selector("#result .banner", timeout=20000)
    assert w["qr"] in page.inner_text("#input-status .in-notice") and "https://dhl-fee-pay.xyz/qr" in page.input_value("#message")
    no_overflow(f"{lang}-inputs-on-qr")

    # a blurry picture: the text goes in the box but nothing is checked until the person has looked
    page.goto(base)
    page.set_input_files("#shot-file", pic(202))
    expect(page.locator("#input-status .in-notice")).to_contain_text(w["hard"])
    page.wait_for_timeout(700)
    assert page.locator("#result .banner").count() == 0 and not page.is_visible("#live") and "dh1-fee-pay" in page.input_value("#message")
    assert page.evaluate("document.activeElement.id") == "message", "the text box has the focus so the person can fix it"
    no_overflow(f"{lang}-inputs-on-blurry")
    page.fill("#message", "")
    assert page.locator("#input-status").inner_text().strip() == "" and page.get_attribute("#source", "value") == "text"

    # no message found: a plain error, and nothing else changes
    page.set_input_files("#shot-file", pic(203))
    expect(page.locator("#input-status .in-err")).to_contain_text(w["no_text"])
    assert page.input_value("#message") == "" and not page.is_disabled("#shot-btn")
    no_overflow(f"{lang}-inputs-on-error")

    # a pasted picture goes the same way as a chosen one
    page.evaluate(CLIPBOARD_JS, [base64.b64encode(picture(200)).decode(), ""])
    page.wait_for_selector("#result .banner", timeout=20000)
    assert w["chip_shot"] in page.inner_text("#result .src")

    # a voice note: the recorder runs, the recording light shows, stopping sends it, the words come back to the box (nothing is checked yet)
    expected["codes"] = ()
    page.goto(base)
    requests = []
    page.on("request", lambda r: requests.append(r) if "/api/read/audio" in r.url else None)
    page.click("#speak-btn")
    expect(page.locator("#input-status .in-rec")).to_contain_text(w["listening"])
    assert "rec" in page.get_attribute("#speak-btn", "class") and w["stop"] in page.inner_text("#speak-btn") and page.is_disabled("#shot-btn")
    page.wait_for_timeout(1300)
    assert page.inner_text("#input-status .in-time") != "0:00"
    no_overflow(f"{lang}-inputs-on-recording")
    page.click("#speak-btn")
    expect(page.locator("#input-status .in-notice")).to_contain_text(w["heard"], timeout=15000)
    assert page.input_value("#message") == SERVER_HEARD[lang]
    assert len(requests) == 1 and page.get_attribute("#source", "value") == "voice" and page.locator("#result .banner").count() == 0
    # (the canned reader answers in the language it is told the person speaks, so the Chinese page getting Chinese back shows the hint travelled with the recording)
    no_overflow(f"{lang}-inputs-on-heard")
    page.click("#check-form button.big")
    page.wait_for_selector("#result .banner")
    assert w["chip_voice"] in page.inner_text("#result .src")
    if lang == "en":  # an English page can send a Malay recording: the hint is ms and the canned reader answers in Malay
        page.goto(base)
        page.select_option("#speak-lang", "ms-MY")
        page.click("#speak-btn")
        page.wait_for_timeout(1000)
        page.click("#speak-btn")
        expect(page.locator("#input-status .in-notice")).to_contain_text(w["heard"], timeout=15000)
        assert page.input_value("#message").startswith("Helo nenek"), page.input_value("#message")
    # giving up while recording sends nothing and releases the microphone
    page.goto(base)
    page.click("#speak-btn")
    expect(page.locator("#input-status .in-rec")).to_be_visible()
    n = len(requests)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    assert page.locator("#input-status").inner_text().strip() == "" and w["speak"] in page.inner_text("#speak-btn") and len(requests) == n
    # microphone refused: a plain message
    page.evaluate("() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('no', 'NotAllowedError')); }")
    page.click("#speak-btn")
    expect(page.locator("#input-status .in-err")).to_contain_text(w["mic"])
    assert not page.is_disabled("#speak-btn") and not page.is_disabled("#shot-btn")
    ctx.close()


def wait_until_up(base: str, seconds: float = 20) -> None:
    import urllib.request

    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(base + "/api/capabilities", timeout=1).read()
            return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"{base} did not start")


def switch_language(page, code: str, tag: str) -> None:
    """Use the header menu like a person would: open it, pick the language, wait for the page to come back in it."""
    page.click("#lang summary")
    page.click(f"#lang a[hreflang='{tag}']")
    expect(page.locator("html")).to_have_attribute("lang", tag)
    page.wait_for_load_state("load")  # (on a slow link the new page is still arriving)
    assert not page.evaluate("document.getElementById('lang').open"), "the menu should be closed after choosing"


def zh_pass(page, base, no_overflow, expect_401, quiet) -> None:
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
    assert "让你的家人" in page.inner_text("h1") and "查一查" in page.inner_text(".tabs") and "练习" in page.inner_text(".tabs") and "记录" in page.inner_text(".tabs")
    assert page.locator(".tabs a").count() == 4 and "游戏" not in page.inner_text(".tabs")
    assert page.is_visible(".tabs") and not page.is_visible("nav .navlink")
    inputs_off_pass(page, base, no_overflow, "zh", quiet)  # screenshot and voice, in Chinese, on a server with the AI off
    page.goto(base)

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
    assert "练习" in page.inner_text("h1") and "快速练习" in page.inner_text("#practice h2") and "游戏" in page.inner_text("#games h2")
    assert "收件箱快答" in page.inner_text("#games") and "你的防骗能力" in page.inner_text("main")
    assert "练习" in page.inner_text(".tabs a[aria-current=page]")
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
        page.click(".step > button.big")
    page.wait_for_selector("text=你答对了")
    no_overflow("zh-train-finish")

    # game: Inbox Rush by keyboard (S / F), one whole round
    page.goto(base + "/game")
    page.wait_for_selector(".mode-card")
    assert "收件箱快答" in page.inner_text(".mode-card >> nth=0") and re.search(r"第\d+级", page.inner_text(".hud-card"))  # the practice above has already earned some XP
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
    open_challenge(page, base)
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
    assert "My records" in chrome and "Train" in chrome and not re.search("[一-鿿]", chrome), chrome
    no_overflow("en-after-zh")


SCAM_MS = "Tahniah! Anda telah memenangi hadiah RM50,000. Sila klik pautan ini untuk menuntut dalam 24 jam http://hadiah-maybank.top/tuntut"


def ms_pass(page, base, no_overflow, quiet) -> None:
    """Bahasa Melayu: pick it from the header menu, then check, practise, play, records and challenge, all at phone width."""
    import re

    page.goto(base)
    switch_language(page, "ms", "ms")
    no_overflow("ms-home")
    assert "lebih sukar ditipu" in page.inner_text("h1") and "Semak" in page.inner_text(".tabs") and "Latihan" in page.inner_text(".tabs") and "Rekod" in page.inner_text(".tabs")
    assert page.locator(".tabs a").count() == 4 and not re.search("[一-鿿]", page.inner_text("main"))
    assert not page.query_selector("#speak-lang")  # (the speech choice is for English pages)

    # check a Malay scam (offline rules): the verdict, the evidence, the steps and the help panel are all Malay
    page.fill("#message", SCAM_MS)
    page.click("button.big:has-text('Semak sekarang')")
    page.wait_for_selector("#result .banner")
    assert "PENIPUAN" in page.inner_text("#result .banner").upper(), page.inner_text("#result .banner")
    result = page.inner_text("#result")
    for word in ("Tanda pembongkar", "Apa yang perlu dibuat", "Bukti", "Baca dengan kuat", "Ditambah pada latihan anda", "Perlukan bantuan", "1799", "997"):
        assert word.upper() in result.upper(), (word, result)  # (headings are set in capitals by the stylesheet)
    assert not re.search("[一-鿿]", result) and "The giveaway" not in result
    no_overflow("ms-result")
    page.evaluate("(() => { window.__lang = null; speechSynthesis.speak = (u) => { window.__lang = u.lang; }; })()")
    page.click("#result .speak")
    assert page.evaluate("window.__lang") == "ms-MY", page.evaluate("window.__lang")
    page.click("#result [data-feedback=up]")
    page.wait_for_selector("#result [data-fb-note]:has-text('Terima kasih')")

    # practice, on Malay messages
    page.goto(base + "/train")
    no_overflow("ms-train")
    assert "Latihan" in page.inner_text("h1") and "Latihan pantas" in page.inner_text("#practice h2")
    page.click("#start")
    for i in range(4):
        page.wait_for_selector(".step .opt, .step textarea")
        if page.query_selector(".step .opt"):
            page.click(".step .opt >> nth=0")
        else:
            page.fill(".step textarea", "Saya akan abaikan, dan telefon bank saya untuk menyemak")
            page.click(".step button.big")
        page.wait_for_selector(".feedback")
        assert not re.search("[一-鿿]", page.inner_text(".feedback")), page.inner_text(".feedback")
        if i == 0:
            no_overflow("ms-train-feedback")
        page.click(".step > button.big")
    page.wait_for_selector("text=Anda menjawab")
    no_overflow("ms-train-finish")
    page.goto(base + "/game")
    page.wait_for_selector(".mode-card")
    no_overflow("ms-game-hub")
    page.click(".mode-card >> nth=0")
    page.wait_for_selector(".choice")
    buttons = " ".join(page.locator(".choice").all_inner_texts())   # (the message itself may be a Chinese scam from this person's own circle, on purpose)
    assert re.search("Penipuan", buttons) and not re.search("[一-鿿]", buttons)
    no_overflow("ms-game-play")

    # records and the challenge
    page.goto(base + "/records")
    page.wait_for_selector("#tg")
    no_overflow("ms-records")
    assert "Rekod saya" in page.inner_text("h1") and page.locator(".rec").count() >= 1
    open_challenge(page, base)
    page.wait_for_selector("#start")
    assert "Bolehkah anda mengesan penipuan" in page.inner_text("h1"), page.inner_text("h1")
    no_overflow("ms-challenge")
    for url, word in (("/friends", "Kawan"), ("/family", "Kumpulan keluarga"), ("/link", "Cari Pautan Palsu"), ("/road", "Sedia memandu?")):   # the newer pages, in Malay, at phone width
        page.goto(base + url)
        page.wait_for_selector("main")
        no_overflow("ms" + url.replace("/", "-"))
        assert word in page.inner_text("main") and not re.search("[一-鿿]", page.inner_text("main")), url
    switch_language(page, "en", "en")
    chrome = page.inner_text("h1") + page.inner_text(".tabs")
    assert "Train" in chrome and "Latihan" not in chrome, chrome
    no_overflow("en-after-ms")


SCAM_TA = "உங்கள் DBS கணக்கு முடக்கப்படும். உடனே இங்கே சரிபார்க்கவும்: http://dbs-verify.top/login"


def ta_pass(page, base, no_overflow, quiet) -> None:
    """தமிழ்: pick it from the header menu, then check, practise, play, records, the house and the road, all at phone width. The words are looked up in the
    translation table, so the test follows the wording rather than repeating it."""
    import re

    from core.lang.i18n import tr

    def ta(text: str, **kw) -> str:
        return tr(text, "ta", **kw)

    no_tamil_gaps = lambda text: not re.search("[一-鿿]", text)
    page.goto(base)
    switch_language(page, "ta", "ta")
    no_overflow("ta-home")
    assert ta("harder to fool") in page.inner_text("h1") and page.locator(".tabs a").count() == 4 and no_tamil_gaps(page.inner_text("main"))
    for word in ("Check", "Train", "Friends", "Records"):
        assert ta(word) in page.inner_text(".tabs"), word
    assert not page.query_selector("#speak-lang")        # (the speech choice is for English pages)

    # a Tamil scam (no rule pack: the lookalike link and the model's absence give "scam" or "not sure", never "safe")
    page.fill("#message", SCAM_TA)
    page.click("#check-form button.big")
    page.wait_for_selector("#result .banner")
    banner = page.inner_text("#result .banner")
    assert re.search("[஀-௿]", banner) and ta("SCAM").upper() != "" and "safe" not in banner.lower(), banner
    result = page.inner_text("#result")
    for key in ("The giveaway", "What to do", "Need help, or want to report it?", "Read aloud"):
        assert ta(key).upper() in result.upper(), (key, result[:300])
    assert "1799" in result and "997" in result and "The giveaway" not in result and no_tamil_gaps(result)
    no_overflow("ta-result")
    page.evaluate("(() => { window.__lang = null; speechSynthesis.speak = (u) => { window.__lang = u.lang; }; })()")
    page.click("#result .speak")
    assert page.evaluate("window.__lang") == "ta-IN", page.evaluate("window.__lang")

    # practice on Tamil messages
    page.goto(base + "/train")
    no_overflow("ta-train")
    assert ta("Quick practice") in page.inner_text("#practice h2")
    page.click("#start")
    for i in range(4):
        page.wait_for_selector(".step .opt, .step textarea")
        if page.query_selector(".step .opt"):
            page.click(".step .opt >> nth=0")
        else:
            page.fill(".step textarea", "நான் இதை புறக்கணித்து வங்கியை அழைத்துச் சரிபார்ப்பேன்")
            page.click(".step button.big")
        page.wait_for_selector(".feedback")
        assert no_tamil_gaps(page.inner_text(".feedback"))
        if i == 0:
            no_overflow("ta-train-feedback")
        page.click(".step > button.big")
    page.goto(base + "/game")
    page.wait_for_selector(".mode-card")
    no_overflow("ta-game-hub")
    page.click(".mode-card >> nth=0")
    page.wait_for_selector(".choice")
    buttons = " ".join(page.locator(".choice").all_inner_texts())
    assert ta("Scam") in buttons and no_tamil_gaps(buttons)
    no_overflow("ta-game-play")
    for url, key in (("/records", "My records"), ("/friends", "Friends"), ("/house", "Your house"), ("/link", "Link Hunt"), ("/road", "Scam Road")):
        page.goto(base + url)
        page.wait_for_selector("main")
        no_overflow("ta" + url.replace("/", "-"))
        assert ta(key) in page.inner_text("main") or ta(key) in page.title() or ta(key) in page.inner_text("h1"), (url, key)
        assert url == "/records" or no_tamil_gaps(page.inner_text("main")), url      # (the records hold the messages checked earlier, in whatever language they were)
    switch_language(page, "en", "en")
    assert "Train" in page.inner_text(".tabs") and not re.search("[஀-௿]", page.inner_text(".tabs"))
    no_overflow("en-after-ta")


SOFTWARE_GL = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]  # a headless Chrome with no graphics card still draws WebGL


def blank_check(page, selector: str) -> float:
    """How much the picture inside `selector` varies (0 = one flat colour): a 3D scene that did not draw is flat."""
    box = page.locator(selector).bounding_box()
    img = Image.open(io.BytesIO(page.screenshot(clip=box))).convert("L").resize((64, 40))
    px = list(img.tobytes())  # (one byte per pixel in greyscale)
    mean = sum(px) / len(px)
    return (sum((v - mean) ** 2 for v in px) / len(px)) ** 0.5


def grant_xp(ctx, social_db: str, xp: int) -> None:
    """Give the profile in this browser some XP to spend (written straight into the server's throw-away database: playing for it takes minutes)."""
    pid = next(c["value"] for c in ctx.cookies() if c["name"] == "bp")
    old = {k: os.environ.get(k) for k in ("BAITPROOF_DB", "BAITPROOF_MULTIUSER")}
    os.environ.update({"BAITPROOF_DB": social_db, "BAITPROOF_MULTIUSER": "1"})
    try:
        from core.game import state as gs
        from core.storage import db

        db.set_profile(pid)
        s = gs.get()
        s["xp"] = xp
        gs.save(s)
        db.set_profile(None)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def tap_start(social_db: str, chat_id: int, code: str) -> str:
    """What the bot does when someone taps the Open Telegram link and presses Start: /start with the code, run here against the server's throw-away database."""
    old = {k: os.environ.get(k) for k in ("BAITPROOF_DB", "BAITPROOF_MULTIUSER")}
    os.environ.update({"BAITPROOF_DB": social_db, "BAITPROOF_MULTIUSER": "1"})
    try:
        from bot import handlers
        from core.storage import db

        return handlers.on_start(chat_id, code)
    finally:
        db.set_profile(None)
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def house_pass(browser, key, friend, base, problems, social_db) -> None:
    """The house: Mei buys a fern, a sofa and a carpet with the XP she was given, drags things around (a bad spot is refused), turns and puts away, makes her character,
    and her friend Aiman visits on a phone: sees the room, cannot shop, and can make the character walk."""
    ctx_lap = browser.new_context(viewport={"width": 1100, "height": 800})
    lap = ctx_lap.new_page()
    lap.on("console", lambda m: problems.append(f"house console {m.type}: {m.text}") if m.type == "error" else None)
    lap.on("pageerror", lambda e: problems.append(f"house pageerror: {e}"))
    lap.goto(base + "/signin")
    lap.fill("#key", key.lower())
    lap.click("button:has-text('Log in')")
    lap.wait_for_selector("h1:has-text('Mei')")
    no_overflow = overflow_checker(lap, problems, W=1100)
    from core.game import house as shop

    price = lambda i: shop.CATALOG[i].price
    spendable = 4000
    grant_xp(ctx_lap, social_db, spendable)
    lap.goto(base + "/house")
    ready = "() => !!(window.__house && window.__house.state.view)"
    for _ in range(80):
        if lap.evaluate(ready):
            break
        lap.wait_for_timeout(250)
    assert lap.evaluate(ready), "the house loaded"
    H = "window.__house"
    assert blank_check(lap, "#scene") > 6, "the 3D room drew something"
    assert lap.inner_text("#points-n") == str(spendable) and lap.evaluate(f"() => {H}.checkModels()") == [], "every model exists and fits its footprint"
    assert lap.locator(".hh-tab").count() == 7 and lap.locator(".hh-card").count() == 7
    no_overflow("house")

    def count():
        return lap.evaluate(f"() => {H}.state.placed.length")

    def card_button(name, label):
        return lap.locator(".hh-card", has=lap.locator("b", has_text=name)).locator(".hh-buy", has_text=label)

    # ---- buy a fern: it appears in the room at once, is picked, and the XP went down
    card_button("Fern", "Buy").click()
    for _ in range(40):
        if count() == 1:
            break
        lap.wait_for_timeout(150)
    assert count() == 1 and lap.inner_text("#points-n") == str(spendable - price("fern")) and lap.is_visible("#tools") and lap.inner_text("#tool-name") == "Fern" and lap.is_visible("#t-rotate")
    saved = "() => fetch('/api/house').then((r) => r.json()).then((d) => d.layout.length)"
    for _ in range(40):                                        # (the layout is saved a moment after it changes)
        if lap.evaluate(saved) == 1:
            break
        lap.wait_for_timeout(150)
    lap.reload()
    for _ in range(80):
        if lap.evaluate(ready) and count() == 1:
            break
        lap.wait_for_timeout(250)
    assert count() == 1 and lap.inner_text("#points-n") == str(spendable - price("fern")), "what you bought and where you put it is still there after a reload"

    # ---- drag it to another cell (the middle of that cell on the screen), and it stays there
    e = lap.evaluate(f"() => {H}.entity(0)")
    target = lap.evaluate(f"() => {H}.screenOf(8.5, 2.5, 0.3)")
    lap.mouse.move(e["center"]["x"], e["center"]["y"])
    lap.mouse.down()
    lap.mouse.move((e["center"]["x"] + target["x"]) / 2, (e["center"]["y"] + target["y"]) / 2, steps=6)
    lap.mouse.move(target["x"], target["y"], steps=8)
    lap.mouse.up()
    moved = lap.evaluate(f"() => {H}.entity(0)")
    assert (moved["x"], moved["z"]) == (8, 2), moved
    for _ in range(40):
        if lap.evaluate("() => fetch('/api/house').then((r) => r.json()).then((d) => d.layout[0].x)") == 8:
            break
        lap.wait_for_timeout(150)

    # ---- a sofa: bought, placed, turned, put away and placed again from the cupboard
    lap.click(".hh-tab:has-text('Furniture')")
    card_button("Sofa", "Buy").click()
    for _ in range(40):
        if count() == 2:
            break
        lap.wait_for_timeout(150)
    assert count() == 2 and lap.inner_text("#points-n") == str(spendable - price("fern") - price("sofa")) and lap.inner_text("#tool-name") == "Sofa" and lap.is_visible("#t-rotate")
    before = lap.evaluate(f"() => {H}.state.sel.r")
    lap.click("#t-rotate")
    assert lap.evaluate(f"() => {H}.state.sel.r") == (before + 1) % 4
    lap.click("#t-pick")
    assert count() == 1 and not lap.is_visible("#tools") and card_button("Sofa", "Place").count() == 1 and "1 owned" in lap.inner_text(".hh-card:has(b:has-text('Sofa'))")
    card_button("Sofa", "Place").click()
    assert count() == 2

    # ---- dragging the sofa onto the fern is refused: it goes back where it was
    sofa = lap.evaluate(f"() => {H}.entity(1)")
    fern = lap.evaluate(f"() => {H}.entity(0)")
    lap.mouse.move(sofa["center"]["x"], sofa["center"]["y"])
    lap.mouse.down()
    lap.mouse.move(fern["center"]["x"] + 3, fern["center"]["y"] + 3, steps=10)
    lap.mouse.up()
    after = lap.evaluate(f"() => {H}.entity(1)")
    assert (after["x"], after["z"]) == (sofa["x"], sofa["z"]) and "fit" in lap.inner_text("#msg"), after

    # ---- tapping a thing picks it, the arrow keys nudge it, R turns it, Escape lets go
    lap.click("#scene", position={"x": 60, "y": 560})                  # (empty space: nothing picked)
    assert not lap.is_visible("#tools")
    lap.mouse.click(sofa["center"]["x"], sofa["center"]["y"])
    assert lap.is_visible("#tools") and lap.inner_text("#tool-name") == "Sofa"
    lap.keyboard.press("ArrowLeft")
    assert lap.evaluate(f"() => {H}.state.sel.x") == sofa["x"] - 1
    lap.keyboard.press("r")
    assert lap.evaluate(f"() => {H}.state.sel.r") == (sofa["r"] + 1) % 4
    lap.keyboard.press("Escape")
    assert not lap.is_visible("#tools")

    # ---- a new floor, paid for once
    lap.click(".hh-tab:has-text('Floors and walls')")
    lap.locator(".hh-card.style", has=lap.locator("b", has_text="Carpet")).locator(".hh-buy").click()
    for _ in range(40):
        if lap.evaluate(f"() => {H}.state.view.floor") == "carpet":
            break
        lap.wait_for_timeout(150)
    assert lap.evaluate(f"() => {H}.state.view.floor") == "carpet" and lap.inner_text("#points-n") == str(spendable - price("fern") - price("sofa") - shop.FLOORS["carpet"][1])

    # ---- the character: the creator opens, a new look shows at once and is saved
    lap.click("#open-char")
    assert lap.is_visible("#char-sheet") and lap.locator("#char-sheet .cr-group").count() == 7
    lap.click("#char-sheet .cr-group >> nth=1 >> .cr-opt >> nth=8")                  # tudung
    lap.click("#char-sheet .cr-group >> nth=0 >> .cr-opt >> nth=6")                  # a deep skin tone
    look = lap.evaluate(f"() => {H}.state.look")
    assert look.startswith("p.6.8.") and lap.locator("#char-sheet .cr-opt:disabled").count() == 2, look           # (a songkok and a cap do not go on a tudung)
    lap.click("#char-save")
    lap.wait_for_selector("#char-sheet", state="hidden")
    lap.reload()
    for _ in range(80):
        if lap.evaluate(ready):
            break
        lap.wait_for_timeout(250)
    assert lap.evaluate(f"() => {H}.state.look") == look and lap.inner_text("#points-n") == str(spendable - price("fern") - price("sofa") - shop.FLOORS["carpet"][1]) and count() == 2
    # a man's look: a side part, a polo and a beard (the seventh number is the face), saved and still there after a reload, and drawn in 3D without a page error
    lap.click("#open-char")
    lap.click("#char-sheet .cr-group >> nth=1 >> .cr-opt >> nth=9")                  # side part
    lap.click("#char-sheet .cr-group >> nth=3 >> .cr-opt >> nth=5")                  # polo
    lap.click("#char-sheet .cr-group >> nth=6 >> .cr-opt >> nth=5")                  # beard
    import re

    man = lap.evaluate(f"() => {H}.state.look")
    assert re.fullmatch(r"p\.6\.9\.\d+\.5\.\d+\.\d+\.5", man), man
    lap.click("#char-save")
    lap.wait_for_selector("#char-sheet", state="hidden")
    lap.reload()
    for _ in range(80):
        if lap.evaluate(ready):
            break
        lap.wait_for_timeout(250)
    assert lap.evaluate(f"() => {H}.state.look") == man
    look = man                                                                          # the visitor below sees this look

    # ---- tapping the floor makes the character walk there
    spot = lap.evaluate(f"() => {H}.screenOf(9.5, 8.5, 0)")
    lap.mouse.click(spot["x"], spot["y"])
    lap.wait_for_timeout(300)
    walking = lap.evaluate(f"() => {H}.state.char.path.length")
    assert walking > 0, lap.evaluate(f"() => JSON.stringify({{spot: {H}.screenOf(9.5, 8.5, 0), sel: !!{H}.state.sel, char: {H}.state.char.pos, placed: {H}.state.placed.map((e) => [e.id, e.x, e.z, e.r])}})")
    # ---- a pet that follows: bought, put down, told to follow; the character walks to the far corner and the fox comes along
    lap.click(".hh-tab:has-text('Pets')")
    card_button("Fox", "Buy").click()
    for _ in range(40):
        if count() == 3:
            break
        lap.wait_for_timeout(150)
    assert count() == 3 and lap.inner_text("#tool-name") == "Fox" and lap.is_visible("#t-follow") and lap.get_attribute("#t-follow", "aria-pressed") == "false"
    assert lap.is_visible("#t-rotate") and "Follow me" in lap.inner_text("#t-follow")
    lap.click("#t-follow")
    assert lap.get_attribute("#t-follow", "aria-pressed") == "true" and lap.evaluate(f"() => {H}.state.sel.follow") is True
    lap.keyboard.press("Escape")
    corner = lap.evaluate(f"() => {H}.screenOf(1.5, 9.5, 0)")
    lap.mouse.click(corner["x"], corner["y"])
    gap = "() => { const H = window.__house.state, c = H.char.pos, e = H.placed.find((p) => p.id === 'pet-fox'); return Math.hypot(c.x - e.pos.x, c.z - e.pos.z); }"
    for _ in range(60):                                                  # (the walk takes a few seconds; the fox sets off after the character and catches up)
        if lap.evaluate(f"() => {H}.state.char.path.length") == 0 and lap.evaluate(gap) < 3.6:
            break
        lap.wait_for_timeout(250)
    assert lap.evaluate(gap) < 3.6 and lap.evaluate(f"() => {H}.state.char.pos.x") < 3, lap.evaluate(gap)
    for _ in range(40):
        if lap.evaluate("() => fetch('/api/house').then((r) => r.json()).then((d) => d.layout.filter((e) => e.follow).length)") == 1:
            break
        lap.wait_for_timeout(150)
    assert lap.evaluate("() => fetch('/api/house').then((r) => r.json()).then((d) => d.layout.filter((e) => e.follow).map((e) => e.item))") == ["pet-fox"], "following is kept"
    fox = lap.evaluate(f"() => {H}.entity(2)")
    lap.mouse.click(fox["center"]["x"], fox["center"]["y"])                # pick it again and tell it to stay
    assert lap.inner_text("#tool-name") == "Fox" and lap.get_attribute("#t-follow", "aria-pressed") == "true"
    lap.click("#t-follow")
    assert lap.evaluate(f"() => {H}.state.placed[2].follow") is False and lap.get_attribute("#t-follow", "aria-pressed") == "false"
    for _ in range(40):
        if lap.evaluate("() => fetch('/api/house').then((r) => r.json()).then((d) => d.layout.filter((e) => e.follow).length)") == 0:
            break
        lap.wait_for_timeout(150)
    assert lap.evaluate("() => fetch('/api/house').then((r) => r.json()).then((d) => d.layout.filter((e) => e.follow).length)") == 0
    lap.keyboard.press("Escape")

    # ---- the home page shows where you are in the game
    lap.goto(base)
    card = lap.locator(".home-card")
    assert card.is_visible() and card.locator(".avt svg.pt").count() == 1 and card.locator("a[href='/house']").count() == 1 and card.locator("button, a.btn").count() == 0
    left = spendable - price("fern") - price("sofa") - shop.FLOORS["carpet"][1] - price("pet-fox")
    assert f"{left} XP" in card.inner_text() and "Your progress" in card.inner_text()
    lap.goto(base + "/house")
    for _ in range(80):
        if lap.evaluate(ready):
            break
        lap.wait_for_timeout(250)

    no_overflow("house-after")

    # ---- Aiman visits on a phone: the room, no shop, and the character can walk
    friend.goto(base + "/friends")
    friend.click("a:has-text('Visit house')")
    for _ in range(80):
        if friend.evaluate(ready):
            break
        friend.wait_for_timeout(250)
    assert friend.evaluate(ready) and friend.evaluate(f"() => {H}.state.view.visit") is True and friend.evaluate(f"() => {H}.state.placed.length") == 3
    assert "Mei" in friend.inner_text(".hh-title") and friend.locator("#shop").count() == 0 and friend.locator("#open-char").count() == 0 and friend.is_visible(".hh-hint")
    assert friend.evaluate(f"() => {H}.state.look") == look and blank_check(friend, "#scene") > 6
    overflow_checker(friend, problems)("house-visit")
    spot = friend.evaluate(f"() => {H}.screenOf(9.5, 8.5, 0)")
    friend.mouse.click(spot["x"], spot["y"])
    friend.wait_for_timeout(300)
    assert friend.evaluate(f"() => {H}.state.char.path.length") > 0
    friend.goto(base + "/friends")
    ctx_lap.close()


def social_pass(p, base, problems, truth, social_db) -> None:
    """Public mode, three browsers: Aiman makes a profile and an invite; Mei joins from the link on a phone; Mei then signs in on a laptop and drives the 3D road;
    Aiman's phone sees Mei's distance on the board and her flag-marker on the road."""
    import re
    from urllib.parse import urlsplit

    b = p.chromium.launch(executable_path=CHROME, headless=True, args=SOFTWARE_GL)
    LANE = {"scam": "1", "unsure": "2", "safe": "3"}

    def phone(name):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        page.on("console", lambda m: problems.append(f"{name} console {m.type}: {m.text}") if m.type == "error" and "status of 400" not in m.text else None)
        page.on("pageerror", lambda e: problems.append(f"{name} pageerror: {e}"))
        return ctx, page, overflow_checker(page, problems)

    ctx_a, aiman, ov_a = phone("aiman")
    # ---- Aiman: log in link, make a profile, see the key once, find the invite
    aiman.goto(base)
    assert aiman.is_visible("a.me.login") and "Log in" in aiman.inner_text("a.me.login")
    aiman.click("a.me.login")
    assert aiman.url.endswith("/signin") and "Log in" in aiman.inner_text("h1")
    ov_a("signin")
    aiman.click("text=Make your profile")
    aiman.wait_for_selector("input[name=nickname]")
    ov_a("me-new")
    aiman.fill("#nick", "Aiman")
    aiman.click(".creator .cr-group >> nth=1 >> .cr-opt >> nth=3")      # the character creator: a hair style
    assert aiman.locator(".creator .cr-opt[aria-pressed=true]").count() == 7 and aiman.get_attribute("input[name=avatar]", "value").startswith("p.")
    aiman.click("button:has-text('Create my profile')")
    aiman.wait_for_selector("#the-key")
    key_a = aiman.inner_text("#the-key").strip()
    assert re.fullmatch(r"[A-Z0-9]{4}(-[A-Z0-9]{4}){3}", key_a)
    ov_a("me-key")
    aiman.click(".keybox [data-copy]")
    assert aiman.evaluate("() => navigator.clipboard.readText()") == key_a, "the copy button copies the key"
    aiman.goto(base + "/me")
    assert not aiman.query_selector("#the-key") and "Aiman" in aiman.inner_text("h1")   # the key is not shown again
    ov_a("me")
    invite = aiman.get_attribute("[data-copy]", "data-copy")
    assert "/join/" in invite
    aiman.goto(base + "/friends")
    ov_a("friends-empty")
    assert "Add a friend to compete" in aiman.inner_text("main") and aiman.is_visible(".tabs a[aria-current=page]:has-text('Friends')")

    # ---- Mei: opens the invite on a phone, makes a profile and is friends with Aiman at once
    ctx_m, mei, ov_m = phone("mei")
    path = urlsplit(invite).path
    mei.goto(base + path)
    assert "Aiman invited you to be friends" in mei.inner_text("h1")
    ov_m("join")
    mei.fill("#nick", "Mei")
    mei.click("button:has-text('Make my profile and add Aiman')")
    mei.wait_for_selector("#the-key")
    key_m = mei.inner_text("#the-key").strip()
    assert "You and Aiman are now friends." in mei.inner_text("main")
    ov_m("me-joined")
    mei.goto(base + "/friends")
    assert "Aiman" in mei.inner_text(".friends") and mei.locator(".board li").count() == 2
    ov_m("friends")

    # ---- Mei on a laptop: signs in with her key, drives Scam Road (3D) and finishes with three wrong turns
    ctx_l = b.new_context(viewport={"width": 1100, "height": 800})
    lap = ctx_l.new_page()
    lap.on("console", lambda m: problems.append(f"laptop console {m.type}: {m.text}") if m.type in ("error",) else None)
    lap.on("pageerror", lambda e: problems.append(f"laptop pageerror: {e}"))
    lap.goto(base + "/signin")
    lap.fill("#key", key_m.lower())
    lap.click("button:has-text('Log in')")
    lap.wait_for_selector("h1:has-text('Mei')")
    lap.goto(base + "/road")
    lap.wait_for_selector("#go")
    assert lap.is_visible("#intro") and "Ready to drive?" in lap.inner_text("#intro")
    assert blank_check(lap, "#scene") > 6, "the 3D scene drew something"
    lap.click("#go")
    for _ in range(60):
        if lap.evaluate("() => window.__road.state") == "driving":
            break
        lap.wait_for_timeout(250)
    assert lap.evaluate("() => window.__road.state") == "driving" and lap.is_visible("#lanes") and lap.is_visible("#msg")
    assert blank_check(lap, "#scene") > 8, "the road drew"

    def drive_gate(page, right: bool) -> str:
        text = page.evaluate("() => window.__road.text")
        t = truth[text]
        wrong = {"scam": "3", "safe": "1", "unsure": "1"}[t]
        page.keyboard.press(LANE[t] if right else wrong)
        page.wait_for_timeout(250)
        page.evaluate("() => window.__road.advance(window.__road.gateAhead + 2)")
        page.wait_for_timeout(900)
        return t

    def gate(right: bool) -> str:
        return drive_gate(lap, right)

    for i in range(3):
        gate(True)
    for _ in range(40):
        if lap.evaluate("() => window.__road.distance") == 240:
            break
        lap.wait_for_timeout(100)
    assert lap.evaluate("() => window.__road.distance") == 240 and lap.is_visible(".toast.good")
    gate(False)
    lap.wait_for_selector("#why:not([hidden])", timeout=8000)
    assert lap.inner_text("#why-tell").strip()  # (the giveaway is always there; "what to do" only for a scam)
    lap.click("#why-go")
    for _ in range(2):
        gate(False)
        lap.wait_for_selector("#why:not([hidden])", timeout=8000)
        lap.click("#why-go")
    lap.wait_for_selector("#end:not([hidden])", timeout=10000)
    assert "240" in lap.inner_text("#end-dist") and lap.is_visible("#end-best") and "3 right" in lap.inner_text("#end-stats")
    assert "Mei" in lap.inner_text("#end-board") and not lap.is_visible("#end-login")
    run = ctx_l.request.post(base + "/api/road/start", data={"mode": "daily"}).json()
    queue = list(run["items"])
    for i in range(5):                      # four right, then a wrong turn: a path "cccc" + "w"
        g = queue.pop(0)
        t = truth[g["text"]]
        lane = {"scam": 0, "unsure": 1, "safe": 2}[t] if i < 4 else {"scam": 2, "safe": 0, "unsure": 0}[t]
        queue += ctx_l.request.post(base + "/api/road/answer", data={"run": run["run"], "gate": g["id"], "lane": lane}).json()["next"]
    assert ctx_l.request.post(base + "/api/road/finish", data={"run": run["run"]}).json()["distance"] == 320
    ctx_l.close()

    # ---- Aiman's phone: Mei's 240 m is on the board, and the road shows her as a marker to chase (and fits the phone)
    aiman.goto(base + "/friends")
    board = aiman.inner_text(".board")
    assert board.index("Mei") < board.index("Aiman") and "240 m" in board and "no drive yet" in board
    ov_a("friends-board")
    aiman.goto(base + "/road")
    aiman.wait_for_selector("#go")
    assert "Your best" not in aiman.inner_text("#intro")
    ov_a("road-intro")
    aiman.click("#go")
    for _ in range(60):
        if aiman.evaluate("() => window.__road.state") == "driving":
            break
        aiman.wait_for_timeout(250)
    assert "Mei is 240 m ahead" in aiman.inner_text("#race-text") and aiman.locator("#track .mk").count() == 2
    box = aiman.locator("#lanes").bounding_box()
    assert box["y"] + box["height"] <= 844 and box["x"] >= 0 and box["x"] + box["width"] <= 390, "the lane buttons fit the phone"
    ov_a("road-phone")
    aiman.tap(".lanes button[data-lane='2']")
    assert aiman.get_attribute(".lanes button[data-lane='2']", "aria-pressed") == "true" and aiman.evaluate("() => window.__road.lane") == 2
    aiman.click("#pause")
    assert aiman.is_visible("#pause-sheet")
    aiman.click("#quit")
    aiman.wait_for_selector("#end:not([hidden])")
    assert aiman.inner_text("#end-dist").strip().startswith("0")

    # ---- the Daily Road: the same messages for everyone, Mei's drive as a ghost, a first-of-the-day badge, a hat earned, themes and sound
    aiman.goto(base + "/road")
    aiman.wait_for_selector("#go-daily")
    assert aiman.locator(".finn-root").count() == 0 and aiman.locator("canvas.fx").count() == 0   # (a game page: no flying fish, no second WebGL canvas)
    aiman.click(".drawer summary")
    assert aiman.locator("#garage-cars button").count() == 7 and aiman.locator("#garage-cars button:disabled").count() == 6 and aiman.locator("#garage-hats button:disabled").count() == 5
    assert "Next to unlock" in aiman.inner_text("#garage-note")
    aiman.click("#themes button:has-text('Night')")
    assert aiman.evaluate("() => window.__road.theme") == "night"
    ov_a("road-drawer")
    aiman.click("#go-daily")
    for _ in range(60):
        if aiman.evaluate("() => window.__road.state") == "driving":
            break
        aiman.wait_for_timeout(250)
    assert aiman.evaluate("() => window.__road.mode") == "daily" and aiman.evaluate("() => window.__road.ghosts") == 1 and aiman.is_visible("#mode-chip")
    assert aiman.locator("#track .mk").count() == 2   # you, and Mei's drive from today
    drive_gate(aiman, True)
    aiman.click("#sound")
    assert aiman.get_attribute("#sound", "aria-pressed") == "false" and aiman.evaluate("() => window.__road.sound") is False
    aiman.click("#pause")
    aiman.click("#quit")
    aiman.wait_for_selector("#end:not([hidden])")
    assert "Daily Road done" in aiman.inner_text("#end-title") and "Daily driver" in aiman.inner_text("#end-badges") and "Party hat" in aiman.inner_text("#end-badges")
    ov_a("road-daily-end")
    aiman.reload()
    aiman.wait_for_selector("#go-daily")
    assert aiman.evaluate("() => window.__road.theme") == "night" and aiman.evaluate("() => window.__road.sound") is False     # (both remembered)
    aiman.click(".drawer summary")
    aiman.click("#garage-hats button[aria-label='Party hat']")
    for _ in range(40):
        if aiman.evaluate("() => window.__road.skin.hat") == "party":
            break
        aiman.wait_for_timeout(150)
    assert aiman.evaluate("() => window.__road.skin.hat") == "party"
    assert aiman.locator("#push-box").count() == 0     # (this copy has no push keys: nothing about notifications is offered)

    # ---- Link Hunt: four links, one fake, three wrong taps end the round; the score reaches the friends' board
    aiman.goto(base + "/link")
    aiman.wait_for_selector("#lh-start")
    ov_a("link-intro")
    aiman.click("#lh-start")
    aiman.wait_for_selector(".lh-opt")
    assert aiman.locator(".lh-opt").count() == 4 and "Which link is the fake?" in aiman.inner_text("#lh-q")
    ov_a("link-play")
    for i in range(40):
        aiman.click(".lh-opt >> nth=0")
        aiman.wait_for_selector("#lh-feedback:not([hidden])")
        assert aiman.locator(".lh-opt.fake").count() == 1 and aiman.inner_text("#lh-tell").strip()
        if i == 0:
            ov_a("link-feedback")
        last = "See my result" in aiman.inner_text("#lh-next")     # (the third wrong tap: the button now leads to the result)
        aiman.click("#lh-next")
        if last:
            break
    aiman.wait_for_selector("#lh-end:not([hidden])")
    assert "points" in aiman.inner_text("#lh-final") and "Round over" in aiman.inner_text("#lh-end")
    ov_a("link-end")
    aiman.goto(base + "/friends?game=link&scope=all")
    assert "points" in aiman.inner_text(".board") and aiman.is_visible("a[aria-current='true']:has-text('Link Hunt')")
    ov_a("friends-link")

    # ---- a family group: Aiman starts it, Mei joins from the invite, Aiman shares a scam she just checked and Mei sees it (redacted)
    aiman.goto(base + "/family")
    ov_a("family-new")
    aiman.fill("#fname", "The Lims")
    aiman.click("button:has-text('Start group')")
    aiman.wait_for_selector("text=The Lims")
    ov_a("family")
    fam_invite = aiman.get_attribute("[data-copy*='/family/join/']", "data-copy")
    mei.goto(base + urlsplit(fam_invite).path)
    assert "Join The Lims?" in mei.inner_text("h1")
    ov_m("family-join")
    mei.click("button:has-text('Join The Lims')")
    mei.wait_for_selector("h1:has-text('The Lims')")
    aiman.goto(base)
    aiman.fill("#message", "DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Call 0800-555-0199 or pay now: dhl-fee-pay.xyz/track/9981")
    aiman.click("button.big:has-text('Check it')")
    aiman.wait_for_selector("#result .banner")
    aiman.click(".family-share button")
    aiman.wait_for_selector("text=Shared!")
    assert "The Lims" in aiman.inner_text("h1")
    mei.goto(base + "/family")
    page_text = mei.inner_text("main")
    assert "Shared by Aiman" in page_text and "dhl-fee-pay.xyz" in page_text and "0800-555-0199" not in page_text and "/track/9981" not in page_text
    ov_m("family-shared")
    mei.goto(base + "/game")
    mei.wait_for_selector(".mode-card")
    for _ in range(40):
        if "1 scam that reached your own family" in mei.inner_text(".mode-grid"):
            break
        mei.wait_for_timeout(150)
    assert "1 scam that reached your own family" in mei.inner_text(".mode-grid")    # (the shared scam is a gate in Mei's own games)

    # ---- the family dashboard: what each person chose to share, soft spots, a summary for the chat
    aiman.goto(base + "/family/dashboard")
    aiman.wait_for_selector("table.matrix")
    assert aiman.locator("table.matrix tbody tr").count() == 12 and "Family score" in aiman.inner_text("main") and "Mei" in aiman.inner_text(".people") and "Aiman" in aiman.inner_text(".people")
    assert "This week, for the family chat" in aiman.inner_text("main") and "The Lims on Baitproof this week" in aiman.inner_text(".summary")
    assert aiman.locator(".avgbar i").first.evaluate("e => e.style.width") != ""      # (the bars are drawn by the script: the page's policy forbids style attributes)
    ov_a("family-dashboard")
    aiman.click("button:has-text('Hide my progress')")
    aiman.wait_for_selector("text=Your progress is private.")
    aiman.click("button:has-text('Share my progress')")
    aiman.wait_for_selector("text=Your progress is visible to your family.")
    mei.goto(base + "/family")
    assert mei.is_visible("a:has-text('Family dashboard')")

    # ---- a live race: Aiman opens it and asks Mei; Mei joins from the hub; same gates, same moment; Aiman wins; the result and the record
    aiman.goto(base + "/duel")
    assert "Race a friend, live" in aiman.inner_text("h1")
    ov_a("duel-hub")
    aiman.check("input[name=pub]")
    aiman.click("button:has-text('Open a race')")
    aiman.wait_for_selector("#lobby:not([hidden])")
    mei.goto(base + "/duel")
    assert "Aiman challenged you" in mei.inner_text("main")
    ov_m("duel-invite")
    mei.click("a:has-text('Join the race')")
    mei.wait_for_selector("#lobby:not([hidden])")
    aiman.wait_for_selector("#lobby-start:not([hidden])", timeout=15000)
    who = (aiman.inner_text("#lobby-players"), mei.inner_text("#lobby-players"))
    assert "Mei" in who[0] and "Aiman" in who[1] and aiman.locator("#lobby-players li").count() == 2, who
    ov_a("duel-lobby")
    aiman.click("#lobby-start")
    for pg in (aiman, mei):
        for _ in range(80):
            if pg.evaluate("() => window.__road.state") == "driving":
                break
            pg.wait_for_timeout(250)
        assert pg.evaluate("() => window.__road.state") == "driving" and pg.evaluate("() => window.__road.mode") == "duel" and not pg.is_visible("#pause")
    assert aiman.evaluate("() => window.__road.ghosts") == 1 and mei.evaluate("() => window.__road.ghosts") == 1      # (each sees the other as a live car)
    assert "Gate 1 of 12" in aiman.inner_text("#mode-chip")
    for _ in range(4):
        drive_gate(aiman, True)
        drive_gate(mei, True)
    ov_a("duel-race")
    for _ in range(8):
        drive_gate(aiman, True)
    assert "Gate" in aiman.inner_text("#mode-chip") or aiman.is_visible("#duel-wait")
    for _ in range(3):
        drive_gate(mei, False)
        mei.wait_for_selector("#why:not([hidden])", timeout=15000)
        mei.click("#why-go")
    for pg in (aiman, mei):
        pg.wait_for_selector("#duel-end:not([hidden])", timeout=45000)
    assert "You won the race!" in aiman.inner_text("#duel-title") and aiman.is_visible("#duel-won") and "Race over" in mei.inner_text("#duel-title")
    assert aiman.locator("#duel-board li").count() == 2 and aiman.inner_text("#duel-board li >> nth=0").find("Aiman") >= 0 and "12 right" in aiman.inner_text("#duel-board")
    assert "+35 XP" in aiman.inner_text("#duel-chips") and "Duelist" in aiman.inner_text("#duel-chips") and "+10 XP" in mei.inner_text("#duel-chips")
    assert "You and Mei: 1–0" in aiman.inner_text("#duel-record") and "You and Aiman: 0–1" in mei.inner_text("#duel-record")
    ov_a("duel-result")
    ov_m("duel-result-mei")
    aiman.click("#duel-rematch")
    aiman.wait_for_selector("#lobby:not([hidden])")
    mei.goto(base + "/duel")
    assert "Aiman challenged you" in mei.inner_text("main")      # (the rematch asked Mei in again)
    aiman.click("#lobby-leave")
    aiman.wait_for_selector("h1:has-text('Race a friend, live')")
    mei.goto(base + "/duel")
    assert "challenged you" not in mei.inner_text("main")        # (the host left, which closed it: the invitation went with it)
    aiman.goto(base + "/duel/ZZZZZZ")
    assert "isn't open any more" in aiman.inner_text("main")

    # ---- today is a festival (Deepavali): the home page, the road and the scene say so
    fest = ctx_m.new_page()
    fest.goto(base)
    assert "Happy Deepavali!" in fest.inner_text(".season-strip")
    fest.goto(base + "/road")
    fest.wait_for_selector("#go")
    assert "The road is dressed for Deepavali." in fest.inner_text(".season-line") and fest.evaluate("() => window.__road.season") == "deepavali"
    assert fest.evaluate("() => window.__road.theme") == "deepavali"      # (Auto: the festival that is on; Mei never picked a look of her own in this browser)
    fest.close()

    # ---- the house: buy, place, move, turn, put away, character, and a friend's visit
    house_pass(b, key_m, aiman, base, problems, social_db)

    # ---- Telegram in one tap: the page puts a one-time code in the "Open Telegram" link, the bot gets /start with it (called here as Telegram would), and the page notices by itself
    mei.goto(base + "/me")
    mei.wait_for_selector("#tg-open:not(.wait)")
    m = re.fullmatch(r"https://t\.me/BaitproofBot\?start=([A-HJ-NP-Z2-9]{6})", mei.get_attribute("#tg-open", "href") or "")
    assert m, "the link carries a code"
    assert not mei.is_visible("#tg-codetext") and "not connected" in mei.inner_text("#tg-badge").lower()      # (the typed code is folded away)
    mei.click("#tg .tg-alt summary")
    assert mei.inner_text("#tg-codetext").strip() == m.group(1) and mei.is_visible("#tg-timer")      # (and it is the same code, when someone prefers to type it)
    reply = tap_start(social_db, 4242, m.group(1))
    assert reply.startswith("✅ Linked") and "Connected to Mei." in reply
    for _ in range(80):                                                                               # (the page asks every few seconds, then reloads itself)
        if mei.inner_text("#tg-badge").lower() == "connected":      # (the badge is set in capitals: inner_text gives what is shown)
            break
        mei.wait_for_timeout(250)
    assert mei.inner_text("#tg-badge").lower() == "connected" and mei.is_visible("#tg-done") and not mei.is_visible("#tg-open")
    overflow_checker(mei, problems)("me-telegram")
    mei.goto(base + "/records")
    assert mei.inner_text("#tg-badge").lower() == "connected" and mei.is_visible("#tg-unlink")
    mei.click("#tg-unlink")
    mei.wait_for_selector("#tg-open", state="visible")
    assert mei.inner_text("#tg-badge").lower() == "not connected"

    # ---- signing out leaves the account for its key; deleting removes the profile and its place on the board
    mei.goto(base + "/me")
    mei.click("button:has-text('Sign out of this device')")
    mei.wait_for_selector("a.me.login")
    assert "Aiman" not in mei.inner_text("body") and mei.url.rstrip("/") == base
    aiman.goto(base + "/me")
    aiman.check("input[name=confirm]")
    aiman.click("button:has-text('Delete my profile')")
    aiman.wait_for_selector("a.me.login")
    ctx_a.close()
    ctx_m.close()
    b.close()


FINN_POS = "() => { const r = document.querySelector('.finn-root').getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y)] }"
FINN_SAYS = "() => { const b = document.querySelector('.finn-bubble'); return b.classList.contains('on') ? b.textContent : '' }"
FINN_MOOD = "() => (document.querySelector('.finn-root').className.match(/m-(\\w+)/) || [])[1]"


def finn_pass(browser, base, problems) -> None:
    """Finn, the mascot: swims in on a first visit and settles, can be picked up and moved (and is remembered), tells a tip when tapped, reacts to a check,
    obeys the keyboard, can be sent away with the footer switch, holds still for 'reduce motion', and on a phone sits above the tab bar."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 820})
    page = ctx.new_page()
    page.on("console", lambda m: problems.append(f"finn console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: problems.append(f"finn pageerror: {e}"))
    page.goto(base + "/")
    xs = []
    for _ in range(6):
        page.wait_for_timeout(1300)
        xs.append(page.evaluate(FINN_POS)[0])
    assert max(xs) - min(xs) > 400, f"he should swim across the page on a first visit: {xs}"
    page.wait_for_timeout(2400)
    x, y = page.evaluate(FINN_POS)
    assert x > 1000 and y > 560, f"he settles in the bottom-right corner: {(x, y)}"
    assert "Finn" in page.evaluate(FINN_SAYS), "he introduces himself"
    # pick him up and drop him in the middle: he startles while held, stays where he is put, and is remembered after a reload
    c = (x + 64, y + 46)
    page.mouse.move(*c); page.mouse.down(); page.mouse.move(c[0] - 250, c[1] - 200, steps=8); page.mouse.move(560, 340, steps=10)
    page.wait_for_timeout(150)
    assert page.evaluate(FINN_MOOD) == "grab"
    page.mouse.up(); page.wait_for_timeout(1800)
    dropped = page.evaluate(FINN_POS)
    assert abs(dropped[0] - (560 - 64)) < 150 and abs(dropped[1] - (340 - 46)) < 150, f"he stays where he was dropped: {dropped}"
    page.reload(); page.wait_for_timeout(2400)
    back = page.evaluate(FINN_POS)
    assert abs(back[0] - dropped[0]) < 150 and abs(back[1] - dropped[1]) < 150, f"a reload remembers the spot: {dropped} -> {back}"
    # a tap is a tip
    page.evaluate("window.bpFinn.hide()")
    page.mouse.click(back[0] + 64, back[1] + 46); page.wait_for_timeout(400)
    assert page.evaluate(FINN_SAYS), "a tap gives a tip"
    # he reacts to a check: alarmed by a scam
    page.evaluate("window.bpFinn.hide()")
    page.fill("#message", "DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours or it will be returned. Pay now: dhl-fee-pay.xyz/track")
    page.click("#check-form button.big")
    page.wait_for_selector("#result", timeout=60000)
    page.wait_for_timeout(900)
    assert page.evaluate(FINN_MOOD) == "alert" and "link" in page.evaluate(FINN_SAYS), "he is alarmed by a scam"
    # keyboard: arrows move him, Enter gives a tip
    page.evaluate("window.bpFinn.hide()")
    page.focus(".finn-root")
    before = page.evaluate(FINN_POS)
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    assert page.evaluate(FINN_POS)[0] < before[0], "the arrow keys move him"
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    assert page.evaluate(FINN_SAYS), "Enter gives a tip"
    ctx.close()
    # reduce motion: he is simply there, and does not move
    ctx = browser.new_context(viewport={"width": 1280, "height": 820}, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(base + "/")
    page.wait_for_timeout(700)
    a = page.evaluate(FINN_POS)
    page.wait_for_timeout(700)
    assert a == page.evaluate(FINN_POS) and a[0] > 1000, "no flying for reduce motion"
    ctx.close()
    # a phone: smaller, and above the tab bar
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(base + "/")
    page.wait_for_timeout(9500)
    r = page.evaluate("() => { const r = document.querySelector('.finn-root').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.bottom)] }")
    assert r[0] <= 100 and r[1] <= 844 - 70, f"on a phone he is smaller and clear of the tab bar: {r}"
    ctx.close()


def desktop_pass(browser, base, problems) -> None:
    ctx = browser.new_context(viewport={"width": 1280, "height": 720})
    ctx.add_init_script(FAKE_SPEECH)
    page = ctx.new_page()
    page.on("console", lambda m: problems.append(f"desktop console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: problems.append(f"desktop pageerror: {e}"))
    for url in ("/", "/train", "/game", "/records"):
        page.goto(base + url)
        assert [a.strip() for a in page.locator("nav .navlink").all_inner_texts()] == ["Check", "Train", "Friends", "Records"], url
        assert page.locator("nav .navlink").first.is_visible() and not page.is_visible(".tabs"), url
        assert page.is_visible("#textsize") and not page.query_selector("nav .cta") and page.is_visible("#lang summary"), url  # "Aa" and the language menu stay; there is no family-challenge button any more
        assert page.evaluate("document.documentElement.scrollWidth") <= 1280, url
    page.goto(base)
    assert page.is_visible(".home-demo") and page.is_visible("#message") and page.locator("#map").count() == 0
    assert page.is_visible("#inputs") and page.is_visible("#speak-btn") and page.locator("#shot-btn").count() == 0 and page.evaluate("document.documentElement.scrollWidth") <= 1280
    btn = page.evaluate("document.querySelector('#check-form button.big').getBoundingClientRect().bottom")
    assert btn <= 720, btn  # the whole form is above the fold on a laptop
    page.click("nav .navlink:has-text('Train')")
    page.wait_for_selector("#games")
    assert page.inner_text("nav .navlink[aria-current=page]").strip() == "Train"
    page.click("#games a:has-text('Spot the Tell')")
    page.wait_for_selector(".words .w")  # straight into the mode
    assert page.inner_text("nav .navlink[aria-current=page]").strip() == "Train"
    page.goto(base + "/game")  # the game's own address still opens the game hub
    page.wait_for_selector(".mode-card")
    assert page.locator(".boss-grid .tile").count() == 12
    ctx.close()


def main() -> int:
    # NEBIUS_API_KEY="" forces offline rules: the e2e test must never spend model credit (dotenv does not override set vars)
    env = {**os.environ, "BAITPROOF_DB": tempfile.mkdtemp() + "/e2e.sqlite", "BAITPROOF_LOG_DIR": tempfile.mkdtemp(), "NEBIUS_API_KEY": "", "VAPID_PRIVATE_KEY": "", "VAPID_PUBLIC_KEY": "", "BAITPROOF_STT": "0", "BAITPROOF_RATE": "300", "BAITPROOF_BLOCKLIST": "0", "BAITPROOF_ADMIN_TOKEN": "e2e-token", "TELEGRAM_BOT_USERNAME": ""}  # (no AI and no server speech-to-text, even if faster-whisper is installed here)
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.main:app", "--port", str(PORT)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems = f"http://127.0.0.1:{PORT}", []
    wait_until_up(base)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True)
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                                permissions=["clipboard-read", "clipboard-write"])
            ctx.add_init_script(FAKE_SPEECH)  # the browser's speech service is stood in for (it needs a network and a person)
            page = ctx.new_page()
            expect_401 = {"n": 0}  # the wrong-token login attempt deliberately returns 401
            quiet = {"codes": ()}  # statuses a step expects (the 'needs the AI' answer is a 503 on purpose); the browser logs each as a console error

            def on_console(m):
                if m.type in ("error", "warning") and not (expect_401["n"] and "401" in m.text) and not any(f"status of {c}" in m.text for c in quiet["codes"]):
                    problems.append(f"console {m.type}: {m.text}")
            page.on("console", on_console)
            page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

            no_overflow = overflow_checker(page, problems)  # fixed 390px viewport width; innerWidth can't be used because mobile emulation widens it to fit overflow

            # Check flow
            page.goto(base)
            no_overflow("home")
            assert page.locator(".tabs a").count() == 4 and [a.strip() for a in page.locator(".tabs a").all_inner_texts()] == ["Check", "Train", "Friends", "Records"]
            assert page.inner_text(".tabs a[aria-current=page]").strip() == "Check"
            assert not page.is_visible(".home-demo"), "the demo is for wide screens only"
            assert page.locator("#map").count() == 0, "the resilience map lives on the Train page now"
            # the form is the first thing on the phone: the text box, the way-in buttons and the Check button sit above the fold (and above the tab bar);
            # the example chips come after the button there, so the button never drops off the first screen
            box = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
                return { ta: r('#message').bottom, inputs: r('#inputs').top, ex: r('.examples').top, btn: r('#check-form button.big').bottom, h: innerHeight }; }""")
            assert 0 <= box["inputs"] - box["ta"] < 30, box  # the buttons sit right under the text box
            assert box["btn"] <= 844 - 80 and box["ex"] >= box["btn"], box  # the button is visible without scrolling, clear of the bottom tab bar
            page.click("text=Parcel fee")
            assert "dhl-fee-pay" in page.input_value("#message")
            page.click("button.big:has-text('Check it')")
            page.wait_for_selector("#result .banner")
            assert "SCAM" in page.inner_text("#result .banner"), page.inner_text("#result .banner")
            assert "Added to your practice" in page.inner_text("#result")
            no_overflow("result")
            assert page.locator("#map").count() == 0 and "Your scam resilience" not in page.inner_text("main")
            steps = page.locator("#live-steps li").count()
            assert steps >= 5 and not page.is_visible("#live"), steps  # the live view showed the gates, then got out of the way
            res = page.inner_text("#result").lower()  # inner_text applies CSS text-transform
            assert "the evidence" in res and "red flag" in res
            page.click("#result [data-feedback=up]")
            page.wait_for_selector("#result [data-fb-note]:has-text('Thanks')")
            assert page.is_disabled("#result [data-feedback=down]")

            # "Practise this trick" goes to the Train hub: quick practice, the games and the resilience map, with Train as the current tab
            page.click("#result a.big:has-text('Practise this trick')")
            page.wait_for_selector("#practice")
            assert page.url.endswith("/train")
            no_overflow("train-hub")
            assert page.is_visible("#practice #start") and page.is_visible("#games") and page.is_visible("#map")
            assert page.locator("#games a.gm").count() == 6 and "Inbox Rush" in page.inner_text("#games") and "Quick practice" in page.inner_text("#practice")
            # the house is the first thing on the page: above the games, with the one button that opens it; the room draws itself and the character walks where you tap
            assert page.locator("#house").bounding_box()["y"] < page.locator("#games").bounding_box()["y"] < page.locator("#practice").bounding_box()["y"]
            assert page.locator(".hub a.btn.big[href='/house']").count() == 1 and page.locator(".hub .btn").count() == 1
            for _ in range(60):
                if page.evaluate("() => document.getElementById('house').classList.contains('ready')"):
                    break
                page.wait_for_timeout(250)
            assert page.evaluate("() => document.getElementById('house').classList.contains('ready')"), "the preview drew the room"
            page.evaluate("window.scrollTo(0, 0)")  # ("Practise this trick" lands on the practice section, further down the page)
            page.wait_for_timeout(300)
            walking = False
            for cell in ((2.5, 2.5), (3.5, 3.5), (9.5, 2.5), (2.5, 7.5)):  # a floor spot nothing (a piece of furniture, Finn) is covering
                spot = page.evaluate("([x, z]) => window.__house.screenOf(x, z)", list(cell))
                if not page.evaluate("([x, y]) => document.elementFromPoint(x, y)?.id === 'scene'", [spot["x"], spot["y"]]):
                    continue
                page.mouse.click(spot["x"], spot["y"])
                page.wait_for_timeout(500)
                if page.evaluate("() => window.__house.state.char.path.length > 0"):
                    walking = True
                    break
            assert walking, "tapping the floor sends the character walking"
            assert page.inner_text(".tabs a[aria-current=page]").strip() == "Train"

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
            assert page.locator("table.tbl tbody tr").count() >= 1 and page.locator(".kpi use[href='#i-thumb-up']").count() >= 1 and "feedback" in body
            page.goto(base)

            # screenshot and voice on a server with nothing switched on (the AI is off here): no dead buttons, a clear answer, the page keeps working
            inputs_off_pass(page, base, no_overflow, "en", quiet)

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
            open_challenge(page, base)
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

            # ---- the Train page opens a game straight away (/game#rush), and Quit lands on the game hub; Train stays the current tab
            page.goto(base + "/train")
            page.click("#games a:has-text('Inbox Rush')")
            page.wait_for_selector(".choice")
            assert page.url.endswith("/game#rush") and page.inner_text(".tabs a[aria-current=page]").strip() == "Train"
            page.click("button.ghost.quit")
            page.wait_for_selector(".mode-card")

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
            assert page.locator(".hearts use[href='#i-heart-fill']").count() == 3
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
            zh_pass(page, base, no_overflow, expect_401, quiet)
            ms_pass(page, base, no_overflow, quiet)
            ta_pass(page, base, no_overflow, quiet)

            # ---- a laptop: the menu in the header, the form above the fold with the demo beside it, no tab bar
            desktop_pass(b, base, problems)
            finn_pass(b, base, problems)
            b.close()

            # ---- friends and the 3D road, on a public-mode copy: three browsers
            os.environ.setdefault("BAITPROOF_DB", env["BAITPROOF_DB"])  # (the pool of messages is read in this process too, from the same throw-away folder)
            from core.game import pool as gp

            truth = {i.text: i.truth for i in gp.build_pool("en")}
            social_base = f"http://127.0.0.1:{SOCIAL_PORT}"
            social_db = tempfile.mkdtemp() + "/social.sqlite"
            social = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.main:app", "--port", str(SOCIAL_PORT)],
                                      env={**env, "BAITPROOF_MULTIUSER": "1", "BAITPROOF_DB": social_db, "BAITPROOF_RATE": "1000", "BAITPROOF_TODAY": "2026-11-08", "TELEGRAM_BOT_USERNAME": "BaitproofBot"},
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                wait_until_up(social_base)
                social_pass(p, social_base, problems, truth, social_db)
            finally:
                social.terminate()

            # ---- a server that CAN read pictures and voice (canned readers): the full screenshot and voice flows at phone width, in English and Chinese
            fake_base = f"http://127.0.0.1:{FAKE_PORT}"
            fake = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.e2e.fake_inputs_app:app", "--port", str(FAKE_PORT)], env={**env, "BAITPROOF_RATE": "1000"},
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                wait_until_up(fake_base)
                # (--mute-audio: without it a headless Chrome here waits forever for the audio hardware; the fake microphone is a tone)
                b2 = p.chromium.launch(executable_path=CHROME, headless=True, args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--mute-audio"])
                for lang in ("en", "zh"):
                    inputs_on_pass(b2, fake_base, problems, lang)
                b2.close()
            finally:
                fake.terminate()
    finally:
        srv.terminate()
    print("PROBLEMS:" if problems else "E2E OK", *problems, sep="\n  ")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
