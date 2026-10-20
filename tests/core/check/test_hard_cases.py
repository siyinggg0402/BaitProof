"""Regression tests for the failures a live comparison found on the hard sets (see README, 'Measured accuracy')."""
import pytest

from core.ai import llm
from core.domain.schemas import TacticHit, Verdict as V
from core.pipelines.check import check_message, preconditions, tools
from core.pipelines.check.ingest import ingest
from core.pipelines.check import intent as intent_stage


def ctx(text):
    ing = ingest(text)
    it = intent_stage.diagnose(ing)
    f = tools.Findings(hosts=list(ing.entities.hosts))
    return ing, it, f


# ---------------------------------------------------------------- the precondition gate
@pytest.mark.parametrize("text,tactic,kept", [
    ("A new payee was added to your account. Call the number on your card.", "lookalike-link", False),  # no link at all
    ("Check it out: quiet-bill-notice.top", "lookalike-link", True),
    ("Meet me at the cafe at 5.", "irreversible-payment", False),
    ("Please pay with a gift card.", "irreversible-payment", True),
    ("Invoice attached for the garden work.", "impersonation-official", False),
    ("This is your bank's fraud team.", "impersonation-official", True),
    ("Ben from the club: send the $25 fee please.", "job-task-scam", False),
    ("Remote role paying $4,500 a week.", "job-task-scam", True),
    ("Your parcel is here.", "otp-credential-phish", False),
    ("Reply with the code we sent you.", "otp-credential-phish", True),
    ("Lunch on Sunday?", "urgency-pressure", False),
    ("Pay within 24 hours or it is cancelled.", "urgency-pressure", True),
    ("Lunch on Sunday?", "remote-access-request", False),
    ("Please install AnyDesk.", "remote-access-request", True),
])
def test_a_models_claim_must_be_possible_for_the_message(text, tactic, kept):
    ing, it, f = ctx(text)
    out, dropped = preconditions.filter_claims([TacticHit(id=tactic, quote=text[:10])], ing, it, f)
    assert bool(out) is kept and (not kept) == bool(dropped)


def test_a_real_official_link_cannot_be_called_a_lookalike():
    ing, it, f = ctx("Update your card at https://www.netflix.com/youraccount")
    f.official_hosts["www.netflix.com"] = "netflix"
    out, _ = preconditions.filter_claims([TacticHit(id="lookalike-link", quote="netflix.com")], ing, it, f)
    assert out == []


def test_unknown_tactic_ids_are_not_silently_dropped():
    ing, it, f = ctx("hello")
    assert preconditions.filter_claims([TacticHit(id="brand-new-trick", quote="hello")], ing, it, f)[0]


def _fake(monkeypatch, analysis):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: ({"asks": [], "pressure": []} if "diagnose what a message wants" in system else
                                                                      {"concern": False} if "second reviewer" in system else analysis))


def test_hallucinated_tactics_never_reach_the_verdict(monkeypatch):
    # the real failure: a genuine bank alert with NO link, 'looks like a real company but the address is slightly off'
    halluc = {"verdict": "likely_scam", "tactics": [
        {"id": "lookalike-link", "quote": "number on the back of your card", "why": "address slightly off"},
        {"id": "job-task-scam", "quote": "call the number", "why": "fabricated issue"}], "the_tell": "t", "action": "a"}
    _fake(monkeypatch, halluc)
    r = check_message("Alert from your bank: a new payee was added to your account. If this was you, no action is needed. If not, call the number on the back of your card.")
    assert r.verdict != V.SCAM and r.verdict != V.LIKELY_SCAM
    g = [s for s in r.trace if s.stage == "grounding" and s.status == "flag"]
    assert g and "lookalike-link: there is no unverified link" in g[0].detail and "job-task-scam" in g[0].detail  # says WHY


# ---------------------------------------------------------------- first-contact openers can never be 'safe'
@pytest.mark.parametrize("text", [
    "Hi, is this Margaret? I got your number from Linda at the book club. Sorry if I've got the wrong person!",
    "Dad, I dropped my phone in the pool, this is my temporary number. Can you text me when you see this?",
    "Hi Sam, it's Priya from HR. Can you check if you can receive an important message? Reply as soon as you see this.",
    "Hi, I'm interested in your listing. Is the item still available? Please text me on 555-0142.",
    "I saw your profile and think you'd be great for a role. Add me on Telegram @jen_recruit",
])
def test_openers_are_never_cleared_even_if_the_model_says_safe(monkeypatch, text):
    _fake(monkeypatch, {"verdict": "safe", "tactics": [], "the_tell": "", "action": ""})
    r = check_message(text)
    assert r.verdict != V.SAFE and any(e.source == "opener" for e in r.evidence)
    assert check_message(text).verdict != V.SAFE  # and offline


@pytest.mark.parametrize("text", [
    "Hey, I'm outside!", "Hi Mum, I'm at the shops. Do you need milk or bread?", "Can you pick up Ollie from football at 5? Thanks.",
    "Hi, thanks for your enquiry about the flat. Viewings are Saturday 10 to 12. Reply with a time that suits.",
    "Mum, I've landed! Will call you when I get to the hotel x",
])
def test_ordinary_friendly_messages_are_not_openers(text):
    assert ctx(text)[1].opener == ""


# ---------------------------------------------------------------- over-generic rules that caused false alarms
@pytest.mark.parametrize("text", [
    "Congratulations on your new job! Dinner is on us on Saturday to celebrate.",
    "Netflix: your payment method is expiring soon. You can update it in your account settings at https://www.netflix.com/youraccount",
    "Verify your email address to finish creating your Spotify account: https://www.spotify.com/verify?token=abc123",
    "Invoice #2291 attached: $380 for the garden work in October. Bank details are on the invoice. Thanks!",
    "Hi, this is Ben from the sports club. Can you send me the $25 membership fee by Friday? Bank details are the same as last year.",
])
def test_genuine_messages_that_used_to_false_alarm_do_not_now(text):
    r = check_message(text)
    assert r.verdict not in (V.SCAM, V.LIKELY_SCAM), (r.verdict, [e.claim for e in r.evidence if e.supports == "scam"])


def test_bank_details_is_not_a_claim_to_be_a_bank():
    assert ctx("Bank details are the same as last year.")[1].claimed == ""
    assert ctx("This is Acme Bank. Your account is locked.")[1].claimed_kind == "organisation"


def test_official_domain_table_is_broad_and_imitations_are_still_caught():
    for host in ("www.spotify.com", "zoom.us", "github.com", "www.royalmail.com", "dpd.co.uk", "m.facebook.com"):
        assert tools.domain_check(host)["official"] and not tools.domain_check(host)["hard"], host
    for host in ("spotify-billing-help.top", "zoom-us-verify.xyz", "royalmail-redelivery.top", "facebook.com.evil.xyz"):
        assert tools.domain_check(host)["hard"], host
    assert not tools.domain_check("targetprocess.com")["hard"]  # a real company whose name merely begins with a brand word


@pytest.mark.parametrize("text", [
    "Flat owner here, I'm abroad on work so can't show it, but I'll post you the keys once you transfer the 900 pound holding deposit.",
    "You qualify for a 300 pound energy rebate from the government. Claim now: https://energy-support-claim.com/start",
    "I have two spare tickets for the sold-out concert. Payment first by bank transfer, tickets emailed once it clears.",
    "Congrats on the job! We will send you a cheque to buy your equipment from our approved vendor. Deposit it and send the vendor the balance.",
])
def test_more_scam_scripts_are_recognised(text):
    assert ctx(text)[1].scenario
