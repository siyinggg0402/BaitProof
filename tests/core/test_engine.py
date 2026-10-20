import pytest

from core import obs
from core.ai import llm
from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message, engine, gates, tools
from core.pipelines.check.evidence import Ledger
from core.storage import library

LINK_MSG = "Your statement is ready, open quiet-bill-notice.top"  # one weak flag (odd ending) + a link nobody can vouch for


def steps(r, name):
    return [s for s in r.trace if s.stage == name]


@pytest.fixture
def net(monkeypatch):
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")
    calls = []

    def age(h):
        calls.append(("domain_age", h))
        return {"host": h, "domain": h, "age_days": AGE["days"]}

    def dns(h):
        calls.append(("dns_check", h))
        return {"host": h, "status": AGE["dns"]}
    AGE.update(days=5, dns="nxdomain")
    monkeypatch.setitem(tools.SPECS, "domain_age", tools.Spec("domain_age", "host", age, "age", net=True))
    monkeypatch.setitem(tools.SPECS, "dns_check", tools.Spec("dns_check", "host", dns, "dns", net=True))
    return calls


AGE = {}


# ---------------------------------------------------------------- the loop
def test_confident_cases_do_not_loop():
    r = check_message("Buy 4 gift cards and send me the codes. Don't tell Mom.")
    assert r.confidence == "high" and not steps(r, "loop")
    assert steps(r, "sufficiency")[0].detail == "confident enough" and steps(r, "sufficiency")[0].status == "pass"


def test_loop_gathers_facts_until_confident_and_stacked_evidence_flips_the_verdict(net):
    r = check_message(LINK_MSG)
    assert r.verdict == V.SCAM and r.confidence == "high"  # weak flag + 5-day-old + non-existent site add up
    loops = steps(r, "loop")
    assert len(loops) == 1 and "round 2" in loops[0].detail and "domain_age" in loops[0].detail
    assert steps(r, "sufficiency")[0].detail == "confident enough"
    assert {c[0] for c in net} == {"domain_age", "dns_check"}
    assert any(e.source == "domain_age" and e.supports == "scam" for e in r.evidence)


def test_loop_can_also_lower_confidence_when_facts_are_reassuring(net):
    AGE.update(days=4000, dns="ok")  # old, resolving site
    r = check_message(LINK_MSG)
    assert r.verdict != V.SCAM  # a long-established site is evidence in its favour
    assert any(e.supports == "safe" and e.source == "domain_age" for e in r.evidence)


def test_loop_stops_when_nothing_more_can_be_learned(net):
    AGE.update(days=1000, dns="ok")  # neither reassuring enough nor alarming: tools answered, nothing left to ask
    r = check_message(LINK_MSG)
    sf = steps(r, "sufficiency")[0]
    assert sf.status == "flag" and "nothing more" in sf.detail
    assert len(steps(r, "loop")) <= 1 and r.verdict in (V.LIKELY_SCAM, V.UNSURE)  # not forced to a confident answer


def test_round_limit_and_time_budget_are_enforced(net, monkeypatch):
    monkeypatch.setattr(engine, "MAX_ROUNDS", 1)
    r = check_message(LINK_MSG)
    assert not steps(r, "loop") and "round limit" in steps(r, "sufficiency")[0].detail and not net
    monkeypatch.setattr(engine, "MAX_ROUNDS", 3)
    monkeypatch.setattr(engine, "MAX_SECONDS", -1)
    r2 = check_message(LINK_MSG)
    assert "time budget" in steps(r2, "sufficiency")[0].detail and not net


def test_network_budget_is_enforced_across_rounds(net, monkeypatch):
    monkeypatch.setattr(tools.ToolGate, "__init__", lambda self, ing, org, trace, budget=1: (setattr(self, "ing", ing), setattr(self, "org", org.lower()),
                                                                                           setattr(self, "trace", trace), setattr(self, "budget", 1), setattr(self, "used", 0), setattr(self, "blocked", [])) and None)
    check_message(LINK_MSG)
    assert len(net) == 1  # only one network call fits the budget


