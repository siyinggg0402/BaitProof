"""Install Baitproof as an app and share a message into it from the phone's Share menu; and the help panel on a result. The readers are fakes."""
import io
import json
import re

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from core.inputs import image
from core.inputs.errors import InputError
from web import deps
from web.main import app
from web.routes import pwa

SCAM = "DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours or it will be returned. Pay now: dhl-fee-pay.xyz/track"


@pytest.fixture
def client():
    deps.HITS.clear()
    pwa._stash.clear()
    return TestClient(app)


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (12, 12), "white").save(out, "PNG")
    return out.getvalue()


def shared(client, token_from):
    """Follow a /share answer to the page it redirects to."""
    assert token_from.status_code == 303
    return client.get(token_from.headers["location"])


# ---------------------------------------------------------------- the app
def test_the_manifest_makes_baitproof_installable_and_a_share_target(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["display"] == "standalone" and m["start_url"] == "/" and m["scope"] == "/" and m["theme_color"] == "#7A5CD0"
    t = m["share_target"]
    assert t["action"] == "/share" and t["method"] == "POST" and t["enctype"] == "multipart/form-data"
    assert t["params"]["text"] == "text" and t["params"]["files"] == [{"name": "image", "accept": ["image/*"]}]
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes and any(i["purpose"] == "maskable" for i in m["icons"])
    for icon in m["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_the_service_worker_covers_the_whole_site_and_caches_nothing(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"] and r.headers["service-worker-allowed"] == "/" and r.headers["cache-control"] == "no-cache"
    assert "caches." not in r.text and "cache.put" not in r.text  # a scam checker must show the live answer


def test_every_page_links_the_manifest_and_has_no_install_button(client):
    html = client.get("/").text
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html and 'name="theme-color"' in html and "/static/js/pwa.js" in html
    assert "install-btn" not in html  # the browser's own "install" menu is the way in; the page carries no button of its own


# ---------------------------------------------------------------- sharing words
def test_shared_words_land_in_the_box_and_are_checked_at_once(client):
    r = client.post("/share", files={"x": ("a", b"")}, data={"text": SCAM, "title": "DHL"}, follow_redirects=False)
    assert re.fullmatch(r"/\?share=[\w-]{16,}", r.headers["location"])
    page = shared(client, r).text
    assert SCAM in page.replace("&#34;", '"') and 'data-autocheck="1"' in page and "Shared from another app. Checking it now…" in page
    assert 'name="source" id="source" value="text"' in page


def test_a_shared_item_works_once_and_then_is_forgotten(client):
    mine = "My own shared words, ZEBRA-4242"  # (the page's built-in examples contain SCAM, so use words nothing else has)
    r = client.post("/share", data={"text": mine}, files={"x": ("a", b"")}, follow_redirects=False)
    assert mine in shared(client, r).text
    again = shared(client, r).text
    assert mine not in again and 'data-autocheck' not in again


def test_a_shared_item_expires(client, monkeypatch):
    r = client.post("/share", data={"text": "ZEBRA-4242 words"}, files={"x": ("a", b"")}, follow_redirects=False)
    monkeypatch.setattr(pwa.time, "time", lambda: 10 ** 10)
    assert "ZEBRA-4242" not in shared(client, r).text


def test_a_long_message_arrives_whole_and_a_repeated_address_is_not_added_twice(client):
    long = ("Your bank account will be suspended unless you verify now. " * 60)[:3500] + " https://evil-bank.top/x"
    r = client.post("/share", data={"text": long, "url": "https://evil-bank.top/x", "title": "Your bank account will be suspended"}, files={"x": ("a", b"")}, follow_redirects=False)
    page = shared(client, r).text
    assert page.count("https://evil-bank.top/x") == 1 and "suspended unless you verify now." in page and len(re.search(r"<textarea[^>]*>(.*?)</textarea>", page, re.S).group(1)) > 3000
    assert pwa.words_of({"title": "Hi", "text": "Hello there", "url": "https://a.example/x"}) == "Hi\nHello there\nhttps://a.example/x"
    assert pwa.words_of({"title": "Hello", "text": "Hello there, how are you", "url": ""}) == "Hello there, how are you"  # a title that starts the text is not said twice


def test_nothing_shared_or_too_much_is_explained_not_checked(client):
    empty = client.post("/share", data={}, files={"x": ("a", b"")}, follow_redirects=False)
    assert empty.headers["location"] == "/?shared=empty" and "Nothing came through from the Share menu" in shared(client, empty).text
    page = client.get("/?shared=too_big").text
    assert "That picture is too big" in page and "data-autocheck" not in page
    big = client.post("/share", files={"image": ("s.png", b"x" * (image.MAX_BYTES + 100_000), "image/png")}, follow_redirects=False)
    assert big.headers["location"] == "/?shared=too_big"


def test_too_many_waiting_at_once_is_said_politely(client):
    for i in range(pwa.MAX_ITEMS):
        assert pwa.keep({"text": str(i), "image": None})
    r = client.post("/share", data={"text": SCAM}, files={"x": ("a", b"")}, follow_redirects=False)
    assert r.headers["location"] == "/?shared=busy" and "busy right now" in shared(client, r).text


def test_the_token_cannot_be_used_for_anything_else(client):
    assert "not-a-real-token" not in client.get("/?share=not-a-real-token").text and 'data-autocheck' not in client.get("/?share=").text
    assert pwa.take("") is None and pwa.take("nope") is None


# ---------------------------------------------------------------- sharing a screenshot
def test_a_shared_screenshot_is_read_and_its_origin_goes_with_the_check(client, monkeypatch):
    monkeypatch.setattr(image, "read_image", lambda data, *, lang="en": image.ImageReading(text="Voucher Applied APP | PAYDAY REWARDS 1-FOR-1", channel="app", app="Tomoro Coffee"))
    r = client.post("/share", files={"image": ("shot.png", png(), "image/png")}, follow_redirects=False)
    page = shared(client, r).text
    assert "Voucher Applied APP" in page and 'name="source" id="source" value="screenshot"' in page and 'data-autocheck="1"' in page
    assert 'id="origin-app" value="Tomoro Coffee"' in page and 'id="origin-channel" value="app"' in page


def test_a_shared_screenshot_that_cannot_be_read_says_so_or_falls_back_to_its_words(client, monkeypatch):
    def broken(data, *, lang="en"):
        raise InputError("unavailable", "Reading screenshots needs the AI, which is not switched on here. Paste the text instead.")
    monkeypatch.setattr(image, "read_image", broken)
    r = client.post("/share", files={"image": ("shot.png", png(), "image/png")}, follow_redirects=False)
    page = shared(client, r).text
    assert "Reading screenshots needs the AI" in page and "data-autocheck" not in page
    r = client.post("/share", files={"image": ("shot.png", png(), "image/png")}, data={"text": SCAM}, follow_redirects=False)
    page = shared(client, r).text
    assert SCAM in page and 'data-autocheck="1"' in page  # the words that came with the picture are still checked


def test_the_picture_is_never_kept_after_it_is_read(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(image, "read_image", lambda data, *, lang="en": seen.setdefault("n", len(data)) and image.ImageReading(text="hello there"))
    r = client.post("/share", files={"image": ("shot.png", png(), "image/png")}, follow_redirects=False)
    shared(client, r)
    assert seen["n"] > 0 and pwa._stash == {}  # taken from memory on use; nothing on disk


def test_the_share_pages_obey_the_strict_security_policy(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "'unsafe-inline'" not in csp and "script-src 'self'" in csp and not re.search(r"\sstyle=", r.text)
    assert "<script>" not in r.text  # no inline script (the dictionary is JSON, not code)


# ---------------------------------------------------------------- the help panel on a result
def check(client, text):
    return client.post("/check", data={"message": text}).text


def test_a_scam_result_offers_the_official_lines_with_tappable_numbers(client):
    page = check(client, SCAM)
    assert 'class="help" open' in page and "Need help, or want to report it?" in page
    for must in ('href="tel:1799"', 'href="tel:1800-722-6688"', 'href="tel:997"', "https://go.gov.sg/scamreport", "https://semakmule.rmp.gov.my/", "Singapore", "Malaysia"):
        assert must in page, must
    assert 'rel="noopener"' in page and "Real officials never ask you to move money" in page


def test_an_ordinary_message_has_no_help_panel_and_the_panel_is_translated(client):
    assert 'class="help"' not in check(client, "Your verification code is 482913. It expires in 10 minutes. Never share it.")
    zh = TestClient(app, cookies={"lang": "zh"}).post("/check", data={"message": SCAM}).text
    assert "需要帮助，或想举报？" in zh and "新加坡" in zh and "马来西亚" in zh and 'href="tel:997"' in zh


def test_the_manifest_is_valid_json_with_no_surprises():
    text = json.dumps(pwa.MANIFEST)
    assert "http://" not in text and "javascript:" not in text
