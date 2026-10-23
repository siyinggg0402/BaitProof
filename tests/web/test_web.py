"""Finn, the mascot. The behaviour is checked in a real browser (tests/e2e/browser.py, finn_pass); here: what the server sends, and that the script and
stylesheet keep to the site's rules (no inline styles, no outside files, calm for 'reduce motion', every line he can say translated)."""
from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

from core.lang.i18n import tr
from core.storage import library, model
from web import ui
from web import deps
from web.main import app


def test_web_flow():
    from web.main import app

    c = TestClient(app)
    assert c.get("/").status_code == 200
    r = c.post("/check", data={"message": "Pay with gift cards today or you will be arrested. IRS notice."})
    assert r.status_code == 200 and "SCAM" in r.text
    s = c.post("/api/train/start").json()
    assert s["items"] and "correct_index" not in s["items"][0]
    first = s["items"][0]
    a = c.post("/api/train/answer", json={"session": s["session"], "item_id": first["id"], "choice": 0, "text": "ignore it"}).json()
    assert a["result"] in ("correct", "incorrect", "partial") and "map" in a
    ch = c.post("/challenge/new", follow_redirects=False)
    cid = ch.headers["location"].split("/")[-1]
    assert c.get(f"/challenge/{cid}").status_code == 200
    sub = c.post(f"/api/challenge/{cid}/submit", json={"answers": [True] * 6}).json()
    card = c.get(sub["card_url"])
    assert "og:title" in card.text


