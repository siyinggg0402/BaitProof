import pytest

from core.domain.schemas import Verdict as V
from core.pipelines import check, train
from core.pipelines.check import check_message
from core.storage import library
from tests.data.en import smoke as M


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


@pytest.mark.parametrize("text", [
    "a" * 50_000, "<script>alert(1)</script> pay now", "\x00\x00 hello", "💸" * 500,
    "https://" + "a" * 3000 + ".com/x", "1" * 300, "  \n\t ".join(["word"] * 2000),
])
def test_check_never_crashes_on_weird_input(text):
    r = check_message(text, store=False)
    assert r.verdict and r.headline
