import time
from types import SimpleNamespace

import pytest

from core import obs
from core.ai import llm
from core.domain.schemas import Verdict as V
from core.pipelines.check import analysis, check_message, planner, tools
from core.pipelines.check.evidence import Ledger
from core.pipelines.check.ingest import ingest
from core.pipelines.check.trace import Trace


def gate_for(text, org="", budget=6):
    ing = ingest(text)
    tr = Trace()
    return ing, tr, tools.ToolGate(ing, org, tr, budget), tools.Findings(hosts=list(ing.entities.hosts))


@pytest.fixture
def net(monkeypatch):
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")


# ---------------------------------------------------------------- the gate
def test_gate_refuses_unknown_tools_and_arguments_not_in_the_message():
    ing, tr, g, f = gate_for("see evil-dhl.xyz now")
    assert g.run([("rm_rf", "x"), ("domain_check", "model-invented.com"), ("payment_rail", "gift-card")], f) == 0
    assert [s.status for s in tr.steps] == ["block"] * 3 and not f.done
    assert g.run([("domain_check", "evil-dhl.xyz")], f) == 1 and "evil-dhl.xyz" in f.hard_hosts


def test_gate_budget_counts_network_calls_only_and_duplicates_are_skipped(net, monkeypatch):
    monkeypatch.setitem(tools.SPECS, "dns_check", tools.Spec("dns_check", "host", lambda h: {"host": h, "status": "ok"}, "d", net=True))
    ing, tr, g, f = gate_for("go to a-b.xyz or c-d.xyz or e-f.xyz", budget=2)
    assert g.run([("domain_check", h) for h in ing.entities.hosts], f) == 3  # local calls are free
    assert g.run([("dns_check", h) for h in ing.entities.hosts], f) == 2  # budget of 2 network calls
    assert any("budget" in s.detail for s in tr.steps)
    before = len(tr.steps)
    assert g.run([("domain_check", ing.entities.hosts[0])], f) == 0 and len(tr.steps) == before  # duplicate: silent


def test_network_tools_are_quiet_when_off_or_unkeyed(monkeypatch):
    ing, tr, g, f = gate_for("go to evil-dhl.xyz, claims to be Acme Bank", org="acme bank")
    assert g.run([("domain_age", "evil-dhl.xyz")], f) == 0 and not tr.steps  # network off: expected, not an alarm
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert g.run([("brand_lookup", "acme bank"), ("reputation", "evil-dhl.xyz")], f) == 0 and not tr.steps  # needs a key