def test_public_deploy_isolates_visitors_but_shares_challenges(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    from web.main import app

    a, b = TestClient(app), TestClient(app)
    a.get("/")
    b.get("/")
    assert a.cookies.get("bp") and a.cookies.get("bp") != b.cookies.get("bp")
    a.post("/check", data={"message": "Buy 4 gift cards and send me the numbers please."})
    assert a.get("/api/map").json()["tactics"] and len(library.user_examples()) == 0  # nothing leaked to the global/default DB
    exposure = lambda c: sum(1 for t in c.get("/api/map").json()["tactics"] if t["level"] != "untested")
    assert exposure(b) == 0
    a.post("/api/train/start")  # A's session pulls A's own library
    cid = a.post("/challenge/new", follow_redirects=False).headers["location"].split("/")[-1]
    assert b.get(f"/challenge/{cid}").status_code == 200  # a different person can open it


def test_rate_limit_and_headers(monkeypatch):
    from web import deps
    from web.main import app

    monkeypatch.setattr(deps, "RATE", 3)
    deps.HITS.clear()
    c = TestClient(app)
    codes = [c.post("/check", data={"message": "hello there friend"}).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3] == 429
    assert "default-src 'self'" in c.get("/").headers["content-security-policy"]


def test_share_card_image_and_og_tags():
    from web.main import app

    c = TestClient(app)
    cid = c.post("/challenge/new", follow_redirects=False).headers["location"].split("/")[-1]
    png = c.get(f"/card-image/{cid}.png?s=4")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    page = c.get(f"/card/{cid}?s=4").text
    assert 'og:image' in page and f"/card-image/{cid}.png?s=4" in page and 'id="share"' in page
    assert c.get("/card-image/nope.png").status_code == 404


def test_web_rejects_empty_and_escapes_html():
    from web.main import app

    c = TestClient(app)
    assert c.post("/check", data={"message": "   "}).status_code == 400
    page = c.post("/check", data={"message": "<img src=x onerror=alert(1)> pay now by gift card"}).text
    assert "<img src=x" not in page and "&lt;img" in page
    assert c.post("/api/train/answer", json={"session": "nope", "item_id": "x", "choice": 0}).status_code == 404
    assert c.get("/challenge/doesnotexist").status_code == 404


def test_due_pill_shown_on_the_train_hub_only():
    from web.main import app

    model.record_result("urgency-pressure", "incorrect")
    c = TestClient(app)
    assert "due for a refresher" in c.get("/train").text and 'href="/train#practice"' in c.get("/train").text
    assert "due for a refresher" not in c.get("/").text


# ------------------------------------------------------------------------------------------------ navigation and the page structure
def nav(html):
    """(links of the header menu, links of the phone tab bar), each as [(href, text, is_current)]."""
    def links(block):
        return [(m.group(1), re.sub(r"<[^>]+>", "", m.group(3)).strip(), "aria-current" in m.group(2)) for m in re.finditer(r'<a (?:class="navlink" )?href="([^"]+)"([^>]*)>(.*?)</a>', block, flags=re.S)]
    head = re.search(r'<nav aria-label="Main">(.*?)</nav>', html, flags=re.S).group(1)
    tabs = re.search(r'<nav class="tabs"[^>]*>(.*?)</nav>', html, flags=re.S).group(1)
    return links(head), links(tabs)


def test_the_menu_and_the_phone_tabs_are_check_train_friends_records():
    from web.main import app

    c = TestClient(app)
    for url in ("/", "/train", "/game", "/records", "/records?channel=web"):
        head, tabs = nav(c.get(url).text)
        assert [(h, t) for h, t, _ in head] == [("/", "Check"), ("/train", "Train"), ("/friends", "Friends"), ("/records", "Records")], url
        assert [(h, t) for h, t, _ in tabs] == [("/", "Check"), ("/train", "Train"), ("/friends", "Friends"), ("/records", "Records")], url
        assert "Challenge family" in c.get(url).text and 'id="textsize"' in c.get(url).text and 'id="lang"' in c.get(url).text  # the CTA, "Aa" and the language menu stay


def test_the_current_tab_follows_the_page_and_the_game_belongs_to_train():
    from web.main import app

    c = TestClient(app)
    current = lambda html: ([h for h, _, on in nav(html)[0] if on], [h for h, _, on in nav(html)[1] if on])  # noqa: E731
    assert current(c.get("/").text) == (["/"], ["/"])
    assert current(c.post("/check", data={"message": "hello there friend"}).text) == (["/"], ["/"])
    assert current(c.get("/train").text) == (["/train"], ["/train"])
    assert current(c.get("/game").text) == (["/train"], ["/train"])
    assert current(c.get("/records").text) == (["/records"], ["/records"])


def test_the_train_hub_holds_quick_practice_and_the_games_and_the_map():
    from web.main import app

    c = TestClient(app)
    html = c.get("/train").text
    assert html.index('id="practice"') < html.index('id="games"') < html.index('id="map-h"')  # quick practice, then games, then the map
    assert 'id="stage"' in html and 'id="start"' in html and "/static/js/train.js" in html and "Quick practice" in html and "Start practice" in html
    games = html[html.index('id="games"'):html.index('id="map-h"')]
    hrefs = re.findall(r'class="mode-card[^"]*" href="([^"]+)"', games)
    assert len(hrefs) == 6 and hrefs[:2] == ["/road", "/link"] and all(h.split("#")[0] == "/game" for h in hrefs[2:]) and {"/game#rush", "/game#daily", "/game#tell"} <= set(hrefs)
    assert "Scam Road" in games and "Link Hunt" in games and "Inbox Rush" in games and "Daily Challenge" in games and "Spot the Tell" in games and "Boss battles" in games
    game = c.get("/game")  # the game itself is where it always was
    assert game.status_code == 200 and 'id="game"' in game.text


def test_the_home_page_leads_with_the_checker_and_no_longer_carries_the_map():
    from web.main import app

    c = TestClient(app)
    for html in (c.get("/").text, c.post("/check", data={"message": "Pay with gift cards today or you will be arrested. IRS notice."}).text):
        assert 'id="map"' not in html and "Your scam resilience" not in html
        assert html.index("<h1") < html.index('id="check-form"') < html.index('id="demo-bubble"')  # the form comes before the demo
        assert html.index("<textarea") < html.index("data-example") < html.index('<button class="big">')  # the example chips sit right under the text box
        assert "Start practice" not in html  # the hero no longer carries a second button: Train is a tab
    result = c.post("/check", data={"message": "Pay with gift cards today or you will be arrested. IRS notice."}).text
    assert re.search(r'<a class="big" href="/train">Practise this trick', result)  # after a result, practice is the Train hub


ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "web/static/js/mascot.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/static/css/mascot.css").read_text(encoding="utf-8")


