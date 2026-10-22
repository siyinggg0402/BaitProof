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


def overflow_checker(page, problems, W: int = 390):
    """The phone-width check used for every page: nothing sticks out to the right of the screen (tables scroll inside their own box)."""
    def no_overflow(label):
        bad = page.evaluate("""(W) => {
            const bar = document.querySelector('.bar'), br = bar ? bar.getBoundingClientRect().right : W;
            const out = [];
            for (const e of document.querySelectorAll('body *')) {
                if (e.closest('.glow, .tbl-wrap, .sr-only') || !e.getClientRects().length) continue;  // tables scroll inside their own container
                const r = e.getBoundingClientRect().right;
                if (r > W + 1 || (bar && bar.contains(e) && r > br + 1)) out.push(e.tagName.toLowerCase() + '.' + (e.className || '') + '@' + Math.round(r));
            }
            return [document.documentElement.scrollWidth, ...out.slice(0, 5)];
        }""", W)
        if bad[0] > W or len(bad) > 1:
            problems.append(f"{label}: overflow/clipping {bad}")
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
    assert w["chip_voice"] in page.inner_text("#result .src") and "🎤" in page.inner_text("#result .src")
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
    if lang == "en":  # an English page can listen for Malay too
        assert [o.strip() for o in page.locator("#speak-lang option").all_inner_texts()] == ["English", "Bahasa Melayu"]
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
    assert w["chip_shot"] in page.inner_text("#result .src") and "📷" in page.inner_text("#result .src")
    assert not page.is_disabled("#shot-btn") and not page.is_visible("#live")
    panel = page.locator("#result .links")  # the links panel: a real lookalike, an official site and a short link, none of them tappable
    assert w["links"].lower() in panel.inner_text().lower() and panel.locator("li").count() >= 1 and panel.locator("a").count() == 0 and panel.locator("[href]").count() == 0
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
    assert page.locator(".tabs a").count() == 3 and "游戏" not in page.inner_text(".tabs")
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
    assert "My records" in chrome and "Train" in chrome and not re.search("[一-鿿]", chrome), chrome
    no_overflow("en-after-zh")


def desktop_pass(browser, base, problems) -> None:
    ctx = browser.new_context(viewport={"width": 1280, "height": 720})
    ctx.add_init_script(FAKE_SPEECH)
    page = ctx.new_page()
    page.on("console", lambda m: problems.append(f"desktop console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: problems.append(f"desktop pageerror: {e}"))
    for url in ("/", "/train", "/game", "/records"):
        page.goto(base + url)
        assert [a.strip() for a in page.locator("nav .navlink").all_inner_texts()] == ["Check", "Train", "Records"], url
        assert page.locator("nav .navlink").first.is_visible() and not page.is_visible(".tabs"), url
        assert page.is_visible("#textsize") and page.is_visible("nav .cta") and page.is_visible("#lang summary"), url  # "Aa", the family challenge and the language menu stay
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
    env = {**os.environ, "BAITPROOF_DB": tempfile.mkdtemp() + "/e2e.sqlite", "BAITPROOF_LOG_DIR": tempfile.mkdtemp(), "NEBIUS_API_KEY": "", "BAITPROOF_STT": "0", "BAITPROOF_BLOCKLIST": "0", "BAITPROOF_ADMIN_TOKEN": "e2e-token"}  # (no AI and no server speech-to-text, even if faster-whisper is installed here)
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
            assert page.locator(".tabs a").count() == 3 and [a.strip() for a in page.locator(".tabs a").all_inner_texts()] == ["Check", "Train", "Records"]
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
            assert page.locator("#games a.mode-card").count() == 4 and "Inbox Rush" in page.inner_text("#games") and "Quick practice" in page.inner_text("#practice")
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
            assert page.locator("table.tbl tbody tr").count() >= 1 and "👍 1" in body
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
            zh_pass(page, base, no_overflow, expect_401, quiet)

            # ---- a laptop: the menu in the header, the form above the fold with the demo beside it, no tab bar
            desktop_pass(b, base, problems)
            b.close()

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