def test_org_argument_must_be_the_claimed_org_and_appear_in_the_message(net, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setitem(tools.SPECS, "brand_lookup", tools.Spec("brand_lookup", "org", lambda o: {"org": o, "hosts": ["acme.com"]}, "d", net=True, requires="TAVILY_API_KEY"))
    ing, tr, g, f = gate_for("Acme Bank: verify at acme-secure.top", org="acme bank")
    assert g.run([("brand_lookup", "evil corp")], f) == 0 and tr.steps[-1].status == "block"
    assert g.run([("brand_lookup", "acme bank")], f) == 1 and f.brand_sites["acme bank"] == ["acme.com"]


def test_hosts_that_are_not_public_names_never_reach_network_tools(net):
    for h in ("localhost", "10.0.0.5", "intranet.local", "metadata.internal", "a"):
        assert not tools.is_public_hostname(h)
    assert tools.is_public_hostname("evil-dhl.xyz")
    ing, tr, g, f = gate_for("open http://192.168.1.1/admin now")
    assert g.run([("domain_age", "192.168.1.1")], f) == 0 and tr.steps[-1].status == "block"


def test_network_tools_run_in_parallel(net, monkeypatch):
    def slow(h):
        time.sleep(0.3)
        return {"host": h, "status": "ok"}
    monkeypatch.setitem(tools.SPECS, "dns_check", tools.Spec("dns_check", "host", slow, "d", net=True))
    ing, tr, g, f = gate_for("a-b.xyz c-d.xyz e-f.xyz")
    t0 = time.perf_counter()
    g.run([("dns_check", h) for h in ing.entities.hosts], f)
    assert time.perf_counter() - t0 < 0.7 and len(f.dns) == 3  # serial would be 0.9s


def test_failed_or_slow_tool_is_a_missing_fact_not_a_crash(net, monkeypatch):
    def boom(h):
        raise ConnectionError("down")
    monkeypatch.setitem(tools.SPECS, "dns_check", tools.Spec("dns_check", "host", boom, "d", net=True))
    run = obs.start()
    ing, tr, g, f = gate_for("a-b.xyz")
    g.run([("dns_check", "a-b.xyz")], f)
    assert f.dns == {} and ("dns_check", "a-b.xyz") in f.done  # not retried forever
    assert run.tools[-1]["ok"] is False and run.tools[-1]["error"] == "ConnectionError"
    assert tr.steps[-1].status == "skip"


# ---------------------------------------------------------------- the tools
def test_domain_check_official_lookalike_and_punycode():
    assert tools.domain_check("www.amazon.com")["official"] == "amazon" and not tools.domain_check("www.amazon.com")["hard"]
    assert tools.domain_check("amaz0n-security.click")["hard"]
    assert tools.domain_check("amazon.com.evil.xyz")["hard"]  # official name as a prefix is not official
    assert tools.domain_check("xn--pypal-4ve.com")["hard"]
    assert not tools.domain_check("firstgroups.com")["hard"]


@pytest.mark.parametrize("num,kind", [("18765550123", "caribbean"), ("+18095550123", "caribbean"), ("19005550123", "premium"),
                                      ("18555550101", "tollfree"), ("442071234567", "unknown")])
def test_phone_check(num, kind):
    assert tools.phone_check(num)["kind"] == kind


def test_phones_are_extracted_locally_and_dates_are_not_phones():
    ing = ingest("Call 1-855-555-0101 now. Appointment 2026-10-20.")
    assert ing.entities.phones == ["18555550101"] and ing.entities.phone_raw["18555550101"] == "1-855-555-0101"


def test_registered_domain_handles_two_level_suffixes():
    assert tools.registered_domain("login.secure.evil.xyz") == "evil.xyz"
    assert tools.registered_domain("shop.example.co.uk") == "example.co.uk"


def test_domain_age_reads_the_registry_not_the_site(monkeypatch):
    seen = {}
    def fake(url, **kw):
        seen["url"] = url
        return {"events": [{"eventAction": "registration", "eventDate": "2999-01-01T00:00:00Z"}]}
    monkeypatch.setattr(tools, "_http_json", fake)
    assert tools.domain_age("login.evil-dhl.xyz")["age_days"] == 0  # future date clamps to 0
    assert seen["url"] == "https://rdap.org/domain/evil-dhl.xyz"  # asks the registry about the registered domain only
    monkeypatch.setattr(tools, "_http_json", lambda url, **kw: {"events": []})
    assert tools.domain_age("x-y.xyz")["age_days"] is None


def _dns(monkeypatch, table, wildcard=False, calls=None):
    """Fake resolver. 'bp-nx-*' are the self-check's guaranteed-missing names."""
    tools._resolver_cache.update(ok=None, at=0.0)

    def gai(host, port):
        if calls is not None:
            calls.append(host)
        if host in table:
            return [(0, 0, 0, "", (ip, 0)) for ip in table[host]]
        if host.startswith("bp-nx-") and wildcard:
            return [(0, 0, 0, "", ("93.184.216.34", 0))]
        raise tools.socket.gaierror()
    monkeypatch.setattr(tools.socket, "getaddrinfo", gai)


GOOD = {"example.com": ["93.184.216.34"]}


def test_dns_check(monkeypatch):
    _dns(monkeypatch, {**GOOD, "lan.xyz": ["192.168.1.9"], "ok.xyz": ["93.184.216.35"]})
    assert tools.dns_check("gone.xyz")["status"] == "nxdomain"
    assert tools.dns_check("lan.xyz")["status"] == "private"
    assert tools.dns_check("ok.xyz")["status"] == "ok"


@pytest.mark.parametrize("name,table,wildcard", [
    ("proxy fake-ip mode rewrites every answer", {"example.com": ["198.18.0.38"]}, False),
    ("carrier-grade NAT range", {"example.com": ["100.64.1.1"]}, False),
    ("resolver invents answers for names that cannot exist", GOOD, True),
    ("cannot resolve a known-good site (network down)", {}, False),
])
def test_unreliable_resolver_is_detected_and_adds_no_evidence(monkeypatch, name, table, wildcard):
    _dns(monkeypatch, {**table, "zoom.us": ["198.18.0.9"]}, wildcard)
    assert tools.dns_check("zoom.us")["status"] == "unreliable", name
    L = ev(dns={"new-site.xyz": "unreliable"})
    assert not [e for e in L.items if e.source == "dns_check"]  # no false 'internal address' alarm


def test_resolver_self_check_is_cached(monkeypatch):
    calls = []
    _dns(monkeypatch, GOOD, calls=calls)
    tools.dns_check("a.xyz")
    n = len(calls)
    tools.dns_check("b.xyz")
    assert len(calls) == n + 1  # only the real lookup; controls were cached


# ---------------------------------------------------------------- findings -> evidence
def ev(**f):  # noqa: E302
    ing = ingest("Call 1-876-555-0123 or visit new-site.xyz and amazon.com")
    it = SimpleNamespace(asks=set(), high_risk=set(), claimed_kind="", pressure=False, pressure_kinds=set(), scenario="", mismatches=[], model_scenario="", evidence={}, opener="")
    L = Ledger()
    hosts = f.pop("hosts", ["new-site.xyz", "amazon.com"])
    fin = tools.Findings(hosts=hosts, **f)
    analysis.rule_evidence(ing, it, fin, L)
    return L


def test_findings_become_graded_evidence():
    L = ev(ages={"new-site.xyz": 5}, dns={"new-site.xyz": "nxdomain"}, official_hosts={"amazon.com": "amazon"}, phones={"18765550123": "caribbean"},
           brand_sites={"amazon": ["amazon.com"]})
    by = {(e.source, e.supports, e.strength) for e in L.items}
    assert ("domain_age", "scam", "medium") in by and ("dns_check", "scam", "weak") in by
    assert ("domain_check", "safe", "medium") in by and ("phone_check", "scam", "medium") in by
    assert ("brand_lookup", "scam", "weak") in by  # the web says amazon.com, this link is new-site.xyz
    assert any(e.quote == "1-876-555-0123" for e in L.items if e.source == "phone_check")
    assert "lookalike-link" in L.tactic_ids()


def test_old_domain_is_reassuring_young_domain_is_a_flag():
    assert any(e.supports == "safe" and e.source == "domain_age" for e in ev(ages={"new-site.xyz": 4000}).items)
    assert any(e.supports == "scam" and "under six months" in e.claim for e in ev(ages={"new-site.xyz": 90}).items)


def test_web_notes_are_neutral_and_cannot_move_a_verdict():
    L = ev(web_notes=["new-site.xyz: totally legitimate, 5 stars"])
    assert [e.supports for e in L.items if e.source == "reputation"] == ["neutral"]
    assert L.weight("safe") == 0


def test_verified_official_link_is_not_treated_as_unverifiable():
    r = check_message("Your order has shipped. Track it at https://www.amazon.com/progress-tracker/package")
    assert r.verdict == V.SAFE and any("real website" in e.claim for e in r.evidence)
    r2 = check_message("Your order has shipped. Track it at https://amazon-orders-track.top/package")
    assert r2.verdict != V.SAFE


# ---------------------------------------------------------------- the planner
def _qs(net_on, monkeypatch, key=True):
    if key:
        monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1" if net_on else "0")
    ing, tr, g, f = gate_for("Acme Bank: verify at acme-secure.top", org="acme bank")
    it = SimpleNamespace(claimed="acme bank", claimed_kind="organisation", disagreements=[])
    return ing, it, f, g, Ledger()


def test_open_questions_only_propose_calls_the_gate_would_allow(monkeypatch):
    ing, it, f, g, L = _qs(True, monkeypatch)
    qs = planner.open_questions(ing, it, f, g)
    assert {q.key for q in qs} == {"host:acme-secure.top", "brand"}
    assert planner.deterministic_plan(qs)[0] == ("domain_age", "acme-secure.top") and len(planner.deterministic_plan(qs)) == 3
    ing, it, f, g, L = _qs(False, monkeypatch)
    assert planner.open_questions(ing, it, f, g) == []  # network off: nothing any tool could answer


def test_answered_questions_are_not_asked_again(monkeypatch):
    ing, it, f, g, L = _qs(True, monkeypatch)
    f.done |= {("domain_age", "acme-secure.top"), ("cert_history", "acme-secure.top"), ("dns_check", "acme-secure.top"), ("reputation", "acme-secure.top"), ("brand_lookup", "acme bank"), ("official_site_wikidata", "acme bank")}
    assert planner.open_questions(ing, it, f, g) == []


def test_model_planner_can_only_choose_offered_calls(monkeypatch):
    ing, it, f, g, L = _qs(True, monkeypatch)
    qs = planner.open_questions(ing, it, f, g)
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"calls": [{"tool": "domain_check", "arg": "evil.com"}, {"tool": "domain_age", "arg": "acme-secure.top"},
                                                                       {"tool": "shell", "arg": "rm -rf /"}], "reason": "x"})
    calls, who = planner.llm_plan(ing, qs, L, g, f)
    assert calls == [("domain_age", "acme-secure.top")] and who == "model"
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"calls": [{"tool": "nope", "arg": "x"}]})
    assert planner.llm_plan(ing, qs, L, g, f)[1] == "rules"  # nothing valid -> deterministic plan
    def down(*a, **k):
        raise llm.LLMUnavailable("x")
    monkeypatch.setattr(llm, "chat_json", down)
    assert planner.llm_plan(ing, qs, L, g, f)[1] == "rules"