def page(lang="en"):
    c = TestClient(app)
    c.cookies.set("lang", lang)
    return c.get("/").text


def test_every_page_loads_him_and_the_switch_that_sends_him_away():
    html = page()
    assert '/static/css/mascot.css' in html and '/static/js/mascot.js' in html
    assert re.search(r'id="mascot-toggle"[^>]*aria-pressed="true"[^>]*hidden>Finn the fish<', html)  # hidden until the script knows he can run
    assert html.index("/static/js/app.js") < html.index("/static/js/mascot.js")  # he uses the page's translator, so it loads first


def test_the_switch_and_his_aria_label_are_translated():
    assert "小鱼 Finn" in page("zh") and "小魚 Finn" in page("zh-Hant")  # Traditional is derived from the Simplified text
    assert tr("Finn the fish, your scam-spotting helper. Press Enter for a tip, and use the arrow keys to move him.", "zh").startswith("小鱼 Finn")


def test_the_admin_pages_have_no_mascot_script_problem():
    # the dashboard extends the same layout: it must still render
    c = TestClient(app)
    assert c.get("/admin").status_code in (200, 401, 404)


def test_every_line_he_says_has_a_chinese_version_in_both_scripts():
    said = [k for k in ui.js_keys() if k in JS_LINES]
    assert len(said) >= 24  # the tips, the reactions, the greeting and his label
    for k in said:
        assert tr(k, "zh") != k and tr(k, "zh-Hant") != k, k


JS_LINES = {m.group(1) for m in re.finditer(r'\bt\("((?:[^"\\\n]|\\.)*)"\)', JS)}


def test_the_drawing_and_the_script_obey_the_site_rules():
    svg = re.search(r"const SVG = `(.*?)`;", JS, re.S).group(1)
    assert "style=" not in svg and "http" not in svg and "<script" not in svg and "<image" not in svg  # strict CSP: no inline style, no outside file
    assert "eval(" not in JS and "new Function" not in JS and "document.write" not in JS
    assert "innerHTML" in JS and JS.count("innerHTML") == 1  # only the fixed drawing is ever parsed as markup; his words go in as plain text
    assert "textContent" in JS and "bubble.textContent = text" in JS
    assert "@import" not in CSS and "url(" not in CSS  # nothing fetched from anywhere


def test_he_is_calm_for_reduce_motion_and_never_blocks_the_page():
    assert "prefers-reduced-motion" in CSS and "prefers-reduced-motion" in JS
    assert re.search(r"\.finn-root\.moving:not\(\.grabbed\)\{pointer-events:none\}", CSS)  # swimming on his own, he is click-through
    assert "pointer-events:none" in CSS.split(".finn-bubble{")[1].split("}")[0]  # his speech bubble never catches a click
    assert 'aria-hidden", "true"' in JS and 'role", "status"' in JS  # the bubble is hidden from screen readers; one polite live region speaks instead
    assert "localStorage" in JS and "try {" in JS  # a blocked store (private mode) must not break the page


@pytest.fixture
def client():
    deps.HITS.clear()
    return TestClient(app)


def start(c, mode="rush", trick=""):
    return c.post("/api/game/start", json={"mode": mode, "trick": trick}).json()


def test_page_and_state(client):
    html = client.get("/game").text
    assert 'id="game"' in html and "/static/js/game.js" in html
    assert re.search(r'href="/train"\s+aria-current="page"', html)  # the game lives under the Train tab: it is the current one here
    s = client.get("/api/game/state").json()
    assert s["level"] == 1 and len(s["tricks"]) == 12 and s["badges"] == []


