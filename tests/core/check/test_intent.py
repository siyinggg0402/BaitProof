import pytest

from core.ai import llm
from core.ai.prompts import CHECK_SYSTEM, INTENT_SYSTEM
from core.domain import intents
from core.domain.schemas import Verdict as V
from core.pipelines.check import analysis, check_message, intent, scenarios
from core.pipelines.check import intent as intent_stage
from core.pipelines.check.ingest import ingest
from core.pipelines.check.tools import Findings
from core.storage import library
from tests.data.en import heldout_1, heldout_2


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


# ---------------------------------------------------------------- the catalogue itself
def test_catalogue_is_complete_and_consistent():
    assert len(intents.PURPOSES) >= 18 and "other" in intents.PURPOSES
    assert set(intents.PRIORITY_RISKY + intents.PRIORITY_NORMAL) == set(intents.PURPOSES)
    for p in intents.PURPOSES.values():
        assert p.risk in ("benign", "neutral", "risky") and p.genuine and p.scam and p.label
        assert not p.clearable or p.risk == "benign"  # only plainly ordinary purposes may ever be cleared without the model
    assert {p.id for p in intents.PURPOSES.values() if p.clearable} == {"one-time-code", "delivery-update", "appointment-booking"}
    assert all(intents.PURPOSES[i].risk == "risky" for i in intents.PRIORITY_RISKY)


def test_every_purpose_reaches_both_prompts_so_the_model_chooses_from_the_same_list():
    for pid in intents.PURPOSES:
        assert pid in CHECK_SYSTEM and pid in INTENT_SYSTEM
    for bad in ("Be decisive", 'Do NOT answer "unsure" just because'):  # the old contradictory patches are gone
        assert bad not in CHECK_SYSTEM


def test_guidance_names_the_genuine_and_the_scam_form():
    g = intents.guidance("delivery-update")
    assert "GENUINE" in g and "SCAM" in g and "fee" in g and intents.guidance("other") == "" and intents.guidance("nope") == ""


# ---------------------------------------------------------------- rule classification
@pytest.mark.parametrize("text,purpose", [
    ("Your code is 482913. It expires in 10 minutes. Never share it.", "one-time-code"),
    ("Reply with the 6-digit code we just sent to keep your account.", "request-secret"),
    ("You have won 1000 pounds! Text CLAIM to 81010", "request-payment"),  # a short-code text is a paid reply
    ("Congratulations, you won a $500 voucher. Claim at bit.ly/win and pay $4.95 shipping", "request-payment"),
    ("Hi, is this Margaret? I got your number from Linda.", "first-contact-opener"),
    ("Your Uber ride has arrived. Look for a white Toyota.", "delivery-update"),
    ("Reminder: dentist appointment tomorrow at 3pm.", "appointment-booking"),
    ("Please install AnyDesk so our technician can fix your computer", "request-install-access"),
    ("Hey, I'm outside!", "social-chat"),
    ("Your debit card has been blocked. Reactivate by verifying your PIN.", "urgent-account-warning"),  # the alarm form, no link needed
    ("Account hacked! Open the app now to secure it.", "urgent-account-warning"),
    ("Your cloud storage is full. Please click to free up space.", "urgent-account-warning"),
])
def test_rule_purpose(text, purpose):
    assert dx(text).purpose == purpose


# ---------------------------------------------------------------- the model must choose from the list, and the text must support it
def test_a_made_up_purpose_is_ignored(monkeypatch):
    _fake(monkeypatch, {"purpose": "friendly-scam-chat", "asks": []})
    assert dx("Lunch on Sunday?").model_purpose == ""


def test_a_purpose_the_text_cannot_support_is_ignored(monkeypatch):
    _fake(monkeypatch, {"purpose": "one-time-code", "asks": []})
    assert dx("Lunch on Sunday at ours?").model_purpose == ""  # no code anywhere in the message
    _fake(monkeypatch, {"purpose": "request-payment", "asks": []})
    assert dx("Lunch on Sunday at ours?").model_purpose == ""  # nothing asks for money
    _fake(monkeypatch, {"purpose": "callback-request", "asks": ["call"]})
    assert dx("Please call us about your booking tomorrow").model_purpose == ""  # a call ask, but no number to call


