from datetime import timedelta

from core.storage import db, library, model
from core.domain.tactics import TACTICS


def test_seed_bank_is_valid():
    for e in library.seed_examples():
        assert all(t in TACTICS for t in e["tactics"])
        if e["tell_phrase"]:
            assert e["tell_phrase"] in e["text"], e["id"]
    covered = {t for e in library.seed_examples() for t in e["tactics"]}
    assert covered == set(TACTICS)


def test_redaction_strips_pii():
    out = library.redact("Call +1 (555) 123-4567 or mail bob@x.com, see https://evil-pay.xyz/a?token=SECRET123")
    assert "555" not in out and "bob@" not in out and "SECRET123" not in out and "evil-pay.xyz" in out


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


def test_due_count():
    model.record_result("urgency-pressure", "incorrect")  # a miss is due immediately
    assert model.resilience_map()["due"] == 1
