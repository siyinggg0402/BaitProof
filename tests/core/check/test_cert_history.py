"""cert_history (Certificate Transparency via crt.sh) and the offline phone rules. The network is always faked."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.pipelines.check import analysis, linkinfo, planner, tools
from core.pipelines.check.evidence import Ledger
from core.pipelines.check.ingest import ingest
from core.pipelines.check.trace import Trace


def day(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S")


def crt(*ages):
    return json.dumps([{"issuer_name": "C=US, O=Let's Encrypt", "common_name": "x", "name_value": "x", "not_before": day(a), "not_after": day(a - 90)} for a in ages]).encode()


@pytest.fixture
def net(monkeypatch):
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")


# ---------------------------------------------------------------- the tool
def test_the_first_certificate_gives_a_floor_for_the_age_and_only_the_domain_is_sent(monkeypatch):
    seen = {}

    def fake(url, **kw):
        seen["url"], seen["kw"] = url, kw
        return crt(5, 40, 200)
    monkeypatch.setattr(tools, "_http_bytes", fake)
    d = tools.cert_history("login.shop.example.co.uk")
    assert d["domain"] == "example.co.uk" and d["certs"] == 3 and d["first_days"] == 200 and d["many"] is False
    assert seen["url"] == "https://crt.sh/?output=json&q=example.co.uk"  # the registered domain, and nothing from the message but the name
    assert seen["kw"]["timeout"] == tools.CERT_TIMEOUT and seen["kw"]["max_bytes"] == tools.CERT_MAX_BYTES


def test_no_certificates_on_record_is_an_answer_but_not_an_age(monkeypatch):
    monkeypatch.setattr(tools, "_http_bytes", lambda *a, **k: b"[]")
    assert tools.cert_history("brand-new.xyz") == {"host": "brand-new.xyz", "domain": "brand-new.xyz", "certs": 0, "first_days": None, "many": False}


def test_a_cut_off_answer_claims_no_age(monkeypatch):
    body = crt(*([3000] * 5))
    monkeypatch.setattr(tools, "CERT_MAX_BYTES", len(body))  # the answer fills the whole allowance: there may be more behind it
    monkeypatch.setattr(tools, "_http_bytes", lambda *a, **k: body)
    d = tools.cert_history("big-site.com")
    assert d["many"] is True and d["first_days"] is None and d["certs"] == 5


def test_a_page_that_is_not_the_log_is_an_error_not_a_fact(monkeypatch):
    monkeypatch.setattr(tools, "_http_bytes", lambda *a, **k: b"<html><body>502 Bad Gateway</body></html>")
    with pytest.raises(ValueError):
        tools.cert_history("x-y.xyz")


def test_a_failing_log_is_a_missing_fact_not_a_crash(net, monkeypatch):
    def boom(*a, **k):
        raise OSError("crt.sh is down")
    monkeypatch.setattr(tools, "_http_bytes", boom)
    ing = ingest("open x-y.xyz now")
    tr = Trace()
    f = tools.Findings(hosts=list(ing.entities.hosts))
    assert tools.ToolGate(ing, "", tr).run([("cert_history", "x-y.xyz")], f) == 1
    assert f.certs == {} and ("cert_history", "x-y.xyz") in f.done and any("unavailable" in s.detail for s in tr.steps)


def test_an_answer_is_remembered_so_the_free_service_is_asked_once_per_domain(monkeypatch):
    calls = []
    monkeypatch.setattr(tools, "_http_bytes", lambda url, **kw: calls.append(url) or crt(900))
    a = tools.cert_history("login.shop.example.com")
    b = tools.cert_history("www.example.com")
    assert len(calls) == 1 and a["first_days"] == b["first_days"] == 900 and b["host"] == "www.example.com"


def test_after_an_error_the_free_service_is_left_alone_for_a_few_minutes(monkeypatch):
    from urllib.error import HTTPError
    calls = []

    def limited(url, **kw):
        calls.append(url)
        raise HTTPError(url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(tools, "_http_bytes", limited)
    for h in ("a-one.xyz", "b-two.xyz", "c-three.xyz"):
        with pytest.raises(OSError if h == "a-one.xyz" else RuntimeError):
            tools.cert_history(h)
    assert len(calls) == 1  # one 429, then no more requests until the pause is over
    monkeypatch.setitem(tools._cert_pause, "until", 0.0)
    monkeypatch.setattr(tools, "_http_bytes", lambda url, **kw: crt(10))
    assert tools.cert_history("d-four.xyz")["first_days"] == 10


def test_it_is_a_network_tool_so_it_is_off_with_the_other_network_tools():
    ing = ingest("open x-y.xyz now")
    f = tools.Findings(hosts=list(ing.entities.hosts))
    assert tools.ToolGate(ing, "", Trace()).run([("cert_history", "x-y.xyz")], f) == 0  # BAITPROOF_NET_TOOLS=0 in tests


# ---------------------------------------------------------------- what it means
def ledger_for(f):
    ing = ingest("Please open acme-docs.xyz to see it")
    it = SimpleNamespace(asks=set(), high_risk=set(), claimed_kind="", pressure=False, pressure_kinds=set(), scenario="", mismatches=[], model_scenario="", evidence={}, opener="")
    L = Ledger()
    analysis.rule_evidence(ing, it, f, L)
    return L


def test_a_brand_new_certificate_is_a_weak_flag_never_more():
    L = ledger_for(tools.Findings(hosts=["acme-docs.xyz"], certs={"acme-docs.xyz": 3}))
    (e,) = [e for e in L.items if e.source == "cert_history"]
    assert e.supports == "scam" and e.strength == "weak"  # a domain can exist for years before it gets its first certificate


def test_years_of_certificates_is_weak_reassurance():
    (e,) = [e for e in ledger_for(tools.Findings(hosts=["acme-docs.xyz"], certs={"acme-docs.xyz": 2000})).items if e.source == "cert_history"]
    assert e.supports == "safe" and e.strength == "weak" and "5 years" in e.claim


def test_the_registry_wins_when_it_answered():
    f = tools.Findings(hosts=["acme-docs.xyz"], ages={"acme-docs.xyz": 400}, certs={"acme-docs.xyz": 3})  # the domain was re-registered; the certificates are the old owner's
    assert not [e for e in ledger_for(f).items if e.source == "cert_history"]
    assert f.age_of("acme-docs.xyz") == 400 and "security certificate" not in f.summary()


def test_the_certificate_clock_can_stand_in_for_a_silent_registry():
    f = tools.Findings(hosts=["old-club.org"], certs={"old-club.org": 3000}, dns={"old-club.org": "ok"})
    assert f.age_of("old-club.org") == 3000 and f.all_links_established()
    f.certs["old-club.org"] = 100
    assert not f.all_links_established()
    f.certs["old-club.org"] = None
    assert f.age_of("old-club.org") is None


def test_the_links_panel_shows_the_certificate_note_only_when_the_registry_said_nothing():
    ing = ingest("open old-club.org now")
    (k,) = linkinfo.build(ing, tools.Findings(hosts=["old-club.org"], certs={"old-club.org": 3000}, dns={"old-club.org": "ok"}), "en")
    assert k.status == "established" and any("certificates on record" in n for n in k.notes)
    (k,) = linkinfo.build(ing, tools.Findings(hosts=["old-club.org"], ages={"old-club.org": 3000}, certs={"old-club.org": 3000}, dns={"old-club.org": "ok"}), "en")
    assert not any("certificate" in n for n in k.notes)


def test_the_planner_asks_for_the_certificate_log_in_the_same_round_as_the_registry(net):
    ing = ingest("Your invoice: https://billing.acme-docs.xyz/inv/1")
    f = tools.Findings(hosts=list(ing.entities.hosts))
    gate = tools.ToolGate(ing, "", Trace())
    qs = planner.open_questions(ing, SimpleNamespace(claimed="", claimed_kind="", disagreements=[]), f, gate)
    (q,) = [q for q in qs if q.key.startswith("host:")]
    assert {t for t, _ in q.calls} == {"domain_age", "dns_check", "cert_history"}


# ---------------------------------------------------------------- phone numbers
@pytest.mark.parametrize("num,kind", [
    ("+18765550123", "caribbean"), ("8765550123", "caribbean"), ("18764565123", "caribbean"),
    ("+447012345678", "personal"), ("07012345678", "personal"), ("447012345678", "personal"),
    ("09061234567", "premium"), ("+19005551234", "premium"),
    ("8005551234", "tollfree"), ("+442079460958", "unknown"), ("+6591234567", "unknown"), ("+60123456789", "unknown"),
])
def test_phone_check_reads_the_number_with_offline_rules(num, kind):
    assert tools.phone_check(num)["kind"] == kind


def test_a_sloppy_number_still_gets_the_older_prefix_check():
    # scam texts are often malformed: these are not valid numbers, but the prefix still says what they are (measured: dropping this lost 13 of 1,019 real catches)
    for num, kind in (("087187272008", "premium"), ("0906346330", "premium"), ("8760000000", "caribbean"), ("7679046492", "caribbean")):
        assert tools.phone_check(num)["kind"] == kind


def test_the_library_only_adds_to_what_the_prefix_rules_find():
    for num in ("18765550123", "19005550123", "08718726270150", "1900123456", "8005551234", "442071234567"):
        old = tools._phone_check_prefix(num)["kind"]
        assert old == "unknown" or tools.phone_check(num)["kind"] == old
    assert tools.phone_check("07012345678")["kind"] == "personal" and tools._phone_check_prefix("07012345678")["kind"] == "unknown"  # a new finding


def test_without_the_package_the_older_prefix_rules_still_run(monkeypatch):
    monkeypatch.setattr(tools, "phonenumbers", None)
    assert tools.phone_check("18765550123")["kind"] == "caribbean" and tools.phone_check("19005550123")["kind"] == "premium"


def test_a_personal_number_is_medium_evidence_with_the_number_quoted():
    ing = ingest("Please call me back on 07012 345678 today")
    it = SimpleNamespace(asks=set(), high_risk=set(), claimed_kind="", pressure=False, pressure_kinds=set(), scenario="", mismatches=[], model_scenario="", evidence={}, opener="")
    L = Ledger()
    f = tools.Findings(hosts=[], phones={ing.entities.phones[0]: "personal"})
    analysis.rule_evidence(ing, it, f, L)
    (e,) = [e for e in L.items if e.source == "phone_check"]
    assert e.supports == "scam" and e.strength == "medium" and "070" in e.claim and e.quote == "07012 345678"
    assert "personal number" in f.summary()
