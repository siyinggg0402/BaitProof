import pytest

from core.ai import llm
from core.ai.prompts import CHECK_SYSTEM, INTENT_SYSTEM
from core.domain import intents
from core.domain.schemas import Verdict as V
from core.pipelines.check import analysis, check_message, intent as intent_stage
from core.pipelines.check.ingest import ingest
from core.pipelines.check.tools import Findings


def dx(text):
    return intent_stage.diagnose(ingest(text))


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
def _fake(monkeypatch, out):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: out)


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
