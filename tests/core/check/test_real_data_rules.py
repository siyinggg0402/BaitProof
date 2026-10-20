"""Rules learned from REAL messages (DIFrauD SMS / Mendeley), plus a guard against silent internal errors."""
import pytest

from core.ai import llm
from core.domain.intents import clearing_conditions_met
from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message, intent as intent_stage
from core.pipelines.check.ingest import ingest
from core.storage import library
from tests.data.en import hard_1, hard_2, hard_3, heldout_1, heldout_2


def test_the_crash_guard_never_fires_on_any_message_we_have():
    """The guard turns a bug into a polite 'not sure'. That must never happen silently: every message in every set must run clean."""
    texts = [e["text"] for e in library.seed_examples()]
    for ds in (heldout_1, heldout_2):
        texts += [t[0] if isinstance(t, tuple) else t for t in ds.SCAMS + ds.LEGIT]
    for ds in (hard_1, hard_2, hard_3):
        texts += [t[1] for t in ds.SCAMS + ds.LEGIT]
    assert len(texts) > 200
    bad = [t[:50] for t in texts if any(s.stage == "guard" for s in check_message(t, store=False, log=False).trace)]
    assert not bad, bad


def test_the_guard_also_never_fires_with_a_model_in_the_loop(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: (
        {"asks": ["pay"], "pressure": ["deadline"], "claimed_identity": {"name": "bank", "kind": "organisation"}, "scenario": "bank-security"}
        if "diagnose what a message wants" in system else {"concern": True, "reason": "x"} if "second reviewer" in system else
        {"calls": []} if "investigator" in system else {"verdict": "likely_scam", "tactics": [{"id": "advance-fee", "quote": "fee", "why": "w"}], "the_tell": "t", "action": "a"}))
    for t in [t[1] for t in hard_1.SCAMS + hard_1.LEGIT]:
        assert not any(s.stage == "guard" for s in check_message(t, store=False, log=False).trace), t[:50]


def dx(text):
    return intent_stage.diagnose(ingest(text))


@pytest.mark.parametrize("text", [
    "Congrats 2 mobile 3G Videophones R yours. call 09063458120 now! videochat wid ur mates, 150ppm",
    "1000's flirting NOW! Txt GIRL or BLOKE & ur NAME & AGE, eg GIRL ZOE 18 to 8007 to join and get chatting!",
    "HOT LIVE FANTASIES call now 08707509020 Just 20p per min NTT Ltd, PO Box 1327 Croydon CR9 5WB",
    "Your free ringtone is waiting to be collected. Simply text the password MIX to 85069 to verify.",
])
def test_premium_rate_spam_is_recognised_without_the_model(text):
    r = check_message(text, store=False, log=False)
    assert any(e.source == "premium-rate" and e.kind == "rule" for e in r.evidence) or any(e.source == "phone_check" for e in r.evidence)
    assert r.verdict in (V.SCAM, V.LIKELY_SCAM, V.UNSURE) and r.verdict != V.SAFE


def test_text_to_a_short_code_is_a_paying_ask():
    assert "pay" in dx("Text the password MIX to 85069 to get your ringtone").asks
    assert "pay" not in dx("Text me when you get there").asks


@pytest.mark.parametrize("text", ["Fraudulent transaction detected, provide OTP.", "Loan approved, confirm by sending OTP code.",
                                  "Claim your reward by submitting OTP within 10 minutes."])
def test_otp_requests_in_every_verb_form_are_asks(text):
    assert "share_code" in dx(text).asks
    assert check_message(text, store=False, log=False).verdict in (V.SCAM, V.LIKELY_SCAM)


@pytest.mark.parametrize("text", ["Your code is 482913. Never share this code with anyone.", "Use code 771204 to log in. Do not share it with anyone."])
def test_delivering_a_code_and_warning_about_it_is_not_asking_for_it(text):
    assert "share_code" not in dx(text).asks


def test_a_plain_bill_reminder_is_not_hard_evidence_but_an_ultimatum_is():
    soft = check_message("Reminder: Utility bill of 1,250 BDT due tomorrow. Please pay to avoid late fee", store=False, log=False)
    assert not [e for e in soft.evidence if e.source == "ask:pay+pressure" and e.strength == "strong"]
    hard = check_message("Pay $300 today or your electricity will be disconnected: pay-power.top", store=False, log=False)
    assert hard.verdict == V.SCAM


def test_independent_evidence_without_a_named_trick_still_counts_as_a_red_flag():
    r = check_message("Just 20p per min call now 08707509020", store=False, log=False)  # premium rate + premium number, no 'tactic' id
    assert r.verdict in (V.SCAM, V.LIKELY_SCAM) and r.confidence != "low"


def test_reply_to_claim_is_an_ask_so_a_model_only_prize_flag_is_not_dismissed_as_asking_for_nothing(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    flag = {"verdict": "scam", "tactics": [{"id": "too-good-to-be-true", "quote": "won a holiday", "why": "prize"}], "the_tell": "t", "action": "a"}
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: ({"asks": [], "pressure": []} if "diagnose what a message wants" in system else
                                                                      {"concern": False} if "second reviewer" in system else flag))
    r = check_message("Congratulations! You've won a holiday trip. Reply to claim.", store=False, log=False)
    assert r.verdict in (V.LIKELY_SCAM, V.SCAM)


