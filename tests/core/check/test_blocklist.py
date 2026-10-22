"""The public phishing list: a local file, refreshed in the background, asked about by the blocklist_check tool. The download is always faked here."""
import os
import time
from types import SimpleNamespace

import pytest

from core.domain.schemas import Verdict as V
from core.pipelines.check import analysis, blocklist, check_message, linkinfo, tools
from core.pipelines.check.evidence import Ledger
from core.pipelines.check.ingest import ingest
from core.pipelines.check.trace import Trace

LIST = "# comment\nPhishy-Bank-Login.xyz\nwww.pay-now-parcel.top\nnot a host\n\nlogin.evil-site.cc.\nUPPER.example.net\nplain\nweeblysite.com\nbad-page.weeblysite.com\n"


@pytest.fixture
def listed():
    """A local list holding a few names."""
    blocklist.install(blocklist.parse(LIST))


def gate_for(text):
    ing = ingest(text)
    return ing, tools.ToolGate(ing, "", Trace()), tools.Findings(hosts=list(ing.entities.hosts))


# ---------------------------------------------------------------- the list file
def test_parse_keeps_only_names_shaped_like_hosts():
    assert blocklist.parse(LIST) == ["phishy-bank-login.xyz", "pay-now-parcel.top", "login.evil-site.cc", "upper.example.net", "weeblysite.com", "bad-page.weeblysite.com"]


def test_install_lookup_and_size(listed):
    assert blocklist.available() and blocklist.size() == 6
    assert blocklist.lookup(["nothing.com", "pay-now-parcel.top"]) == "pay-now-parcel.top"
    assert blocklist.lookup(["nothing.com"]) == "" and blocklist.lookup([]) == ""


def test_no_list_means_no_answer_not_a_crash():
    assert not blocklist.available() and blocklist.lookup(["pay-now-parcel.top"]) == "" and blocklist.size() == 0 and blocklist.age_seconds() is None
    assert tools.blocklist_check("pay-now-parcel.top") == {"host": "pay-now-parcel.top", "status": "unavailable", "listed": ""}


def test_a_damaged_file_is_a_missing_list(listed):
    blocklist.db_path().write_bytes(b"this is not a database at all, " * 50)
    assert blocklist.lookup(["pay-now-parcel.top"]) == "" and blocklist.size() == 0


def test_the_list_can_be_switched_off(listed, monkeypatch):
    monkeypatch.setenv("BAITPROOF_BLOCKLIST", "0")
    assert not blocklist.available() and tools.blocklist_check("pay-now-parcel.top")["status"] == "unavailable"


def test_refresh_downloads_when_missing_and_skips_while_fresh():
    calls = []
    big = "\n".join(f"scam{i}.example.xyz" for i in range(1500))

    def fetch():
        calls.append(1)
        return big
    assert blocklist.refresh(fetch=fetch) == 1500 and blocklist.size() == 1500
    assert blocklist.refresh(fetch=fetch) is None and len(calls) == 1  # fresh: nothing to do
    old = time.time() - blocklist.MAX_AGE - 60
    os.utime(blocklist.db_path(), (old, old))
    assert blocklist.stale() and blocklist.refresh(fetch=fetch) == 1500 and len(calls) == 2
    assert blocklist.refresh(force=True, fetch=fetch) == 1500 and len(calls) == 3


def test_a_bad_download_never_replaces_a_good_list(listed):
    old = time.time() - blocklist.MAX_AGE - 60
    os.utime(blocklist.db_path(), (old, old))
    with pytest.raises(ValueError):
        blocklist.refresh(fetch=lambda: "<html>502 Bad Gateway</html>")
    assert blocklist.size() == 6 and blocklist.lookup(["pay-now-parcel.top"])  # still the old list
    with pytest.raises(OSError):
        blocklist.refresh(fetch=lambda: (_ for _ in ()).throw(OSError("offline")))
    assert blocklist.size() == 6


def test_the_background_refresher_stays_off_when_the_network_tools_are_off(monkeypatch):
    monkeypatch.setattr(blocklist, "_started", False)
    assert blocklist.start_background() is False  # the test setup turns the network tools off
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")
    monkeypatch.setenv("BAITPROOF_BLOCKLIST", "0")
    assert blocklist.start_background() is False


