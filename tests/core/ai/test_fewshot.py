import pytest

from core.ai import fewshot
from core.domain import intents
from core.domain.tactics import TACTICS
from core.pipelines.check import analysis, intent as intent_stage
from core.pipelines.check.ingest import ingest
from core.pipelines.check.tools import Findings
from core.storage import library
from tests.data.en import hard_1, hard_2, hard_3, heldout_1, heldout_2


def _norm(t):
    return " ".join(t.lower().split())


# ---------------------------------------------------------------- the bank itself
def test_bank_is_valid():
    bank = fewshot.load_authored()
    assert len(bank) >= 60 and len({e.id for e in bank}) == len(bank)
    for e in bank:
        assert e.verdict in ("scam", "likely_scam", "unsure", "safe") and e.text and e.why
        assert e.purpose in intents.PURPOSES, e.id
        assert all(t in TACTICS for t in e.tactics), e.id
        assert (e.verdict == "safe") == (not e.tactics) or e.verdict in ("unsure", "likely_scam", "scam")  # a safe example names no tricks
    assert {e.verdict for e in bank} == {"scam", "likely_scam", "unsure", "safe"}


def test_bank_texts_do_not_leak_from_any_evaluation_set():
    """The bank is authored independently. If a bank message also sat in an evaluation set, that measurement would be contaminated."""
    evalset = {_norm(e["text"]) for e in library.seed_examples()}
    for ds in (heldout_1, heldout_2):
        evalset |= {_norm(t[0] if isinstance(t, tuple) else t) for t in ds.SCAMS + ds.LEGIT}
    for ds in (hard_1, hard_2, hard_3):
        evalset |= {_norm(t[1]) for t in ds.SCAMS + ds.LEGIT}
    overlap = [e.id for e in fewshot.load_authored() if _norm(e.text) in evalset]
    assert not overlap, overlap


# ---------------------------------------------------------------- retrieval
@pytest.mark.parametrize("query,expected_text_fragment", [
    ("Congrats 2 mobile 3G Videophones R yours. call 09063458120 now! videochat wid ur mates 150ppm", "Text GIRL to 85022"),
    ("Your credit card has been temporarily blocked. Reactivate by verifying your PIN.", "frozen"),
    ("Your code is 774411. Do not share it.", "verification code is 482913"),
])
def test_retrieval_finds_structurally_similar_examples(query, expected_text_fragment):
    assert any(expected_text_fragment in e.text for e in fewshot.retrieve(query)), [e.text[:40] for e in fewshot.retrieve(query)]


def test_a_message_is_never_retrieved_as_its_own_example():
    own = fewshot.load_authored()[0].text
    assert all(_norm(e.text) != _norm(own) for e in fewshot.retrieve(own))
    assert all(_norm(e.text) != _norm(own.upper() + "  ") for e in fewshot.retrieve(own.upper() + "  "))  # case / spacing don't sneak it in


def test_gibberish_retrieves_nothing_rather_than_noise():
    assert fewshot.retrieve("zzqx plorb vnn kk") == []


def test_examples_from_both_sides_of_the_verdict_are_shown_when_both_are_relevant():
    got = fewshot.retrieve("Your card payment of 18.40 was made. If you don't recognise it call us")
    assert {e.verdict in fewshot.SCAMMY for e in got} == {True, False}


def test_numbers_links_and_short_codes_are_normalised_so_structure_matches():
    a = fewshot.features("Text WIN to 80466 now, 50p per msg")
    b = fewshot.features("Text CLAIM to 81010 now, 20p per msg")
    assert "shortcodex" in a and "pricex" in a and set(a) & set(b) >= {"shortcodex", "pricex", "text"}
    assert "urlx" in fewshot.features("pay at dpd-fee.top today") and "tldtop" in fewshot.features("pay at dpd-fee.top today")


# ---------------------------------------------------------------- the user's own circle becomes part of the bank (the flywheel)
def test_scams_the_users_circle_forwarded_become_examples(monkeypatch):
    from core.pipelines.check import check_message

    check_message("Hi from the neighbourhood watch: buy 4 gift cards and send me the numbers please. Don't tell anyone.", store=True, log=False)
    assert library.user_examples()
    got = fewshot.retrieve("Neighbourhood watch here, please buy gift cards and send me the card numbers, keep it quiet")
    assert any(e.source == "library" for e in got)


# ---------------------------------------------------------------- prompt assembly
def test_block_shows_verdict_purpose_tricks_and_why():
    b = fewshot.block(fewshot.retrieve("Your card has been frozen. Verify your PIN now."))
    assert b.startswith("SIMILAR LABELLED EXAMPLES") and "-> scam | urgent-account-warning" in b and "otp-credential-phish" in b
    assert fewshot.block([]) == ""


def test_the_analysis_prompt_includes_examples_when_enabled_and_is_off_by_default(monkeypatch):
    ing = ingest("Your debit card has been blocked. Reactivate by verifying your PIN.")
    it = intent_stage._heuristic(ing)
    f = Findings(hosts=list(ing.entities.hosts))
    assert "SIMILAR LABELLED EXAMPLES" not in analysis.build_user(ing, it, f)  # off by default
    assert "SIMILAR LABELLED EXAMPLES" in analysis.build_user(ing, it, f, examples=True)
    monkeypatch.setenv("BAITPROOF_FEWSHOT", "1")
    assert "SIMILAR LABELLED EXAMPLES" in analysis.build_user(ing, it, f)
    assert "SIMILAR LABELLED EXAMPLES" not in analysis.build_user(ing, it, f, examples=False)


def test_a_broken_bank_never_breaks_a_check(monkeypatch):
    from core.domain.schemas import Verdict
    from core.pipelines.check import check_message

    from core.storage import library

    def down():
        raise RuntimeError("db down")

    monkeypatch.setattr(library, "user_examples", down)
    assert fewshot.load_library() == []
    assert check_message("Lunch on Sunday?", store=False, log=False).verdict in Verdict
