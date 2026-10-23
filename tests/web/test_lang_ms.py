"""The website in Bahasa Melayu: choosing it, every page, the scripts' dictionary, the share card, the help panel."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from core.domain.tactics import TACTICS
from core.lang import i18n
from web import deps, ui
from web.main import app

CJK = re.compile(r"[一-鿿]")
PRIZE = "Tahniah! Anda telah memenangi hadiah RM50,000. Sila klik pautan ini untuk menuntut dalam 24 jam http://hadiah-maybank.top/tuntut"
SAME_IN_MALAY = {"WhatsApp", "+{n} XP", "+50 XP", "{a} / {b} XP", "Telegram", "OK", "{n} m", "Scam Road"}  # brands, numbers and loan words written the same
# English wording of the interface that must never show on a Malay page
LEFTOVER = ["Check it", "Check a message", "Practice", "Practise", "Train", "Games", "My records", "Delete", "Read aloud", "The giveaway", "What to do", "The evidence",
            "Red flag", "Reassuring", "Tricks found", "Challenge family", "Start practice", "Paste the message", "Your scam resilience", "Needs work", "Getting there",
            "Loading your game", "Quick practice", "Can you spot", "Take the challenge", "Family challenge", "Connect Telegram", "Not connected",
            "How I decided", "Was this right", "Your data", "Larger text", "Offline mode", "Private by design", "Example only", "Try an example", "Official help"]


@pytest.fixture
def client():
    deps.HITS.clear()
    return TestClient(app)


def ms_client():
    deps.HITS.clear()
    c = TestClient(app)
    c.cookies.set("lang", "ms")
    return c


def visible(html: str) -> str:
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    html = re.sub(r'\sdata-[\w-]+="[^"]*"', "", html)  # (a challenge page carries its messages as data: those are the content being practised, not interface text)
    return re.sub(r'<details class="lang".*?</details>', "", html, flags=re.S)


def html_lang(html: str) -> str:
    return re.search(r'<html lang="([^"]+)"', html).group(1)


def new_challenge(c):
    return c.post("/challenge/new", follow_redirects=False).headers["location"].split("/")[-1]


def test_the_cookie_and_the_browser_can_choose_malay(client):
    assert html_lang(ms_client().get("/").text) == "ms"
    assert html_lang(client.get("/", headers={"accept-language": "ms-MY,ms;q=0.9,en;q=0.5"}).text) == "ms"
    assert html_lang(client.get("/", headers={"accept-language": "en-US,en;q=0.9,ms;q=0.5"}).text) == "en"


def test_switching_to_malay_sets_the_cookie_and_goes_back(client):
    r = client.get("/lang/ms?next=/records", follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers["location"] == "/records" and "lang=ms" in r.headers["set-cookie"]
    assert html_lang(client.get("/records").text) == "ms"
    assert client.get("/lang/MS", follow_redirects=False).headers["set-cookie"].startswith("lang=ms")


def test_the_switcher_names_malay_in_malay_and_marks_it_up():
    html = ms_client().get("/records?channel=web").text
    assert "/lang/ms?next=/records%3Fchannel%3Dweb" in html and "Bahasa Melayu" in html and 'lang="ms"' in html
    assert ">BM<" in html  # what the closed switcher shows for the current language


def test_malay_pages_are_in_malay_with_no_chinese_or_english_chrome():
    c = ms_client()
    cid = new_challenge(c)
    c.post("/check", data={"message": PRIZE})
    pages = {"/": c.get("/").text, "/train": c.get("/train").text, "/game": c.get("/game").text, "/records": c.get("/records").text,
             "/challenge": c.get(f"/challenge/{cid}").text, "/card": c.get(f"/card/{cid}?s=3").text, "/check": c.post("/check", data={"message": PRIZE}).text,
             "/check-en": c.post("/check", data={"message": "Pay with gift cards today or you will be arrested. IRS notice."}).text}
    for name, html in pages.items():
        text = visible(html)
        assert html_lang(html) == "ms", name
        assert not CJK.search(text), (name, CJK.findall(text)[:5])
        for phrase in LEFTOVER:
            assert phrase not in text, (name, phrase)
    assert "Tampal mesej di sini" in pages["/"] and "<title>Rekod saya · Baitproof</title>" in pages["/records"]
    assert "Mulakan latihan" in pages["/train"] or "latihan" in pages["/train"]


def test_a_malay_result_shows_the_help_panel_in_malay():
    html = ms_client().post("/check", data={"message": PRIZE}).text
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", visible(html)))
    assert "PENIPUAN" in text.upper() and "Perlukan bantuan" in text and "Talian bantuan ScamShield" in text and "Oktober 2026" in text
    assert 'href="tel:1799"' in html and 'href="tel:997"' in html and "semakmule.rmp.gov.my" in html


def test_the_title_and_share_tags_are_malay():
    c = ms_client()
    cid = new_challenge(c)
    page = c.get(f"/card/{cid}?s=3").text
    og = re.search(r'<meta property="og:title" content="([^"]*)"', page).group(1)
    assert "Baitproof" in og and "I&#39;m" not in og and not CJK.search(og)
    sub = c.post(f"/api/challenge/{cid}/submit", json={"answers": [True] * 6}).json()
    assert sub["card_url"].endswith("&lang=ms")  # the link carries the language of its preview


def test_the_share_card_image_renders_in_malay_without_a_chinese_font(client):
    cid = new_challenge(client)
    r = client.get(f"/card-image/{cid}.png?s=3&lang=ms")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def i18n_block(html):
    m = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, flags=re.S)
    return json.loads(m.group(1)) if m else None


def test_the_script_dictionary_carries_malay_and_the_speech_language():
    ms = i18n_block(ms_client().get("/").text)
    assert ms["lang"] == "ms" and ms["speech"] == "ms-MY" and ms["dict"]["Read aloud"] == i18n.tr("Read aloud", "ms") and ms["dict"]["Rushing you"] == "Mendesak anda"
    assert "<" not in ui.i18n_json("ms") and "</script" not in ui.i18n_json("ms")


def test_every_string_the_scripts_translate_has_a_malay_version():
    english_labels = {v["label"] for v in TACTICS.values()}
    missing = [k for k in ui.js_keys() if i18n.tr(k, "ms") == k and k not in english_labels and k not in SAME_IN_MALAY]
    assert not missing, missing


def test_the_speech_choice_stays_on_english_pages():
    assert 'id="speak-lang"' not in ms_client().get("/").text