# ---------------------------------------------------------------- the tool
def test_blocklist_check_matches_the_name_and_its_registered_domain(listed):
    assert tools.blocklist_check("phishy-bank-login.xyz")["status"] == "listed"
    d = tools.blocklist_check("secure.phishy-bank-login.xyz")  # a throwaway subdomain of a listed site
    assert d["status"] == "listed" and d["listed"] == "phishy-bank-login.xyz"
    assert tools.blocklist_check("fine-site.example.org") == {"host": "fine-site.example.org", "status": "clean", "listed": ""}


def test_on_shared_hosting_only_the_exact_name_counts(listed):
    assert tools.blocklist_check("bad-page.weeblysite.com")["status"] == "listed"
    assert tools.blocklist_check("lovely-shop.weeblysite.com")["status"] == "clean"  # weeblysite.com itself is listed, but anyone can open a page there


def test_a_shortener_or_an_open_platform_is_never_judged_by_the_list():
    # the real Phishing.Database carries bit.ly, bit.do, x.co and sites.google.com: a warning on every such link would be wrong far more often than right
    blocklist.install(["bit.ly", "bit.do", "sites.google.com", "weeblysite.com", "evil-page.weeblysite.com"])
    for h in ("bit.ly", "bit.do", "sites.google.com", "weeblysite.com"):
        assert tools.blocklist_check(h) == {"host": h, "status": "exempt", "listed": ""}
    assert tools.blocklist_check("evil-page.weeblysite.com")["status"] == "listed"  # a page on a platform is judged by its own name
    r = check_message("Here is the file you asked for: https://sites.google.com/view/team-notes")
    assert not any(e.source == "blocklist_check" for e in r.evidence)


def test_it_only_looks_up_a_link_that_is_in_the_message_and_never_uses_the_network(listed, monkeypatch):
    monkeypatch.setattr(tools, "_http_bytes", lambda *a, **k: pytest.fail("the list is local"))
    ing, g, f = gate_for("Your parcel: pay-now-parcel.top/track")
    assert g.run([("blocklist_check", "pay-now-parcel.top"), ("blocklist_check", "model-invented.com")], f) == 1
    assert f.listed == {"pay-now-parcel.top": "pay-now-parcel.top"}
    assert ("blocklist_check", "pay-now-parcel.top") in tools.initial_calls(ing)  # asked in round 0, with the other free checks


def test_the_destination_of_a_short_link_is_looked_up_too(listed, monkeypatch):
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")
    monkeypatch.setattr(tools, "expand_link", lambda url: {"url": url, "host": "bit.ly", "dest": "pay-now-parcel.top", "hops": 1, "status": "expanded"})
    monkeypatch.setitem(tools.SPECS, "expand_link", tools.Spec("expand_link", "url", tools.expand_link, "d", net=True))
    ing, g, f = gate_for("Delivery fee: bit.ly/3xK9pQ2")
    f.shorts = {u: "" for u in ing.entities.urls}
    g.run([("expand_link", u) for u in ing.entities.urls], f)
    assert "pay-now-parcel.top" in f.listed and "pay-now-parcel.top" in f.suspicious_hosts


# ---------------------------------------------------------------- what it means
def ledger_for(f, text="Please open pay-now-parcel.top to see it"):
    ing = ingest(text)
    it = SimpleNamespace(asks=set(), high_risk=set(), claimed_kind="", pressure=False, pressure_kinds=set(), scenario="", mismatches=[], model_scenario="", evidence={}, opener="")
    L = Ledger()
    analysis.rule_evidence(ing, it, f, L)
    return L


