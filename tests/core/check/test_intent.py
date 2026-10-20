import pytest

from core.ai import llm
from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message, intent, scenarios
from core.pipelines.check.ingest import ingest
from core.storage import library
from tests.data import heldout_1, heldout_2


def dx(text):
    return intent.diagnose(ingest(text))


@pytest.mark.parametrize("text,script", [
    ("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours: dhl-fee-pay.xyz/track", "parcel-fee"),
    ("Hi grandma it's me, in trouble and stuck abroad. Please wire $600 right now, don't tell Mom.", "family-emergency"),
    ("Microsoft Support: your computer has a virus. Call now and install AnyDesk so our technician can fix it.", "tech-support"),
    ("Earn $30 per task, 20 minutes a day. First deposit $50 to activate your work account.", "job-task"),
    ("Your Prime membership renews today for $349.99. Call 1-855-555-0101 to cancel and get a refund.", "subscription-renewal"),
])
def test_known_scam_scripts_are_recognised(text, script):
    assert dx(text).scenario == script


@pytest.mark.parametrize("text", [
    "Your package from the local bookshop was delivered to your front door at 2:14pm.",
    "Your bank: a new statement is ready. Sign in through our official app. We will never ask for your PIN or full password.",
    "Reminder: your appointment is tomorrow at 10:30am. Reply C to confirm or call us on the number on your appointment card.",
    "Hi Dad, can you transfer me $50 for groceries? I'll pay you back at the weekend.",
])
def test_normal_messages_match_no_script_and_raise_no_mismatch(text):
    it = dx(text)
    assert it.scenario == "" and not it.mismatches


def test_scripts_cover_seed_and_heldout_scams_but_never_legit():
    scams = [e["text"] for e in library.seed_examples() if e["is_scam"]]
    legit = [e["text"] for e in library.seed_examples() if not e["is_scam"]]
    for ds in (heldout_1, heldout_2):
        scams += [t[0] if isinstance(t, tuple) else t for t in ds.SCAMS]
        legit += list(ds.LEGIT)
    hit = sum(1 for t in scams if scenarios.detect(t)[0])
    assert hit / len(scams) >= 0.9, hit / len(scams)
    assert [t[:40] for t in legit if scenarios.detect(t)[0]] == []


def test_pressure_kinds_identity_and_mismatch():
    it = dx("This is the IRS. A warrant will be issued unless you pay within 24 hours with gift cards. Do not tell anyone.")
    assert {"deadline", "threat", "secrecy"} <= it.pressure_kinds
    assert it.claimed_kind == "authority" and "irs" in it.claimed
    texts = [m[0] for m in it.mismatches]
    assert any("payment by gift card" in t for t in texts) and any("keep it secret" in t for t in texts)


def test_family_asking_for_money_is_only_suspicious_with_extra_signals():
    assert not dx("Hi Mum, can you lend me $40 until Friday?").mismatches
    assert dx("Mum, new number, my phone broke. Send $300 now please.").mismatches


def test_script_match_is_itself_a_red_flag_and_cites_evidence():
    r = check_message("Congratulations! You won a $500 voucher. Claim it, just pay the $4.95 shipping fee at bit.ly/win")
    assert r.verdict in (V.SCAM, V.LIKELY_SCAM)
    ev = [e for e in r.evidence if e.source.startswith("scenario:")]
    assert ev and ev[0].kind == "intent" and "scam script" in ev[0].claim


def _fake(monkeypatch, intent_out):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: intent_out)


def test_model_identity_must_appear_in_the_message(monkeypatch):
    _fake(monkeypatch, {"asks": ["pay"], "pressure": ["deadline"], "claimed_identity": {"name": "Barclays Bank", "kind": "organisation"}})
    assert dx("Please settle the invoice by Friday.").claimed == ""  # invented, ignored
    _fake(monkeypatch, {"asks": [], "pressure": [], "claimed_identity": {"name": "Acme Bank", "kind": "organisation"}})
    it = dx("Message from Acme Bank about your statement.")
    assert it.claimed == "acme bank" and it.claimed_kind == "organisation" and it.used_ai


def test_model_cannot_remove_rule_findings_and_pressure_kinds_are_validated(monkeypatch):
    _fake(monkeypatch, {"asks": [], "pressure": ["panic", "threat"], "claimed_identity": "", "scenario": ""})
    it = dx("Pay the $1.99 fee within 24 hours: dhl-fee-pay.xyz")
    assert "pay" in it.asks and "click" in it.asks and "deadline" in it.pressure_kinds  # rules kept
    assert "threat" not in it.pressure_kinds and "panic" not in it.pressure_kinds  # no threatening words in the text: the model's claim is rejected
    _fake(monkeypatch, {"asks": [], "pressure": ["threat", "deadline"]})
    it2 = dx("Pay the fee or your parcel will be returned.")
    assert {"threat", "deadline"} <= it2.pressure_kinds  # consequence wording backs both


def test_rules_vs_model_scenario_disagreement_is_recorded_for_the_loop(monkeypatch):
    _fake(monkeypatch, {"asks": [], "pressure": [], "scenario": "romance"})
    it = dx("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours: dhl-fee-pay.xyz/track")
    assert it.scenario == "parcel-fee" and it.disagreements and "romance" not in it.scenario.lower()
    _fake(monkeypatch, {"asks": [], "pressure": [], "scenario": "investment"})
    it2 = dx("Hello, quick question about the weekend.")
    assert it2.scenario == "" and it2.model_scenario == "investment" and not it2.disagreements
    _fake(monkeypatch, {"asks": [], "pressure": [], "scenario": "not-a-real-script"})
    assert dx("Hello, quick question about the weekend.").model_scenario == ""


def test_neighbouring_scripts_are_not_a_disagreement(monkeypatch):
    _fake(monkeypatch, {"asks": [], "pressure": [], "scenario": "billing-update"})
    it = dx("Your Prime membership renews today for $349.99. Call 1-855-555-0101 to cancel and get a refund.")
    assert it.scenario == "subscription-renewal" and it.disagreements == []  # same family: no noise for the loop


def test_a_bare_time_window_is_not_pressure(monkeypatch):
    _fake(monkeypatch, {"asks": [], "pressure": ["deadline"]})
    assert dx("Use code 482913 to log in. It expires in 15 minutes. If you didn't request this, ignore this message.").pressure_kinds == set()
    assert "deadline" in dx("Your parcel will be returned unless you pay within 24 hours.").pressure_kinds