# ---------------------------------------------------------------- with a model
def fake(monkeypatch, analysis, second=None, planner=None, intent_out=None, critic=None, log=None):
    monkeypatch.setattr(llm, "available", lambda: True)

    def chat(system, user, heavy=True, retries=1, purpose=""):
        if log is not None:
            log.append((purpose, user))
        if "diagnose what a message wants" in system:
            return intent_out or {"asks": [], "pressure": []}
        if "investigator" in system:
            return planner or {"calls": []}
        if "second reviewer" in system:
            return critic or {"concern": False}
        return (second if second is not None and "SECOND LOOK" in user else analysis)
    monkeypatch.setattr(llm, "chat_json", chat)


SAFE = {"verdict": "safe", "tactics": [], "the_tell": "", "action": ""}
SCAM_FLAG = {"verdict": "scam", "tactics": [{"id": "advance-fee", "quote": "small fee", "why": "asks for a fee"}], "the_tell": "t", "action": "a"}


def test_model_reanalyses_with_new_facts_and_stale_opinions_are_dropped(net, monkeypatch):
    log = []
    answers = iter([SAFE, SCAM_FLAG])
    monkeypatch.setattr(llm, "available", lambda: True)

    def chat(system, user, heavy=True, retries=1, purpose=""):
        log.append((purpose, user))
        if "diagnose" in system:
            return {"asks": [], "pressure": []}
        if "investigator" in system:
            return {"calls": [{"tool": "domain_age", "arg": "quiet-bill-notice.top"}]}
        if "second reviewer" in system:
            return {"concern": False}
        return next(answers)
    monkeypatch.setattr(llm, "chat_json", chat)
    r = check_message("Your statement is ready, open quiet-bill-notice.top. Please send the small fee.")
    analyses = [u for p, u in log if p == "analysis"]
    assert len(analyses) == 2 and "registered 5 days ago" not in analyses[0] and "registered 5 days ago" in analyses[1]  # re-read with the new fact
    assert not any(e.kind == "model" and e.supports == "safe" for e in r.evidence)  # the earlier 'found nothing' opinion was discarded
    assert [c[0] for c in net] == ["domain_age"]  # the model chose; dns_check was never run


def test_second_look_disagreement_makes_the_model_unsure(monkeypatch):
    fake(monkeypatch, analysis=SAFE, second=SCAM_FLAG)
    r = check_message("Please act now, we need the small fee for the hall.")  # one independent flag -> not 'high' -> second look
    assert steps(r, "second-look") and "second look" in steps(r, "loop")[0].detail
    # First look said safe (which alone made confidence 'low'); the second look disagreed, so the model no longer counts as a
    # 'safe' voice. The one independent red flag stands at medium confidence instead of being talked down.
    assert r.verdict == V.LIKELY_SCAM and r.confidence == "medium"
    assert steps(r, "sufficiency")[0].status == "flag"  # still not 'high': the loop says so honestly


def test_second_look_agreement_is_recorded_and_runs_once(monkeypatch):
    log = []
    fake(monkeypatch, analysis=SAFE, second=SAFE, log=log)
    r = check_message("Please act now, the hall meets Saturday.")
    assert sum(1 for p, _ in log if p == "second-look") == 1
    assert any(e.source == "second-look" and e.supports == "safe" for e in r.evidence)


def test_hard_evidence_survives_model_self_contradiction(monkeypatch):
    fake(monkeypatch, analysis=SAFE, second=SCAM_FLAG)
    r = check_message("Buy 4 gift cards and send me the numbers please.")
    assert r.verdict == V.SCAM


def test_model_budget_stops_the_loop(net, monkeypatch):
    monkeypatch.setattr(engine, "MAX_LLM_CALLS", 0)
    r = check_message(LINK_MSG)
    assert not steps(r, "loop")  # no budget for extra rounds


# ---------------------------------------------------------------- logging + output gate
def test_rounds_loops_and_pii_counters_reach_the_log(net):
    import json
    from core.obs import logger

    check_message(LINK_MSG)
    e = json.loads(open(logger.path()).read().splitlines()[-1])
    assert e["rounds"] == 2 and "loop" in {s["stage"] for s in e["stages"]} and e["pii_scrubbed"] == 0
    assert {t["tool"] for t in e["tools"]} >= {"domain_check", "domain_age", "dns_check"}


