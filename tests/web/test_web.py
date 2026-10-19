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


def test_due_pill_shown():
    from web.main import app

    model.record_result("urgency-pressure", "incorrect")
    assert "due for a refresher" in TestClient(app).get("/").text
