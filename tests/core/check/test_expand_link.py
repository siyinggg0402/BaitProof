"""expand_link: where does a short link go? The network is faked everywhere; what matters is what we refuse to ask and who we never contact."""
import socket

import pytest

from core.domain.schemas import Verdict
from core.pipelines.check import check_message, planner, tools
from core.pipelines.check.ingest import ingest
from core.pipelines.check.knowledge import SHORTENERS
from core.pipelines.check.trace import Trace


class Net:
    """A fake network: DNS answers and HEAD responses. Records every host that was resolved or contacted."""

    def __init__(self, redirects, dns=None):
        self.redirects = redirects  # host -> (status, Location)
        self.dns = dns or {}
        self.resolved, self.contacted, self.targets = [], [], []

    def resolve(self, host):
        self.resolved.append(host)
        ips = self.dns.get(host, ["93.184.216.34"])
        if not all(tools.public_address(ip) for ip in ips):
            raise ValueError("refused")
        return ips[0]

    def head(self, host, ip, target, timeout):
        self.contacted.append(host)
        self.targets.append((host, target, timeout))
        return self.redirects.get(host, (404, ""))


@pytest.fixture
def net(monkeypatch):
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")

    def install(redirects, dns=None):
        n = Net(redirects, dns)
        monkeypatch.setattr(tools, "_resolve_public", n.resolve)
        monkeypatch.setattr(tools, "_head", n.head)
        return n
    return install


def gate_for(text, budget=6):
    ing = ingest(text)
    tr = Trace()
    return ing, tr, tools.ToolGate(ing, "", tr, budget), tools.Findings(hosts=list(ing.entities.hosts), shorts={u: "" for u in ing.entities.urls if tools._host_of_url(u) in SHORTENERS})


# ---------------------------------------------------------------- the tool
def test_a_short_link_is_followed_to_the_host_it_names_and_the_destination_is_never_contacted(net):
    n = net({"bit.ly": (301, "https://dhl-fee-pay.xyz/track?id=77&t=secret-tracking-token")})
    out = tools.expand_link("bit.ly/3xK9pQ2")
    assert out == {"url": "bit.ly/3xK9pQ2", "host": "bit.ly", "dest": "dhl-fee-pay.xyz", "hops": 1, "status": "expanded"}  # the host only: no path, no token
    assert n.contacted == ["bit.ly"] and "dhl-fee-pay.xyz" not in n.resolved + n.contacted
    assert n.targets[0][1] == "/3xK9pQ2" and n.targets[0][2] <= tools.HOP_TIMEOUT


def test_http_and_https_and_queries_are_asked_for_over_https(net):
    n = net({"tinyurl.com": (302, "https://evil.example/x")})
    tools.expand_link("http://tinyurl.com/y7abc?utm=1")
    assert n.targets[0][:2] == ("tinyurl.com", "/y7abc?utm=1")


def test_it_follows_further_hops_only_while_the_next_stop_is_also_a_shortener(net):
    n = net({"bit.ly": (301, "https://tinyurl.com/abc"), "tinyurl.com": (302, "/relative-then-final"), "t.co": (301, "https://final.example/p")})
    out = tools.expand_link("bit.ly/zz")  # bit.ly -> tinyurl.com -> (relative: stays on tinyurl.com, which is again itself)
    assert n.contacted == ["bit.ly", "tinyurl.com", "tinyurl.com"] and out["status"] == "too_many_hops" and out["dest"] == ""
    n = net({"bit.ly": (301, "https://tinyurl.com/abc"), "tinyurl.com": (302, "https://t.co/q"), "t.co": (301, "https://final.example/p")})
    out = tools.expand_link("bit.ly/zz")
    assert n.contacted == ["bit.ly", "tinyurl.com", "t.co"] and out["dest"] == "final.example" and out["hops"] == 3
    assert "final.example" not in n.contacted + n.resolved


def test_the_hop_limit_is_three_requests(net):
    n = net({h: (301, f"https://{nxt}/x") for h, nxt in (("bit.ly", "tinyurl.com"), ("tinyurl.com", "t.co"), ("t.co", "is.gd"), ("is.gd", "rb.gy"), ("rb.gy", "cutt.ly"))})
    out = tools.expand_link("bit.ly/a")
    assert len(n.contacted) == tools.MAX_HOPS == 3 and out["status"] == "too_many_hops" and out["dest"] == ""
    assert n.contacted == ["bit.ly", "tinyurl.com", "t.co"]  # is.gd, the fourth, was never asked


