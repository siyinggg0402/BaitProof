from bot import handlers
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
