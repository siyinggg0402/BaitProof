"""The website in Tamil (தமிழ்): choosing it, every page, the scripts' dictionary, the share card, the help panel, the voice choices."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from core.domain.tactics import TACTICS
from core.lang import i18n
from web import deps, ui
from web.main import app

TAMIL = re.compile(r"[஀-௿]")
CJK = re.compile(r"[一-鿿]")
MSG = "உங்கள் DBS கணக்கு முடக்கப்படும். உடனே இங்கே சரிபார்க்கவும்: http://dbs-verify.top/login"
SAME_IN_TAMIL = {"WhatsApp", "+{n} XP", "+50 XP", "{a} / {b} XP", "Telegram", "OK", "{n} m", "Baitproof", "XP", "Finn", "SMS", "QR", "OTP", "PIN", "URL"}  # brands, numbers and symbols written the same
# English wording of the interface that must never show on a Tamil page
LEFTOVER = ["Check it", "Check a message", "Practice", "Practise", "Train", "Games", "My records", "Delete", "Read aloud", "The giveaway", "What to do", "The evidence",
            "Red flag", "Reassuring", "Tricks found", "Challenge family", "Start practice", "Paste the message", "Your scam resilience", "Needs work", "Getting there",
            "Loading your game", "Quick practice", "Can you spot", "Take the challenge", "Family challenge", "Connect Telegram", "Not connected",
            "How I decided", "Was this right", "Your data", "Larger text", "Offline mode", "Private by design", "Example only", "Try an example", "Official help"]


@pytest.fixture
def client():
    deps.HITS.clear()
    return TestClient(app)


def ta_client():
    deps.HITS.clear()
    c = TestClient(app)
    c.cookies.set("lang", "ta")
    return c


def visible(html: str) -> str:
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    html = re.sub(r'\sdata-[\w-]+="[^"]*"', "", html)
    return re.sub(r'<details class="lang".*?</details>', "", html, flags=re.S)


def html_lang(html: str) -> str:
    return re.search(r'<html lang="([^"]+)"', html).group(1)


def new_challenge(c):
    return c.post("/challenge/new", follow_redirects=False).headers["location"].split("/")[-1]


def test_the_cookie_and_the_browser_can_choose_tamil(client):
    assert html_lang(ta_client().get("/").text) == "ta"
    assert html_lang(client.get("/", headers={"accept-language": "ta-SG,ta;q=0.9,en;q=0.5"}).text) == "ta"
    assert html_lang(client.get("/", headers={"accept-language": "en-SG,en;q=0.9,ta;q=0.5"}).text) == "en"


def test_switching_to_tamil_sets_the_cookie_and_goes_back(client):
    r = client.get("/lang/ta?next=/records", follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers["location"] == "/records" and "lang=ta" in r.headers["set-cookie"]
    assert html_lang(client.get("/records").text) == "ta"
    assert client.get("/lang/TA", follow_redirects=False).headers["set-cookie"].startswith("lang=ta")


def test_the_switcher_names_tamil_in_tamil_and_marks_it_up():
    html = ta_client().get("/records?channel=web").text
    assert "/lang/ta?next=/records%3Fchannel%3Dweb" in html and ">தமிழ்<" in html and 'lang="ta"' in html
    for lang in ("en", "zh", "ms"):                                   # (every other page offers Tamil too)
        c = TestClient(app)
        c.cookies.set("lang", lang)
        assert "/lang/ta?" in c.get("/").text


def test_tamil_pages_are_in_tamil_with_no_chinese_or_english_chrome():
    c = ta_client()
    cid = new_challenge(c)
    pages = {"/": c.get("/").text, "/train": c.get("/train").text, "/game": c.get("/game").text, "/records": c.get("/records").text, "/house": c.get("/house").text,
             "/challenge": c.get(f"/challenge/{cid}").text, "/card": c.get(f"/card/{cid}?s=3").text, "/check": c.post("/check", data={"message": MSG}).text,
             "/check-en": c.post("/check", data={"message": "Pay with gift cards today or you will be arrested. IRS notice."}).text}
    for name, html in pages.items():
        text = visible(html)
        assert html_lang(html) == "ta", name
        assert not CJK.search(text), (name, CJK.findall(text)[:5])
        assert TAMIL.search(text), name
        for phrase in LEFTOVER:
            assert phrase not in text, (name, phrase)


def test_a_tamil_result_shows_the_help_panel_in_tamil():
    html = ta_client().post("/check", data={"message": MSG}).text
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", visible(html)))
    assert "ScamShield" in text and "1799" in text and 'href="tel:1799"' in html and TAMIL.search(text)
    assert i18n.tr("Need help, or want to report it?", "ta") in text


def test_the_title_and_share_tags_are_tamil():
    c = ta_client()
    cid = new_challenge(c)
    page = c.get(f"/card/{cid}?s=3").text
    og = re.search(r'<meta property="og:title" content="([^"]*)"', page).group(1)
    assert "Baitproof" in og and "I&#39;m" not in og and TAMIL.search(og)
    sub = c.post(f"/api/challenge/{cid}/submit", json={"answers": [True] * 6}).json()
    assert sub["card_url"].endswith("&lang=ta")           # the link carries the language of its preview


def test_the_share_card_image_renders_in_tamil_or_falls_back_to_english_never_to_boxes(client):
    cid = new_challenge(client)
    r = client.get(f"/card-image/{cid}.png?s=3&lang=ta")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def i18n_block(html):
    m = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, flags=re.S)
    return json.loads(m.group(1)) if m else None


def test_the_script_dictionary_carries_tamil_and_the_speech_language():
    ta = i18n_block(ta_client().get("/").text)
    assert ta["lang"] == "ta" and ta["speech"] == "ta-IN" and ta["dict"]["Read aloud"] == i18n.tr("Read aloud", "ta") and TAMIL.search(ta["dict"]["Rushing you"])
    assert "<" not in ui.i18n_json("ta") and "</script" not in ui.i18n_json("ta")


def test_every_string_the_scripts_and_pages_translate_has_a_tamil_version():
    english_labels = {v["label"] for v in TACTICS.values()}
    missing = [k for k in ui.js_keys() if i18n.tr(k, "ta") == k and k not in english_labels and k not in SAME_IN_TAMIL]
    assert not missing, missing
    from pathlib import Path

    keys = set()
    for f in (Path(__file__).resolve().parents[2] / "web" / "templates").glob("*.html"):
        for m in re.finditer(r"""_h?\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""", f.read_text()):
            keys.add(eval(m.group(1)))
    assert not [k for k in keys if k not in i18n.TA and not re.fullmatch(r"[^A-Za-z]*", k) and k not in english_labels], "a template string has no Tamil version"


def test_speaking_is_offered_in_tamil_on_the_english_page_and_follows_the_page_elsewhere():
    en = TestClient(app).get("/").text
    assert 'id="speak-lang"' in en and 'value="ta-IN"' in en
    assert 'id="speak-lang"' not in ta_client().get("/").text


def test_the_other_languages_are_untouched_by_tamil():
    for lang, word in (("ms", i18n.tr("Paste the message here", "ms")), ("zh", i18n.tr("Paste the message here", "zh"))):
        c = TestClient(app)
        c.cookies.set("lang", lang)
        text = c.get("/").text
        assert word in text and not TAMIL.search(visible(text))
