import pytest
from fastapi.testclient import TestClient

from bot import handlers
from core.pipelines.check import check_message
from core.storage import model


def test_bot_check_and_score(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    out = handlers.on_text(111, "Buy 4 gift cards and send me the numbers please.")
    assert out.startswith("🚨") and "giveaway" in out and "Added to your practice" in out
    assert "score" in handlers.on_score(111).lower()
    # a different chat has its own, untouched profile
    assert "Weakest" not in handlers.on_score(222) and model.baitproof_score() == 0
    assert handlers.on_text(111, "   ") == "Send me the message you want checked."


def test_nudge_only_when_due(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert handlers.nudge_text(5) is None
    handlers.bind_chat(5)
    model.record_result("urgency-pressure", "incorrect")  # incorrect => due immediately
    assert "due" in handlers.nudge_text(5)


@pytest.mark.parametrize("text", [
    "a" * 50_000, "<script>alert(1)</script> pay now", "\x00\x00 hello", "💸" * 500,
    "https://" + "a" * 3000 + ".com/x", "1" * 300, "  \n\t ".join(["word"] * 2000),
])
def test_check_never_crashes_on_weird_input(text):
    r = check_message(text, store=False)
    assert r.verdict and r.headline


def test_web_rejects_empty_and_escapes_html():
    from web.main import app

    c = TestClient(app)
    assert c.post("/check", data={"message": "   "}).status_code == 400
    page = c.post("/check", data={"message": "<img src=x onerror=alert(1)> pay now by gift card"}).text
    assert "<img src=x" not in page and "&lt;img" in page
    assert c.post("/api/train/answer", json={"session": "nope", "item_id": "x", "choice": 0}).status_code == 404
    assert c.get("/challenge/doesnotexist").status_code == 404


def test_due_count_and_pill():
    from web.main import app

    model.record_result("urgency-pressure", "incorrect")
    assert model.baitproof_score() >= 0 and model.resilience_map()["due"] == 1
    assert "due for a refresher" in TestClient(app).get("/").text