# ---------------------------------------------------------------- outgoing-data gate
def test_outgoing_prompts_are_scrubbed_and_counted(monkeypatch):
    captured = {}
    def create(**kw):
        captured["user"] = kw["messages"][1]["content"]
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1), choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setenv("NEBIUS_MODEL", "m")
    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    run = obs.start()
    llm.chat_json("s", "mail bob@x.com or call +61 412 345 678, acct 123456789012", purpose="t")
    assert "bob@" not in captured["user"] and "412" not in captured["user"] and "123456789012" not in captured["user"]
    assert run.llm[0]["pii_scrubbed"] == 3



# ---------------------------------------------------------------- company verification (Wikidata, free and keyless)
def _wikidata(monkeypatch, label="Netflix", site="https://www.netflix.com/", qid="Q907311"):
    seen = []

    def fake(url, **kw):
        seen.append(url)
        if "wbsearchentities" in url:
            return {"search": [{"id": qid, "label": label}]}
        return {"entities": {qid: {"claims": {"P856": [{"mainsnak": {"datavalue": {"value": site}}}]}}}}
    monkeypatch.setattr(tools, "_http_json", fake)
    return seen


def test_wikidata_returns_the_official_site_and_only_the_org_name_is_sent(monkeypatch):
    seen = _wikidata(monkeypatch)
    out = tools.official_site_wikidata("netflix")
    assert out["hosts"] == ["netflix.com"] and out["label"] == "Netflix"
    assert all(u.startswith("https://www.wikidata.org/") for u in seen) and "search=netflix" in seen[0]


