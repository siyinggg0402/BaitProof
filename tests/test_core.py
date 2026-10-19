import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from core.pipelines import challenge
from core.pipelines import check
from core.storage import db
from core.storage import library
from core.storage import model
from core.pipelines import train
from core.domain.schemas import Verdict as V
from core.domain.tactics import TACTICS
from tests import messages as M


def test_seed_bank_is_valid():
    for e in library.seed_examples():
        assert all(t in TACTICS for t in e["tactics"])
        if e["tell_phrase"]:
            assert e["tell_phrase"] in e["text"], e["id"]
    covered = {t for e in library.seed_examples() for t in e["tactics"]}
    assert covered == set(TACTICS)


@pytest.mark.parametrize("text,ok,tactic", M.SCAMS)
def test_scams_flagged(text, ok, tactic):
    r = check.check_message(text)
    assert r.verdict in ok
    if tactic:
        assert tactic in {t.id for t in r.tactics}


@pytest.mark.parametrize("text", M.BENIGN_BUT_MONEY)
def test_never_bare_all_clear(text):
    r = check.check_message(text)
    assert r.verdict in (V.SAFE, V.UNSURE)
    assert "check" in r.action.lower() or "verify" in r.action.lower() or "official" in r.action.lower()


def test_victim_branch_not_stored():
    r = check.check_message(M.VICTIM[0])
    assert r.verdict == V.VICTIM and not r.added_to_training
    assert library.user_examples() == []


def test_redaction_strips_pii():
    out = library.redact("Call +1 (555) 123-4567 or mail bob@x.com, see https://evil-pay.xyz/a?token=SECRET123")
    assert "555" not in out and "bob@" not in out and "SECRET123" not in out and "evil-pay.xyz" in out


def test_flywheel_real_scam_shows_in_next_session():
    check.check_message("Dear customer your account is locked. We sent a 6-digit code, reply with that code now.")
    assert library.user_examples()
    for _ in range(5):  # selection has randomness; the just-seen tactic must always be in
        picked = [t for t, _ in train.select_tactics(4)]
        assert "otp-credential-phish" in picked


def test_no_raw_text_stored_beyond_redaction():
    check.check_message("Call me at 0412 345 678 about the gift card, pay immediately, email a@b.co")
    stored = library.user_examples()[0]["text"]
    assert "0412" not in stored and "a@b.co" not in stored


def test_transitions():
    assert model.next_state("untested", 0, "correct") == ("learning", 1)
    assert model.next_state("learning", 1, "correct") == ("strong", 2)
    assert model.next_state("strong", 3, "incorrect") == ("learning", 0)
    assert model.next_state("learning", 1, "incorrect") == ("weak", 0)


def test_score_and_recency():
    assert model.baitproof_score() == 0
    model.record_result("urgency-pressure", "correct")
    s1 = model.baitproof_score()
    assert s1 > 0
    with db.connect() as c:
        c.execute("UPDATE mastery SET last_tested=? WHERE tactic='urgency-pressure'", (db.iso(db.now() - timedelta(days=40)),))
    assert model.baitproof_score() < s1


def test_drill_session_moves_map():
    drills = train.build_session()
    assert len(drills) == 4
    before = model.baitproof_score()
    for d in drills:
        g = train.grade(d, d.correct_index, "I would ignore it and call the real bank")
        assert g.result == "correct"
    assert model.baitproof_score() > before
    levels = {r["tactic"]: r["level"] for r in model.all_mastery()}
    assert {levels[d.tactic] for d in drills} == {"learning"}


def test_wrong_answer_is_encouraging_and_demotes():
    d = train.build_session()[0]
    wrong = next(i for i in range(len(d.options)) if i != d.correct_index) if d.options else None
    g = train.grade(d, wrong, "here is my code 1234")
    assert g.result == "incorrect" and "wrong" not in g.note.lower()


def test_challenge_roundtrip():
    cid = challenge.create()
    items = challenge.get(cid)
    assert len(items) == 6
    res = challenge.score(items, [i["is_scam"] for i in items])
    assert res["pct"] == 100


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
    import web.main as w

    monkeypatch.setattr(w, "RATE", 3)
    w.HITS.clear()
    c = TestClient(w.app)
    codes = [c.post("/check", data={"message": "hello there friend"}).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3] == 429
    assert "default-src 'self'" in c.get("/").headers["content-security-policy"]