def test_output_gate_repairs_safety_violations():
    cav = "I can't be sure, verify first."
    tell, action, fixes = gates.output_gate(V.SAFE, "", "All good.", cav)
    assert cav in action and tell and len(fixes) == 2
    tell, action, fixes = gates.output_gate(V.SCAM, "bad", "This is safe, go ahead.", cav)
    assert "safe" not in action.lower() and fixes
    tell, action, fixes = gates.output_gate(V.UNSURE, "x", "", cav)
    assert action and fixes == ["supplied a safe action"]
    assert gates.output_gate(V.SAFE, "ok", "Fine. " + cav, cav)[2] == []


def test_library_never_stores_numbers_the_model_echoed(monkeypatch):
    fake(monkeypatch, analysis={"verdict": "scam", "tactics": [], "the_tell": "Call 0412 345 678 and ask for Bob at bob@x.com",
                                "action": "Don't call 0412 345 678.", "tell_phrase": "", "abstract_example": "Buy gift cards and send the codes now"})
    check_message("Buy 4 gift cards and send me the codes right now. Don't tell Mom.")
    (ex,) = library.user_examples()
    assert "0412" not in ex["tell"] + ex["action"] and "bob@" not in ex["tell"]


def test_second_look_is_skipped_when_the_doubt_is_not_about_the_model(net, monkeypatch):
    # An unverifiable link makes the answer 'unsure' no matter what the model says, so a second opinion can't help.
    log = []
    AGE.update(days=1000, dns="ok")
    fake(monkeypatch, analysis=SAFE, second=SAFE, log=log)
    r = check_message("Here is the schedule: https://example-club.org/schedule")
    assert not any(p == "second-look" for p, _ in log)
    assert "second look" not in " ".join(s.detail for s in steps(r, "loop"))


def test_model_only_suspicion_is_overruled_by_independent_reassurance(net, monkeypatch):
    AGE.update(days=10000, dns="ok")
    lookalike = {"verdict": "likely_scam", "tactics": [{"id": "lookalike-link", "quote": "invoice is ready", "why": "slightly off address"}],
                 "the_tell": "t", "action": "a"}
    fake(monkeypatch, analysis=lookalike, second=lookalike)
    r = check_message("Hi, your invoice is ready: https://billing.acmeplumbing.com/inv/8841")
    assert r.verdict == V.UNSURE and r.confidence == "low"  # a 27-year-old registration beats the AI's unsupported hunch
    assert any(e.kind == "model" and e.supports == "scam" for e in r.evidence)  # ...but the suspicion stays on the record
    assert any(e.supports == "safe" and e.source == "domain_age" for e in r.evidence)
    # the same claim with NO reassuring fact is still taken seriously
    AGE.update(days=None, dns="ok")
    r2 = check_message("Hi, your invoice is ready: https://billing.quiet-acme.io/inv/8841")
    assert r2.verdict == V.LIKELY_SCAM


def test_a_message_that_asks_for_nothing_cannot_be_called_a_scam_on_the_models_word_alone(monkeypatch):
    otp = {"verdict": "likely_scam", "tactics": [
        {"id": "otp-credential-phish", "quote": "Your verification code is 771204", "why": "requests a code"},
        {"id": "urgency-pressure", "quote": "It expires in 10 minutes", "why": "deadline"}], "the_tell": "t", "action": "a"}
    fake(monkeypatch, analysis=otp, second=otp)
    r = check_message("Your verification code is 771204. It expires in 10 minutes. Never share this code.")
    assert r.verdict == V.UNSURE and r.confidence == "low"  # two quoted-but-unsupported claims, and nothing is being asked
    assert not r.added_to_training


def test_the_scam_label_needs_independent_evidence(monkeypatch):
    two = {"verdict": "scam", "tactics": [{"id": "advance-fee", "quote": "small fee", "why": "fee"},
                                           {"id": "job-task-scam", "quote": "book the hall", "why": "job"}], "the_tell": "t", "action": "a"}
    fake(monkeypatch, analysis=two, second=two, intent_out={"asks": ["pay"], "pressure": []})
    r = check_message("Please send the small fee so we can book the hall.")
    assert r.verdict == V.LIKELY_SCAM  # capped: 'scam' needs evidence the model didn't supply
    assert not r.added_to_training
