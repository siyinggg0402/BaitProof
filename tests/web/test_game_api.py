import re

import pytest
from fastapi.testclient import TestClient

from web import deps
from web.main import app


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