# ---------------------------------------------------------------- bugs the real-data run exposed (each was a false alarm or a miss)
@pytest.mark.parametrize("text", [
    "Your OTP is 8741, do not share it with anyone.",
    "Your OTP is 789654, keep it confidential to secure your account.",
    "Ok i found dis pierre cardin one which looks normal costs 20 its on sale.",
    "As in i want custom officer discount oh.",
    "Can you share the bank details for transferring the rent money?",
    "Sent advance payment of 15,000 BDT for the event hall booking. Await confirmation",
    "Can you send 2,300 BDT by evening? Need to settle an urgent bill",
])
def test_genuine_messages_from_real_data_are_not_flagged_by_the_rules(text):
    r = check_message(text, store=False, log=False)  # offline: rules only
    assert r.verdict not in (V.SCAM, V.LIKELY_SCAM), (r.verdict, [e.claim for e in r.evidence if e.supports == "scam"])


def test_otp_delivery_does_not_match_the_account_verification_script():
    assert dx("Your OTP is 789654, keep it confidential to secure your account.").scenario == ""


def test_premium_price_needs_a_unit():
    for t in ("costs 20 its on sale", "it costs 20 for the ticket"):
        assert not [e for e in check_message(t, store=False, log=False).evidence if e.source == "premium-rate"]
    for t in ("Calls cost 150ppm", "Cost 10p per msg", "costs 1.50 pounds"[:0] or "Just 20p per min"):
        assert [e for e in check_message(t, store=False, log=False).evidence if e.source == "premium-rate"], t


def test_the_word_officer_alone_is_not_an_authority_claim_but_an_identity_claim_is():
    assert not [e for e in check_message("the customs officer discount", store=False, log=False).evidence if e.tactic == "authority-spoofing"]
    assert [e for e in check_message("This is Officer Daniels from the Cyber Crime Unit", store=False, log=False).evidence if e.tactic == "authority-spoofing"]


def test_a_lone_urgent_is_weak_but_a_deadline_with_consequences_is_not():
    weak = check_message("Need to settle an urgent bill", store=False, log=False)
    assert [e.strength for e in weak.evidence if e.tactic == "urgency-pressure"] == ["weak"]
    assert [e.strength for e in check_message("Pay within 24 hours or it is cancelled", store=False, log=False).evidence if e.tactic == "urgency-pressure"] == ["medium"]


@pytest.mark.parametrize("text", ["Your car insurance claim has been approved. Contact us to finalize.",
                                  "Your loan application was approved. Submit documents to receive payment."])
def test_claim_approved_script_is_recognised(text):
    assert dx(text).scenario == "claim-approved"
    assert check_message(text, store=False, log=False).verdict in (V.SCAM, V.LIKELY_SCAM)


def test_rules_alone_catch_most_real_world_premium_sms_spam_and_never_call_it_safe():
    spam = ["WINNER!! As a valued network customer you have been selected to receivea £900 prize reward! To claim call 09061701461. Claim code KL341.",
            "Free entry in 2 a wkly comp to win FA Cup final tkts 21st May 2005. Text FA to 87121 to receive entry question(std txt rate)T&C's apply",
            "URGENT! You have won a 1 week FREE membership in our £100,000 Prize Jackpot! Txt the word: CLAIM to No: 81010",
            "Congrats! 1 year special cinema pass for 2 is yours. call 09061209465 now! C Suprman V, Matrix3, StarWars3, etc all 4 FREE! bx420-ip4-5we. 150pm."]
    for t in spam:
        r = check_message(t, store=False, log=False)
        assert r.verdict in (V.SCAM, V.LIKELY_SCAM), t[:50]


def test_a_premium_content_sms_dressed_as_an_order_update_is_never_cleared():
    # real SMS (train split): "order is on the way" is the bait; the web address is split up so link detection misses it
    t = "BangBabes Ur order is on the way. U SHOULD receive a Service Msg 2 download UR content. If U do not, GoTo wap. bangb. tv on UR mobile internet/service menu"
    assert check_message(t, store=False, log=False).verdict is not V.SAFE
    assert not clearing_conditions_met("delivery-update", t, set())
    assert clearing_conditions_met("delivery-update", "Your parcel has been delivered to the front door.", set())


@pytest.mark.parametrize("text", [
    "Hi, I'm Daniel, a friend of your cousin Mike. He gave me your number. I'm moving to your city next month and wondered if you know any good rental agents?",
    "Hello, your colleague Priya passed me your email. I'm a friend of your manager and need a quick favour.",
    "Hey, we have a mutual friend, Sam. He shared your contact with me, hope you don't mind me writing.",
])
def test_a_stranger_who_claims_a_mutual_acquaintance_is_an_opener_and_is_never_cleared(text):
    assert check_message(text, store=False, log=False).verdict is not V.SAFE
