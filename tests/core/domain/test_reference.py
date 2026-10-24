"""The reference list (data/reference/entries.json): scam scripts that official bodies have named, matched exactly and used as evidence. It must be well formed and
dated, translated, quiet on every ordinary and advisory message we have, and it must name its source when it speaks."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.domain import reference as R
from core.domain.schemas import Verdict as V
from core.domain.tactics import TACTICS
from core.lang import i18n
from core.pipelines.check import check_message
from scripts import common
from web.main import app

SG_POLICE = "This is Inspector Lim from the Singapore Police. You are under investigation for money laundering. Transfer your savings to a safe account now, and call 6789 1234."
DIGITAL_ARREST = "CBI officer here. Your parcel has drugs and you are under digital arrest. Stay on this video call and pay Rs 50,000 bail now."


def offline(text, lang="en"):
    with common.offline(net=True):
        return check_message(text, store=False, log=False, lang=lang)


def test_every_entry_is_well_formed_dated_and_sourced():
    assert len(R.entries()) >= 6
    ids = [e.id for e in R.entries()]
    assert len(set(ids)) == len(ids)
    for e in R.entries():
        assert e.tactic in TACTICS and e.strength in ("weak", "medium", "strong"), e.id
        assert e.source.startswith("https://") and e.publisher and e.region in ("SG", "MY", "IN", "ID"), e.id
        assert date.fromisoformat(e.checked) >= date(2026, 10, 1), e.id                  # (re-check the sources before each release, and change the date when you do)
        assert len(e.claim) <= 200 and e.variants and all(v for v in e.variants), e.id   # (the ledger keeps 240 characters: a claim must fit whole)
        assert re.search(r"\(\d{4}\)|\(\w[\w ,]*\d{4}\)|\(997\)", e.claim), f"{e.id}: the claim should say who said it and when"


@pytest.mark.parametrize("lang", ["zh", "ms", "ta"])
def test_every_claim_and_the_label_are_translated(lang):
    table = {"zh": i18n.ZH, "ms": i18n.MS, "ta": i18n.TA}[lang]
    for e in R.entries():
        assert e.claim in table and table[e.claim] != e.claim, e.id
        assert len(i18n.tr(e.claim, lang)) <= 240, e.id
    assert "Official warning" in table


def test_a_named_script_matches_only_when_the_message_also_asks_for_something():
    assert [e.id for e, _ in R.matches(SG_POLICE, {"pay", "call"})] == ["sg-official-impersonation", "sg-safety-account"]
    assert R.matches(SG_POLICE, set()) == []                                            # nothing asked: nothing to warn about
    assert [e.id for e, _ in R.matches(DIGITAL_ARREST, {"pay"})] == ["in-digital-arrest"]


@pytest.mark.parametrize("text", [
    "Police reminder: never transfer money to a safe account, whoever asks.",
    "Scam alert: officials will not ask you to share Singpass details. Do not click links.",
    "Waspada! Jangan pindahkan wang ke akaun selamat walaupun pegawai polis meminta.",
    "请勿将钱转入所谓的“安全账户”，警方不会这样要求。",
])
def test_an_advisory_that_quotes_the_scam_does_not_match(text):
    assert R.matches(text, {"pay", "call"}) == []


def test_the_other_scripts_match_in_their_own_words():
    assert [e.id for e, _ in R.matches("Pinjaman Rp 5 juta tanpa agunan, cair dalam 10 menit. Bayar biaya admin dulu.", {"pay"})] == ["id-illegal-lender"]
    assert [e.id for e, _ in R.matches("Saya dari NSRC. Anda terlibat dalam kes penipuan, sila hubungi 03-2345 6789.", {"call"})] == ["my-nsrc-impersonation"]
    assert [e.id for e, _ in R.matches("您好，我是新加坡警察，您涉嫌洗黑钱，请把存款转入安全户口。", {"pay"})][:1] == ["sg-official-impersonation"]
    assert [e.id for e, _ in R.matches("DBS: your account is locked, verify at dbs-login.top", {"click"}, link_unverified=True)] == ["sg-bank-link"]
    assert R.matches("DBS: your account is locked, verify at dbs.com.sg", {"click"}, link_unverified=False) == []        # a link we verified is the bank's own: no warning


def test_it_becomes_evidence_that_names_its_source_and_is_not_the_models_opinion():
    r = offline(SG_POLICE)
    ref = [e for e in r.evidence if e.kind == "reference"]
    assert ref and all(e.supports == "scam" and e.claim.startswith(("Singapore Police and", "MAS")) and e.quote for e in ref)
    assert r.verdict in (V.SCAM, V.LIKELY_SCAM)
    zh = offline(SG_POLICE, "zh")
    assert any(e.kind == "reference" and "新加坡警察部队" in e.claim for e in zh.evidence)


def test_the_result_page_labels_it_an_official_warning_in_every_language():
    for lang, label in (("en", "Official warning"), ("zh", "官方警示"), ("ms", "Amaran rasmi"), ("ta", "அதிகாரப்பூர்வ எச்சரிக்கை")):
        c = TestClient(app)
        c.cookies.set("lang", lang)
        assert label in c.post("/check", data={"message": SG_POLICE}).text, lang


def test_it_stays_silent_on_every_ordinary_and_advisory_message_we_have():
    from scripts.eval.languages import SETS

    spoke = []
    for name in ("en-hard3", "en-heldout", "en-sg", "zh-holdout", "zh-fresh", "ms-holdout", "ms-fresh", "id-dev", "id-holdout", "id-fresh", "ta-seeds", "ta-dev", "ta-holdout"):
        for is_scam, tag, text in SETS[name]():
            if not is_scam and any(e.kind == "reference" for e in offline(text).evidence):
                spoke.append(f"{name}:{tag}")
    assert not spoke, spoke