def test_a_supported_choice_is_kept_and_a_risk_class_disagreement_is_recorded(monkeypatch):
    _fake(monkeypatch, {"purpose": "offer-job-or-investment", "asks": []})
    it = dx("We pay 200 a day for simple tasks, add me on Telegram")
    assert it.model_purpose == "offer-job-or-investment"
    _fake(monkeypatch, {"purpose": "work-logistics", "asks": []})
    it2 = dx("Pay the 1.99 fee within 24 hours: dhl-fee-pay.xyz")  # rules: risky; model: ordinary
    assert it2.model_purpose == "" or it2.disagreements  # unsupported ordinary claim is dropped, or the clash is recorded for the loop


def test_the_analysis_prompt_is_given_the_matching_purpose_guidance():
    ing = ingest("Your parcel is on hold. Pay 1.45 at dpd-fee.top")
    it = intent_stage._heuristic(ing)
    shown = analysis.build_user(ing, it, Findings(hosts=list(ing.entities.hosts)))
    assert "PURPOSE GUIDANCE" in shown and "SCAM version" in shown and f"purpose={it.purpose}" in shown


# ---------------------------------------------------------------- clearing without a model: strictly ordinary messages only
@pytest.mark.parametrize("text", [
    "Your verification code is 771204. It expires in 10 minutes. Never share this code.",
    "Your order has shipped and should arrive Thursday.",
    "Reminder: your dentist appointment is Tuesday at 3pm.",
    "Your table for 4 at Luigi's is confirmed for Friday at 7pm. Reply C to cancel.",
])
def test_plainly_ordinary_messages_can_be_cleared_by_rules_alone(text):
    r = check_message(text, store=False, log=False)
    assert r.verdict == V.SAFE and any(e.source.startswith("purpose:") for e in r.evidence)


@pytest.mark.parametrize("text", [  # the four real scams that slipped through the first, looser version
    'Win the newest "Harry Potter and the Order of the Phoenix . reply HARRY, answer 5 questions - chance to be the first among readers!',
    "RECPT 1/3. You have ordered a Ringtone. Your order is being processed...",
    "Your lottery ticket won BDT 1,00,000. Send your details for prize delivery.",
    "Your package delivery is delayed. Track now at this fake link.",
])
def test_real_scams_that_mention_orders_and_deliveries_are_never_cleared(text):
    assert check_message(text, store=False, log=False).verdict != V.SAFE


@pytest.mark.parametrize("text", [
    "Your verification code is 771204. Reply with it to confirm.",   # asks for the code back
    "Your order has shipped. Track it at https://shipping-update.top/x",  # a link
    "Your order has shipped. Call 0161 555 0199 to arrange it.",      # a number to call
    "Your appointment is tomorrow at 3pm. Pay the 20 deposit now.",   # asks for money
    "Your parcel has been delivered. Click here to claim your refund.",
])
def test_clearable_purposes_are_not_cleared_when_anything_risky_is_present(text):
    assert check_message(text, store=False, log=False).verdict != V.SAFE



@pytest.mark.parametrize("text", [
    "Netflix: your payment method is expiring soon. You can update it in your account settings.",
    "Your password was just changed. If you didn't do this, reset it from the sign-in page.",
    "Apple: Your Apple ID was used to sign in on a new device. If this was you, no action is needed.",
    "Your parcel has been delivered to your front porch at 2:41 PM.",
])
def test_ordinary_notices_are_not_read_as_the_alarm_form(text):
    assert dx(text).purpose != "urgent-account-warning"


def test_a_risky_purpose_is_never_cleared_as_safe_even_when_the_model_says_safe(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: ({"asks": [], "pressure": []} if "classify what a message is FOR" in system else
                                                                      {"concern": False} if "second reviewer" in system else
                                                                      {"verdict": "safe", "tactics": [], "the_tell": "", "action": ""}))
    for text in ("Your debit card has been blocked. Reactivate by verifying your PIN.", "Account hacked! Open the app now to secure it."):
        assert check_message(text, store=False, log=False).verdict != V.SAFE