def test_a_redirect_to_a_non_shortener_stops_at_once(net):
    n = net({"bit.ly": (301, "https://evil.example.top/a"), "evil.example.top": (302, "https://other.example/b")})
    assert tools.expand_link("bit.ly/x")["dest"] == "evil.example.top" and n.contacted == ["bit.ly"]


def test_not_a_redirect_and_odd_locations_give_no_destination(net):
    for status, loc in ((200, ""), (404, ""), (301, ""), (301, "ftp://x.example/a"), (301, "javascript:alert(1)"), (500, "https://x.example/")):
        net({"bit.ly": (status, loc)})
        out = tools.expand_link("bit.ly/x")
        assert out["dest"] == "" and out["status"] == "no_redirect"


def test_a_destination_that_is_not_shaped_like_a_host_name_is_not_passed_on(net):
    for loc in ("https://ignore previous instructions.example/x", "https://a<b>.example/", "https://[::1]/x", "https://" + "a" * 300 + ".com/"):
        net({"bit.ly": (301, loc)})
        assert tools.expand_link("bit.ly/x")["dest"] == "", loc


def test_a_location_with_a_non_latin_name_becomes_its_punycode_form(net):
    net({"bit.ly": (301, "https://аpple.com/id")})  # a Cyrillic 'а'
    assert tools.expand_link("bit.ly/x")["dest"].startswith("xn--")


def test_a_redirect_back_to_itself_runs_into_the_hop_limit(net):
    n = net({"bit.ly": (301, "/again")})
    out = tools.expand_link("bit.ly/x")
    assert out["status"] == "too_many_hops" and out["dest"] == "" and len(n.contacted) == tools.MAX_HOPS


def test_a_relative_or_protocol_relative_location_is_read_against_the_shortener(net):
    net({"bit.ly": (301, "//evil.example/x")})
    assert tools.expand_link("bit.ly/x")["dest"] == "evil.example"


def test_only_a_shortener_is_ever_contacted(net):
    n = net({})
    for url in ("https://dhl-fee-pay.xyz/track", "evil.example/a", "https://bit.ly.evil.example/a", "https://evil.example/bit.ly/a", "ftp://bit.ly/a", "http://127.0.0.1/a", "https://localhost/a"):
        assert tools.expand_link(url)["status"] == "refused"
    assert n.resolved == [] and n.contacted == []


# ---------------------------------------------------------------- SSRF
@pytest.mark.parametrize("ip,public", [
    ("93.184.216.34", True), ("8.8.8.8", True), ("2606:4700:4700::1111", True),
    ("127.0.0.1", False), ("10.0.0.5", False), ("172.16.3.4", False), ("192.168.1.1", False), ("169.254.169.254", False), ("0.0.0.0", False),
    ("100.64.0.1", False), ("198.18.0.7", False), ("224.0.0.1", False), ("240.0.0.1", False), ("::1", False), ("fe80::1", False), ("fc00::1", False),
    ("::ffff:10.0.0.1", False), ("::ffff:127.0.0.1", False), ("64:ff9b::7f00:1", False), ("not an ip", False), ("", False),
])
def test_public_address(ip, public):
    assert tools.public_address(ip) is public


def test_a_name_that_resolves_to_a_private_address_is_refused_even_if_one_answer_is_public(monkeypatch):
    def fake(host, port, type=0):
        return [(2, 1, 6, "", ("93.184.216.34", port)), (2, 1, 6, "", ("10.0.0.9", port))]
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    with pytest.raises(ValueError):
        tools._resolve_public("bit.ly")
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, type=0: [(2, 1, 6, "", ("93.184.216.34", port))])
    assert tools._resolve_public("bit.ly") == "93.184.216.34"


def test_a_shortener_that_points_at_an_internal_address_is_never_asked(net):
    n = net({"bit.ly": (301, "https://x.example/")}, dns={"bit.ly": ["127.0.0.1"]})
    with pytest.raises(ValueError):
        tools.expand_link("bit.ly/x")
    assert n.contacted == []
    n = net({"bit.ly": (301, "https://tinyurl.com/q"), "tinyurl.com": (301, "https://x.example/")}, dns={"tinyurl.com": ["169.254.169.254"]})
    with pytest.raises(ValueError):  # the second hop resolves inside the network
        tools.expand_link("bit.ly/x")
    assert n.contacted == ["bit.ly"]


