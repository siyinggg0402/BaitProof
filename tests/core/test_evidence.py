from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message
from core.pipelines.check.evidence import Ledger
from core.storage import library


def test_ledger_dedupes_and_weighs_model_evidence_less():
    L = Ledger()
    a = L.add("rule", "pattern", "scam", "medium", "x", "within 24 hours", "urgency-pressure")
    assert L.add("rule", "pattern", "scam", "medium", "x", "Within 24 hours", "urgency-pressure") is None  # same fact
    L.add("model", "analysis", "scam", "medium", "y", "pay now", "advance-fee")
    assert a.id == "e1" and L.weight("scam") == 2.0 + 1.0  # model medium counts half
    assert L.tactic_ids() == ["urgency-pressure", "advance-fee"] and len(L.independent_scam()) == 1


def test_tactic_hit_prefers_strongest_independent_evidence():
    L = Ledger()
    L.add("model", "analysis", "scam", "strong", "model says", "q1", "lookalike-link")
    L.add("tool", "domain_check", "scam", "medium", "tool says", "evil.xyz", "lookalike-link")
    (hit,) = L.tactic_hits()
    assert hit.why == "tool says" and hit.quote == "evil.xyz"


def test_model_only_evidence_is_never_hard_and_never_feeds_the_flywheel(monkeypatch):
    from core.ai import llm

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: (
        {"asks": [], "pressure": False} if "diagnose what a message wants" in system else
        {"verdict": "scam", "tactics": [{"id": "advance-fee", "quote": "small fee", "why": "asks for a fee"}], "the_tell": "t", "action": "a"}))
    r = check_message("Please send the small fee so we can book the hall.")
    assert r.verdict == V.LIKELY_SCAM and r.confidence == "medium"  # one grounded model flag: not 'scam', not hard
    assert not r.added_to_training and library.user_examples() == []  # model-only: kept out of training
    assert any("independent evidence" in s.detail for s in r.trace if s.stage == "flywheel")


def test_result_cites_its_evidence():
    r = check_message("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz/track")
    assert r.verdict == V.SCAM
    kinds = {(e.kind, e.source) for e in r.evidence}
    assert ("tool", "domain_check") in kinds and ("rule", "pattern") in kinds
    assert any(e.strength == "strong" and e.kind == "tool" for e in r.evidence)
    assert all(e.id.startswith("e") for e in r.evidence) and all(e.claim for e in r.evidence)


def test_safe_verdict_is_backed_by_reassuring_evidence():
    r = check_message("Lunch on Sunday at ours? Everyone's coming around 1.")
    assert r.verdict == V.SAFE and any(e.supports == "safe" for e in r.evidence)


def test_evidence_is_logged_without_claims_or_quotes():
    import json
    from core.obs import logger

    check_message("Pay with gift cards today, secret-token-777")
    raw = open(logger.path()).read()
    ev = json.loads(raw)["evidence"]
    assert ev and set(ev[0]) == {"kind", "source", "supports", "strength", "tactic"}
    assert "secret-token-777" not in raw and "gift cards" not in raw


def test_web_page_shows_evidence_cards():
    from fastapi.testclient import TestClient
    from web.main import app

    html = TestClient(app).post("/check", data={"message": "DHL parcel on hold. Pay within 24 hours: dhl-fee-pay.xyz"}).text
    assert "The evidence (" in html and "Red flag" in html and "Checked" in html
