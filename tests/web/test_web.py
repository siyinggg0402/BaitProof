import re

from fastapi.testclient import TestClient

from core.storage import library, model


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


def test_the_menu_and_the_phone_tabs_are_check_train_records():
    from web.main import app

    c = TestClient(app)
    for url in ("/", "/train", "/game", "/records", "/records?channel=web"):
        head, tabs = nav(c.get(url).text)
        assert [(h, t) for h, t, _ in head] == [("/", "Check"), ("/train", "Train"), ("/records", "Records")], url
        assert [(h, t) for h, t, _ in tabs] == [("/", "Check"), ("/train", "Train"), ("/records", "Records")], url
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
    assert len(hrefs) == 4 and all(h.split("#")[0] == "/game" for h in hrefs) and {"/game#rush", "/game#daily", "/game#tell"} <= set(hrefs)
    assert "Inbox Rush" in games and "Daily Challenge" in games and "Spot the Tell" in games and "Boss battles" in games
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