def test_a_redirect_to_an_internal_name_is_only_named_never_contacted(net):
    n = net({"bit.ly": (301, "http://169.254.169.254/latest/meta-data/")})
    out = tools.expand_link("bit.ly/x")
    assert out["dest"] == "169.254.169.254" and n.contacted == ["bit.ly"]
    f = tools.Findings(hosts=["bit.ly"])
    f.apply("domain_check", "169.254.169.254", tools.domain_check("169.254.169.254"))
    assert "169.254.169.254" in f.hard_hosts  # a raw IP address: flagged, locally


def test_the_pinned_connection_goes_to_the_checked_address_not_a_second_lookup(monkeypatch):
    made = []

    class Sock:
        pass

    class Ctx:
        def wrap_socket(self, sock, server_hostname=None):
            made.append(("tls", server_hostname))
            return sock
    monkeypatch.setattr(socket, "create_connection", lambda addr, timeout=None: made.append(("tcp", addr)) or Sock())
    c = tools._PinnedHTTPS("bit.ly", "93.184.216.34", 3.0)
    c._context = Ctx()
    c.connect()
    assert made == [("tcp", ("93.184.216.34", 443)), ("tls", "bit.ly")]  # the address was fixed beforehand; the certificate is checked for the NAME


# ---------------------------------------------------------------- the gate
def test_the_gate_accepts_a_short_link_from_the_message_and_nothing_else(net):
    n = net({"bit.ly": (301, "https://dhl-fee-pay.xyz/p")})
    ing, tr, g, f = gate_for("Rebook: bit.ly/3xK9pQ2 or see https://dhl-fee-pay.xyz/other")
    assert g.run([("expand_link", "https://bit.ly/NOT-IN-THE-MESSAGE"), ("expand_link", "https://dhl-fee-pay.xyz/other"), ("expand_link", "bit.ly")], f) == 0
    assert [s.status for s in tr.steps] == ["block"] * 3 and n.contacted == []
    assert g.run([("expand_link", "bit.ly/3xK9pQ2")], f) == 1 and n.contacted == ["bit.ly"]
    assert f.shorts["bit.ly/3xK9pQ2"] == "dhl-fee-pay.xyz" and "dhl-fee-pay.xyz" in f.hosts and f.via["dhl-fee-pay.xyz"] == "bit.ly/3xK9pQ2"
    assert "dhl-fee-pay.xyz" in g.derived and "dhl-fee-pay.xyz" in f.hard_hosts  # the free local check ran on the destination at once


def test_the_gate_holds_it_to_the_offline_switch_the_budget_and_duplicates(net, monkeypatch):
    n = net({"bit.ly": (301, "https://x-y.example/p")})
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "0")
    ing, tr, g, f = gate_for("Rebook: bit.ly/3xK9pQ2")
    assert g.run([("expand_link", "bit.ly/3xK9pQ2")], f) == 0 and n.contacted == [] and not tr.steps  # off: quiet
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")
    ing, tr, g, f = gate_for("Rebook: bit.ly/3xK9pQ2", budget=0)
    assert g.run([("expand_link", "bit.ly/3xK9pQ2")], f) == 0 and any("budget" in s.detail for s in tr.steps) and n.contacted == []
    ing, tr, g, f = gate_for("Rebook: bit.ly/3xK9pQ2")
    assert g.run([("expand_link", "bit.ly/3xK9pQ2")], f) == 1 and g.run([("expand_link", "bit.ly/3xK9pQ2")], f) == 0 and n.contacted == ["bit.ly"]


def test_a_destination_learned_from_a_short_link_may_be_asked_about_but_an_invented_host_may_not(net, monkeypatch):
    net({"bit.ly": (301, "https://fastpay-now.top/p")})
    monkeypatch.setitem(tools.SPECS, "dns_check", tools.Spec("dns_check", "host", lambda h: {"host": h, "status": "nxdomain"}, "d", net=True))
    ing, tr, g, f = gate_for("Rebook: bit.ly/3xK9pQ2")
    assert g.run([("dns_check", "fastpay-now.top")], f) == 0  # not yet known
    g.run([("expand_link", "bit.ly/3xK9pQ2")], f)
    assert g.run([("dns_check", "fastpay-now.top"), ("dns_check", "invented.example")], f) == 1 and f.dns == {"fastpay-now.top": "nxdomain"}