def test_a_full_round_over_the_api_and_answers_stay_hidden_until_revealed(client):
    r = start(client)
    assert r["mode"] == "rush" and len(r["items"]) == 8 and set(r) == {"round", "mode", "trick", "trick_label", "lives", "total", "items"}
    assert all(set(i) <= {"id", "text", "yours", "words"} for i in r["items"])  # no truth, no explanation, no tricks
    # answering the way the page would: reveal returns the verdict and the explanation
    first = r["items"][0]
    a = client.post("/api/game/answer", json={"round": r["round"], "item_id": first["id"], "choice": "scam"}).json()
    assert a["outcome"] in ("correct", "wrong", "partial") and a["truth"] in ("scam", "safe", "unsure") and "tell" in a
    for it in r["items"][1:]:
        client.post("/api/game/answer", json={"round": r["round"], "item_id": it["id"], "choice": "unsure"})
    f = client.post("/api/game/finish", json={"round": r["round"]}).json()
    assert f["completed"] and f["total"] == 8 and f["state"]["rounds"] == 1 and f["xp_gained"] > 0
    assert client.get("/api/game/state").json()["xp"] == f["state"]["xp"]


def test_boss_spot_the_tell_and_daily_modes_work(client):
    b = start(client, "boss", "urgency-pressure")
    assert b["lives"] == 3 and b["trick_label"] and len(b["items"]) >= 5
    t = start(client, "tell")
    assert all(i["words"] for i in t["items"])
    res = client.post("/api/game/answer", json={"round": t["round"], "item_id": t["items"][0]["id"], "picked": [0, 1]}).json()
    assert res["tell_phrase"] and res["outcome"] in ("correct", "partial", "wrong")
    d1, d2 = start(client, "daily"), start(client, "daily")
    assert [i["id"] for i in d1["items"]] == [i["id"] for i in d2["items"]]


@pytest.mark.parametrize("body,code", [({"mode": "nonsense"}, 400), ({"mode": "boss", "trick": "nope"}, 400), ({"mode": "yours"}, 400)])
def test_bad_start_requests_get_a_clear_400(client, body, code):
    r = client.post("/api/game/start", json=body)
    assert r.status_code == code and r.json()["detail"]


def test_bad_answers_and_unknown_rounds(client):
    r = start(client)
    it = r["items"][0]["id"]
    assert client.post("/api/game/answer", json={"round": r["round"], "item_id": it, "choice": "maybe"}).status_code == 400
    assert client.post("/api/game/answer", json={"round": r["round"], "item_id": "nope", "choice": "scam"}).status_code == 400
    client.post("/api/game/answer", json={"round": r["round"], "item_id": it, "choice": "scam"})
    assert client.post("/api/game/answer", json={"round": r["round"], "item_id": it, "choice": "scam"}).status_code == 400  # twice
    assert client.post("/api/game/answer", json={"round": "doesnotexist", "item_id": it, "choice": "scam"}).status_code == 404
    assert client.post("/api/game/finish", json={"round": "doesnotexist"}).status_code == 404


def test_visitors_have_separate_progress_and_cannot_answer_each_others_rounds(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    deps.HITS.clear()
    a, b = TestClient(app), TestClient(app)
    a.get("/")
    b.get("/")
    ra = a.post("/api/game/start", json={"mode": "rush"}).json()
    assert b.post("/api/game/answer", json={"round": ra["round"], "item_id": ra["items"][0]["id"], "choice": "scam"}).status_code == 404
    assert b.post("/api/game/finish", json={"round": ra["round"]}).status_code == 404
    for it in ra["items"]:
        a.post("/api/game/answer", json={"round": ra["round"], "item_id": it["id"], "choice": "unsure"})
    a.post("/api/game/finish", json={"round": ra["round"]})
    assert a.get("/api/game/state").json()["xp"] > 0 and b.get("/api/game/state").json()["xp"] == 0


def test_starting_rounds_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(deps, "RATE", 2)
    deps.HITS.clear()
    assert [client.post("/api/game/start", json={"mode": "rush"}).status_code for _ in range(3)] == [200, 200, 429]


def test_playing_improves_the_resilience_score_shown_on_the_hub(client):
    before = client.get("/api/game/state").json()["resilience"]
    r = start(client)
    for it in r["items"]:
        client.post("/api/game/answer", json={"round": r["round"], "item_id": it["id"], "choice": "scam"})
    client.post("/api/game/finish", json={"round": r["round"]})
    assert client.get("/api/game/state").json()["resilience"] >= before and client.get("/api/map").json()["score"] >= before