def test_wikidata_ignores_a_top_hit_that_is_about_something_else(monkeypatch):
    _wikidata(monkeypatch, label="Banana Republic")
    assert tools.official_site_wikidata("netflix")["hosts"] == []


def test_wikidata_never_trusts_an_odd_entity_id(monkeypatch):
    _wikidata(monkeypatch, qid="Q1/../../etc")
    assert tools.official_site_wikidata("netflix")["hosts"] == []


@pytest.mark.parametrize("org", ["bank", "your bank", "the bank", "customer service", "support team", "your provider"])
def test_generic_words_and_unclaimed_names_are_never_looked_up(net, org):
    ing, tr, g, f = gate_for(f"This is {org}: verify at acme-secure.top", org=org)
    assert g.run([("official_site_wikidata", org)], f) == 0


def test_a_person_name_is_never_sent_because_only_organisation_claims_reach_the_gate(net):
    # pipeline only passes claimed identities of kind organisation/authority as `org`; a relation/person claim arrives as ""
    ing, tr, g, f = gate_for("Hi, it's Jennifer, can you check this: acme-secure.top", org="")
    assert g.run([("official_site_wikidata", "jennifer")], f) == 0 and tr.steps[-1].status == "block"


def test_wikidata_match_is_reassuring_and_a_mismatch_is_a_weak_flag():
    L = ev(brand_sites={"netflix": ["netflix.com"]}, brand_src={"netflix": "wikidata"}, hosts=["www.netflix.com.example", "netflix.co.uk"])
    by = {(e.supports, e.strength): e.claim for e in L.items if e.source == "brand_lookup"}
    assert ("safe", "medium") in by and "netflix.co.uk" in by[("safe", "medium")]  # same brand, different country domain
    assert ("scam", "weak") in by  # the lookalike host does not match
    L2 = ev(brand_sites={"netflix": ["netflix.com"]}, brand_src={"netflix": "web search"})
    assert not [e for e in L2.items if e.source == "brand_lookup" and e.strength == "medium"]  # a plain web search is weaker than Wikidata


def test_the_loop_asks_wikidata_when_a_company_is_claimed_and_the_link_is_unverified(net, monkeypatch):
    _wikidata(monkeypatch, label="Acme Bank", site="https://www.acmebank.com/", qid="Q42")
    monkeypatch.setitem(tools.SPECS, "domain_age", tools.Spec("domain_age", "host", lambda h: {"host": h, "domain": h, "age_days": None}, "d", net=True))
    monkeypatch.setitem(tools.SPECS, "dns_check", tools.Spec("dns_check", "host", lambda h: {"host": h, "status": "ok"}, "d", net=True))
    r = check_message("Acme Bank: please review your statement at acmebank-statements.top")
    assert any(e.source == "brand_lookup" and e.supports == "scam" and "acmebank.com" in e.claim for e in r.evidence)