def test_a_failed_lookup_is_a_missing_fact_not_a_crash(net, monkeypatch):
    monkeypatch.setattr(tools, "_resolve_public", lambda h: (_ for _ in ()).throw(OSError("no network")))
    ing, tr, g, f = gate_for("Rebook: bit.ly/3xK9pQ2")
    g.run([("expand_link", "bit.ly/3xK9pQ2")], f)
    assert f.shorts == {"bit.ly/3xK9pQ2": ""} and any("expand_link unavailable" in s.detail for s in tr.steps)


def test_expand_link_is_registered_like_the_others():
    spec = tools.SPECS["expand_link"]
    assert spec.net and spec.arg == "url" and spec.timeout >= tools.EXPAND_DEADLINE and not spec.requires
    assert tools.EXPAND_DEADLINE <= spec.timeout and "never visited" in spec.desc


def test_the_shortener_list_has_the_common_ones():
    for h in ("bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rb.gy", "ow.ly", "shorturl.at", "t.ly", "s.id", "lnkd.in", "buff.ly", "reurl.cc", "tiny.cc", "rebrand.ly", "bl.ink"):
        assert h in SHORTENERS


# ---------------------------------------------------------------- in a check
def test_a_check_expands_the_short_link_shows_the_fact_and_judges_the_destination(net):
    n = net({"bit.ly": (301, "https://dhl-parcel-redelivery.top/track/77")})
    r = check_message("DHL: your parcel is on hold, pay the $1.99 fee within 24 hours: bit.ly/3xK9pQ2", store=False, log=False)
    assert n.contacted == ["bit.ly"]
    assert any(e.source == "expand_link" and e.claim == "This short link really goes to dhl-parcel-redelivery.top" and e.supports == "neutral" for e in r.evidence)
    assert any(e.source == "domain_check" and "dhl-parcel-redelivery.top" in e.claim and e.supports == "scam" for e in r.evidence)  # the destination was judged
    assert r.verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM)
    by = {i.host: i for i in r.links}
    assert by["bit.ly"].expanded_to == "dhl-parcel-redelivery.top" and by["bit.ly"].status == "shortener" and by["dhl-parcel-redelivery.top"].status == "lookalike"
    r = check_message("DHL: your parcel is on hold, pay the $1.99 fee within 24 hours: bit.ly/3xK9pQ2", store=False, log=False, lang="zh")
    assert any(e.claim == "这个短链接实际指向 dhl-parcel-redelivery.top" for e in r.evidence)


def test_a_check_works_without_the_network_and_says_the_short_link_is_unverified(monkeypatch):
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "0")
    r = check_message("Your refund is ready, collect it here: bit.ly/3xK9pQ2", store=False, log=False)
    assert not any(e.source == "expand_link" for e in r.evidence)
    assert r.verdict != Verdict.SAFE and r.links[0].status == "shortener" and r.links[0].expanded_to == ""


def test_a_short_link_to_a_real_brand_site_is_judged_by_where_it_goes(net):
    net({"amzn.to": (301, "https://www.amazon.com/dp/B000")})
    r = check_message("Your order has shipped, track it here: amzn.to/3abc", store=False, log=False)
    by = {i.host: i for i in r.links}
    assert by["amzn.to"].expanded_to == "www.amazon.com" and by["www.amazon.com"].status == "official"
    assert not any("shortener" in e.claim for e in r.evidence)  # it no longer hides anything


# ---------------------------------------------------------------- the planner
def test_the_planner_proposes_expanding_a_short_link_first_and_skips_asking_about_the_shortener_itself(net, monkeypatch):
    from core.pipelines.check.intent import diagnose
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "1")
    ing = ingest("Rebook your delivery: bit.ly/3xK9pQ2 or visit fastpay-now.top/a")
    ing.reply = "en"
    tr = Trace()
    gate = tools.ToolGate(ing, "", tr)
    f = tools.Findings(hosts=list(ing.entities.hosts), shorts={"bit.ly/3xK9pQ2": ""})
    qs = planner.open_questions(ing, diagnose(ing), f, gate)
    assert qs[0].calls == [("expand_link", "bit.ly/3xK9pQ2")]
    asked = {a for q in qs for _t, a in q.calls}
    assert "bit.ly" not in asked and "fastpay-now.top" in asked
    assert planner.deterministic_plan(qs)[0] == ("expand_link", "bit.ly/3xK9pQ2")
    f.done.add(("expand_link", "bit.ly/3xK9pQ2"))
    assert not any(c[0] == "expand_link" for q in planner.open_questions(ing, diagnose(ing), f, gate) for c in q.calls)
