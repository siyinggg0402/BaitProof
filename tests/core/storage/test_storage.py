from datetime import timedelta
import sqlite3

from core.domain.schemas import CheckResult, TacticHit, Verdict
from core.domain.tactics import TACTICS
from core.storage import db, library, model
from core.storage import history, links


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


def result(cid="abc123def456", verdict=Verdict.SCAM, **kw):
    return CheckResult(verdict=verdict, headline="🚨 SCAM. Don't pay.", tell="a giveaway", action="do this", confidence="high", check_id=cid,
                       tactics=[TacticHit(id="urgency-pressure")], **kw)


# ---------------------------------------------------------------- history
def test_a_record_keeps_the_verdict_tricks_and_giveaway_but_never_the_raw_message():
    raw = "Call +61 412 345 678 or mail bob@example.com about secret-token-777, pay at https://evil.xyz/a?token=SECRET"
    history.add(result(), "telegram", raw)
    (r,) = history.list_checks()
    assert r["verdict"] == "scam" and r["tactics"] == ["urgency-pressure"] and r["channel"] == "telegram" and r["tell"] == "a giveaway"
    for leaked in ("412", "bob@", "SECRET", "token="):
        assert leaked not in r["preview"]
    assert "evil.xyz" in r["preview"]  # a scam domain is kept: it isn't personal and it is what makes the record recognisable
    dump = " ".join(sqlite3.connect(db.db_path()).iterdump())
    assert "bob@example.com" not in dump and "+61 412 345 678" not in dump and "SECRET" not in dump


def test_previews_are_capped_and_can_be_switched_off():
    history.add(result("aaaaaaaaaaaa"), "web", "word " * 100)
    assert len(history.list_checks()[0]["preview"]) <= history.PREVIEW_LEN
    history.set_setting("store_preview", "0")
    history.add(result("bbbbbbbbbbbb"), "web", "hello there")
    assert history.list_checks(1)[0]["preview"] == ""


def test_the_same_check_is_recorded_once_and_unknown_channels_are_ignored():
    history.add(result(), "web", "x")
    history.add(result(), "web", "x")
    history.add(result("ffffffffffff"), "carrier-pigeon", "x")
    history.add(CheckResult(verdict=Verdict.SAFE, headline="h"), "web", "x")  # no check id
    assert len(history.list_checks()) == 1


def test_only_the_newest_records_are_kept(monkeypatch):
    monkeypatch.setattr(history, "KEEP", 3)
    for i in range(6):
        history.add(result(f"{i:012x}"), "web", f"m{i}")
    assert len(history.list_checks()) == 3


def test_delete_filter_and_stats():
    history.add(result("000000000001"), "web", "a")
    history.add(result("000000000002", Verdict.SAFE), "telegram", "b")
    history.add(result("000000000003"), "telegram", "c")
    assert [r["channel"] for r in history.list_checks(channel="telegram")] == ["telegram", "telegram"]
    assert len(history.list_checks(verdict="safe")) == 1
    s = history.stats()
    assert s["total"] == 3 and s["flagged"] == 2 and s["by_channel"] == {"web": 1, "telegram": 2} and s["top_tricks"][0] == ("urgency-pressure", 3)
    assert history.delete("000000000001") and not history.delete("000000000001")
    assert history.delete_all() == 2 and history.list_checks() == []


# ---------------------------------------------------------------- linking
def test_codes_are_short_unambiguous_and_one_use():
    code = links.new_code("p1")
    assert len(code) == 6 and set(code) <= set(links.ALPHABET) and not set(code) & set("0O1I")
    assert links.redeem(code.lower() + " ", 111) == "p1"  # forgiving about case and spaces
    assert links.redeem(code, 222) is None  # already used
    assert links.profile_for_chat(111) == "p1" and links.profile_for_chat(222) is None


def test_a_new_code_cancels_the_previous_one_for_that_profile():
    a, b = links.new_code("p1"), links.new_code("p1")
    assert links.redeem(a, 1) is None and links.redeem(b, 1) == "p1"


def test_wrong_malformed_and_expired_codes_fail(monkeypatch):
    assert links.redeem("ZZZZZZ", 1) is None and links.redeem("", 1) is None and links.redeem("12", 1) is None and links.redeem("ABC0OI", 1) is None
    code = links.new_code("p1")
    real = links.time.time
    monkeypatch.setattr(links.time, "time", lambda: real() + links.TTL + 5)
    assert links.redeem(code, 1) is None


def test_relinking_a_chat_moves_it_and_unlink_removes_it():
    links.redeem(links.new_code("p1"), 5)
    links.redeem(links.new_code("p2"), 5)
    assert links.profile_for_chat(5) == "p2" and links.chats_for("p1") == 0 and links.chats_for("p2") == 1
    assert links.unlink_profile("p2") == 1 and links.profile_for_chat(5) is None
    links.redeem(links.new_code("p3"), 6)
    assert links.unlink_chat(6) and not links.unlink_chat(6)


def test_a_profile_can_have_more_than_one_chat():
    links.redeem(links.new_code("p1"), 1)
    links.redeem(links.new_code("p1"), 2)
    assert links.chats_for("p1") == 2


def test_current_profile_is_local_without_multiuser(monkeypatch):
    assert links.current_profile() == links.LOCAL
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    db.set_profile("a" * 32)
    assert links.current_profile() == "a" * 32
    db.set_profile(None)
    assert links.current_profile() == links.LOCAL
