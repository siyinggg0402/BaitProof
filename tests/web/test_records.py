import re

import pytest
from fastapi.testclient import TestClient

from bot import handlers
from core.storage import db, history, links
from web import deps
from web.main import app

SCAM = "Buy 4 gift cards and send me the codes right now. Don't tell Mom. Call +61 412 345 678"


@pytest.fixture
def client():
    deps.HITS.clear()
    return TestClient(app)


def rec_ids(html):
    return re.findall(r'class="rec [^"]*" data-id="([0-9a-f]{12})"', html)


def test_web_checks_are_recorded_and_shown_without_the_raw_message(client):
    client.post("/check", data={"message": SCAM})
    html = client.get("/records").text
    assert len(rec_ids(html)) == 1 and "Website" in html and "Scam" in html
    assert "412 345" not in html and "+61" not in html  # the phone number is redacted in the preview
    assert "Add to your practice" not in html and "Added to your practice" in html


def test_the_live_stream_path_records_too(client):
    with client.stream("POST", "/api/check/stream", json={"message": SCAM}) as r:
        for _ in r.iter_lines():
            pass
    assert len(rec_ids(client.get("/records").text)) == 1


def test_empty_state_and_navigation(client):
    html = client.get("/records").text
    assert "Nothing here yet" in html and 'href="/records"' in html and 'href="/game"' in html and 'class="tabs"' in html


def test_delete_one_clear_all_and_filters(client):
    client.post("/check", data={"message": SCAM})
    client.post("/check", data={"message": "Lunch on Sunday at ours? Everyone's coming around 1."})
    ids = rec_ids(client.get("/records").text)
    assert len(ids) == 2
    assert client.post("/api/records/delete", json={"id": ids[0]}).json() == {"deleted": True}
    assert len(rec_ids(client.get("/records").text)) == 1
    assert rec_ids(client.get("/records?channel=telegram").text) == []
    assert client.post("/api/records/delete", json={"id": "../etc"}).status_code == 422
    assert client.post("/api/records/clear").json() == {"deleted": 1}
    assert rec_ids(client.get("/records").text) == []


def test_turning_previews_off_removes_the_ones_already_kept(client):
    client.post("/check", data={"message": SCAM})
    assert "rec-preview" in client.get("/records").text
    assert client.post("/api/settings/previews", json={"on": False}).json() == {"previews": False}
    html = client.get("/records").text
    assert "rec-preview" not in html and 'id="pv" checked' not in html
    client.post("/check", data={"message": SCAM + " again"})
    assert "rec-preview" not in client.get("/records").text  # and new ones keep none


def test_connect_code_status_and_unlink(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "@BaitproofBot")
    r = client.post("/api/telegram/code").json()
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", r["code"]) and r["deep_link"] == f"https://t.me/BaitproofBot?start={r['code']}" and r["expires_in"] == 600
    assert client.get("/api/telegram/status").json() == {"linked": 0}
    assert handlers.on_link(901, r["code"]).startswith("✅")
    assert client.get("/api/telegram/status").json() == {"linked": 1}
    assert "Connected" in client.get("/records").text
    assert client.post("/api/telegram/unlink").json() == {"unlinked": 1} and client.get("/api/telegram/status").json() == {"linked": 0}


def test_without_a_bot_username_the_page_still_explains_how(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
    assert client.post("/api/telegram/code").json()["deep_link"] == ""


def test_code_creation_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(deps, "RATE", 2)
    deps.HITS.clear()
    assert [client.post("/api/telegram/code").status_code for _ in range(3)] == [200, 200, 429]


# ---------------------------------------------------------------- the full round trip: web profile <-> Telegram chat
def test_a_telegram_check_appears_in_the_web_records_of_the_linked_profile(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    web, other = TestClient(app), TestClient(app)
    web.get("/")
    other.get("/")
    code = web.post("/api/telegram/code").json()["code"]
    assert handlers.on_link(555, code).startswith("✅ Linked")
    reply = handlers.on_text(555, SCAM)  # the person forwards a scam to the bot
    assert reply.startswith("🚨")
    rows = rec_ids(web.get("/records").text)
    assert len(rows) == 1
    page = web.get("/records").text
    assert "Telegram" in page and "Scam" in page and "412 345" not in page
    assert rec_ids(other.get("/records").text) == []  # a different visitor sees nothing of it
    # ...and the bot's /history sees the same record, and the checks went into the SAME practice profile
    assert "via telegram" in handlers.on_history(555)
    assert web.get("/api/map").json()["tactics"]  # mastery lives in the shared profile


def test_an_unlinked_chat_keeps_its_own_private_history(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    web = TestClient(app)
    web.get("/")
    handlers.on_text(777, SCAM)  # never linked
    assert rec_ids(web.get("/records").text) == []
    assert "via telegram" in handlers.on_history(777)


def test_after_unlinking_new_telegram_checks_no_longer_reach_the_web_profile(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    web = TestClient(app)
    web.get("/")
    handlers.on_link(555, web.post("/api/telegram/code").json()["code"])
    handlers.on_text(555, SCAM)
    web.post("/api/telegram/unlink")
    handlers.on_text(555, SCAM + " one more time")
    assert len(rec_ids(web.get("/records").text)) == 1