def test_a_listed_link_is_graded_by_what_else_is_known():
    # The real list carries some popular sites (gravatar.com, pastebin.com, telegra.ph: a bad page was once hosted there), so one hit is medium on its own...
    f = tools.Findings(hosts=["pay-now-parcel.top"], listed={"pay-now-parcel.top": "pay-now-parcel.top"})
    (hit,) = [e for e in ledger_for(f, "Please open sunny-album.net to see it").items if e.source == "blocklist_check"]
    assert hit.supports == "scam" and hit.strength == "medium" and "pay-now-parcel.top" in hit.quote and hit.tactic == "lookalike-link"
    assert "public list of known phishing" in f.summary()
    # ...strong when anything else is wrong (a rush to pay, a throwaway ending) or the site is brand new...
    (hit,) = [e for e in ledger_for(f, "URGENT: pay the fee now at pay-now-parcel.top or lose it").items if e.source == "blocklist_check"]
    assert hit.strength == "strong"
    f.ages = {"pay-now-parcel.top": 30}
    assert [e.strength for e in ledger_for(f, "Please open sunny-album.net to see it").items if e.source == "blocklist_check"] == ["strong"]
    # ...and weak for a site that has existed for over ten years
    f.ages = {"pay-now-parcel.top": 4000}
    assert [e.strength for e in ledger_for(f, "URGENT: pay the fee now at pay-now-parcel.top or lose it").items if e.source == "blocklist_check"] == ["weak"]
    f.ages, f.certs = {}, {"pay-now-parcel.top": 4000}  # the certificate log counts as a floor for the age
    assert [e.strength for e in ledger_for(f, "Please open sunny-album.net to see it").items if e.source == "blocklist_check"] == ["weak"]


def test_the_grade_is_redone_each_round_as_facts_arrive():
    ing = ingest("Please open sunny-album.net to see it")
    it = SimpleNamespace(asks=set(), high_risk=set(), claimed_kind="", pressure=False, pressure_kinds=set(), scenario="", mismatches=[], model_scenario="", evidence={}, opener="")
    f = tools.Findings(hosts=["sunny-album.net"], listed={"sunny-album.net": "sunny-album.net"})
    L = Ledger()
    grades = []
    for ages in ({}, {"sunny-album.net": 20}, {"sunny-album.net": 5000}):  # round 1: no age yet; round 2: brand new; (a different site) very old
        f.ages = ages
        analysis.rule_evidence(ing, it, f, L)
        grades.append([e.strength for e in L.items if e.source == "blocklist_check"])
    assert grades == [["medium"], ["strong"], ["weak"]]  # one item each time, never a stale copy beside the new one


def test_a_real_brands_own_site_is_never_overruled_by_a_list_entry():
    f = tools.Findings(hosts=["amazon.com"], listed={"amazon.com": "amazon.com"}, official_hosts={"amazon.com": "amazon"})
    assert not [e for e in ledger_for(f, "see amazon.com").items if e.source == "blocklist_check"]


PHOTOS = "Hello, here are the photos from the weekend: sunny-album.net/photos"  # nothing odd about this address or the message, except that the list knows it


def test_an_innocent_looking_message_with_a_listed_link_is_called_a_scam():
    blocklist.install(["sunny-album.net"])
    r = check_message(PHOTOS)
    assert r.verdict in (V.SCAM, V.LIKELY_SCAM)
    assert any(e.source == "blocklist_check" and e.strength == "medium" for e in r.evidence)
    assert [k.status for k in r.links] == ["known_phishing"] and r.links[0].label


def test_the_same_message_without_the_list_is_not_called_a_scam():
    r = check_message(PHOTOS)
    assert r.verdict not in (V.SCAM, V.LIKELY_SCAM) and not any(e.source == "blocklist_check" for e in r.evidence)


def test_the_links_panel_marks_a_listed_site_in_every_language():
    ing = ingest("open pay-now-parcel.top now")
    f = tools.Findings(hosts=["pay-now-parcel.top"], listed={"pay-now-parcel.top": "pay-now-parcel.top"})
    (k,) = linkinfo.build(ing, f, "en")
    assert k.status == "known_phishing" and k.label == "Known phishing website" and any("public list" in n for n in k.notes)
    (z,) = linkinfo.build(ing, f, "zh")
    assert z.status == "known_phishing" and "钓鱼" in z.label and "钓鱼" in " ".join(z.notes)


def test_a_listed_link_is_never_treated_as_established():
    f = tools.Findings(hosts=["old-site.com"], ages={"old-site.com": 4000}, dns={"old-site.com": "ok"}, listed={"old-site.com": "old-site.com"})
    assert not f.all_links_established()
    f.listed.clear()
    assert f.all_links_established()
