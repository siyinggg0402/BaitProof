"""Links written to dodge a filter, spoken links, short-link detection, and the Links panel. expand_link: where does a short link go? The network is faked everywhere; what matters is what we refuse to ask and who we never contact."""
import socket

import pytest

from core.domain.schemas import LinkInfo, Verdict
from core.pipelines.check import check_message
from core.pipelines.check import links as LK
from core.pipelines.check import linkinfo
from core.pipelines.check import planner, tools
from core.pipelines.check.ingest import ingest
from core.pipelines.check.knowledge import SHORTENERS
from core.pipelines.check.tools import Findings, domain_check
from core.pipelines.check.trace import Trace


# ---------------------------------------------------------------- de-obfuscation
@pytest.mark.parametrize("raw,clean", [
    ("Pay at hxxps://dhl-fee[.]xyz/track now", "Pay at https://dhl-fee.xyz/track now"),
    ("hXXp://evil(.)top/x", "http://evil.top/x"),
    ("go to dhl-fee(.)top/x or evil[dot]cc", "go to dhl-fee.top/x or evil.cc"),
    ("hxxp[:]//bad[.]top", "http://bad.top"),
    ("a{.}xyz and b [.] top and c ( dot ) cc", "a.xyz and b.top and c.cc"),
    ("visit www。dhl-fee。com now", "visit www.dhl-fee.com now"),
    ("请点击 dhl-fee。xyz/track 补全", "请点击 dhl-fee.xyz/track 补全"),
    ("访问 ｄｈｌ－ｆｅｅ．ｘｙｚ 查看", "访问 dhl-fee.xyz 查看"),
    ("link: dhl\\.fee\\.xyz", "link: dhl.fee.xyz"),
    ("visit dhl-fee. xyz/track today", "visit dhl-fee.xyz/track today"),
    ("visit dhl-fee .xyz/track today", "visit dhl-fee.xyz/track today"),
    ("tap dhl-fee dot xyz now", "tap dhl-fee.xyz now"),
    ("amazon dot com/login", "amazon.com/login"),
    ("dhl​-fee.xyz", "dhl-fee.xyz"),  # a zero-width space hiding in the name
])
def test_deobfuscate(raw, clean):
    assert LK.deobfuscate(raw) == clean


@pytest.mark.parametrize("text", [
    "Reply stop. info is free", "call me. top priority", "I paid the bill. com on Monday", "the polka dot com idea", "user 0789xxxxxxx. today is your lucky day",
    "Hello. Click here", "see you at 5.30 today", "a lone [.] or (.) is nothing", "list item (.) done", "No links here at all, just words.", "这是一句话。然后另一句。", "Total: 3.5 million",
])
def test_ordinary_text_is_left_alone(text):
    assert LK.deobfuscate(text) == text


def test_obfuscated_links_are_found_but_the_original_text_is_untouched_and_it_is_no_scam_signal():
    raw = "Parcel on hold. Details: hxxps://dhl-fee[.]xyz/track"
    ing = ingest(raw)
    assert ing.text == raw  # the user's words, as written
    assert ing.entities.hosts == ["dhl-fee.xyz"] and ing.entities.urls == ["https://dhl-fee.xyz/track"]
    plain = check_message("Check my website hxxp://example[.]com/about for the photos", store=False, log=False)
    assert not any("obfus" in e.claim.lower() or "disguis" in e.claim.lower() for e in plain.evidence)
    assert [e.claim for e in check_message("see https://example.com/about", store=False, log=False).evidence if e.supports == "scam"] == \
           [e.claim for e in check_message("see hxxps://example[.]com/about", store=False, log=False).evidence if e.supports == "scam"]


def test_chinese_full_width_dots_in_a_message_find_the_host():
    ing = ingest("【顺丰】请于24小时内点击 sf-express-cn。top/addr 补全信息")
    assert "sf-express-cn.top" in ing.entities.hosts
    ing = ingest("请访问 ｗｗｗ．ｄｈｌ-ｆｅｅ．ｃｏｍ 领取")
    assert any(h.endswith("dhl-fee.com") for h in ing.entities.hosts)


def test_an_email_address_is_still_not_a_link_to_its_domain():
    assert ingest("write to claims@yahoo.com or claims@evil[.]top").entities.hosts == []


def test_short_links_without_a_scheme_are_links_too():
    ing = ingest("Pay now rb.gy/Ab3x or goo.gl/zZ9 or s.id/Pos8, thanks.")
    assert ing.entities.hosts == ["rb.gy", "goo.gl", "s.id"] and ing.entities.urls == ["rb.gy/Ab3x", "goo.gl/zZ9", "s.id/Pos8"]
    assert ingest("see http://bit.do/Claim-").entities.urls == ["http://bit.do/Claim-"]


def test_trailing_punctuation_is_not_part_of_the_link():
    assert ingest("Open (https://dhl-fee.xyz/a).").entities.urls == ["https://dhl-fee.xyz/a"]
    assert ingest("Open www.shortbreaks.org.uk!").entities.hosts == ["www.shortbreaks.org.uk"]


# ---------------------------------------------------------------- spoken links
@pytest.mark.parametrize("said,link", [
    ("go to dhl dash fee dash pay dot x y z slash track now", "go to dhl-fee-pay.xyz/track now"),
    ("Visit w w w dot dhl dash parcel dot com slash pay.", "Visit www.dhl-parcel.com/pay."),
    ("open h t t p s colon slash slash bit dot l y slash three x y z", "open https://bit.ly/3xyz"),
    ("visit dhl-fee-pay dot xyz slash track", "visit dhl-fee-pay.xyz/track"),
    ("D.H.L. dash F.E.E. dot X.Y.Z. slash track", "dhl-fee.xyz/track"),
    ("pay at dhl dash fee dash two four dot top slash a b c.", "pay at dhl-fee-24.top/abc."),
    ("it is paypal hyphen secure dot c c slash login", "it is paypal-secure.cc/login"),
    ("go to maybank underscore verify dot com", "go to maybank_verify.com"[:0] + "go to maybank underscore verify.com"),
])
def test_from_speech(said, link):
    assert LK.from_speech(said) == link


@pytest.mark.parametrize("text", ["the dot com bubble burst", "Call me on Monday", "a dot com business", "polka dot dress", "please dot the i", ""])
def test_from_speech_leaves_ordinary_speech_alone(text):
    assert LK.from_speech(text) == text


def test_a_spoken_link_is_then_checked_like_any_link():
    spoken = LK.from_speech("This is DHL. Your parcel is on hold, pay the fee at dhl dash fee dash pay dot x y z slash track within twenty four hours.")
    assert ingest(spoken).entities.hosts == ["dhl-fee-pay.xyz"]


# ---------------------------------------------------------------- the Links panel
def info_for(text, reply="en", **found):
    ing = ingest(text)
    f = Findings(hosts=list(ing.entities.hosts[:3]))
    for h in ing.entities.hosts[:3]:
        f.apply("domain_check", h, domain_check(h))
    for k, v in found.items():
        for h, val in v.items():
            f.apply(k, h, val)
    return linkinfo.build(ing, f, reply), ing, f


def test_a_real_site_a_lookalike_and_an_unknown_one():
    out, *_ = info_for("see dhl.com or dhl-parcel-uk.com/track or kindlyhelper.net/x")
    by = {i.host: i for i in out}
    assert by["dhl.com"].status == "official" and "real website" in by["dhl.com"].label
    assert by["dhl-parcel-uk.com"].status == "lookalike" and by["dhl-parcel-uk.com"].label == "Looks like dhl.com but isn't"
    assert any("imitates dhl" in n for n in by["dhl-parcel-uk.com"].notes)
    assert by["kindlyhelper.net"].status == "unverified" and by["kindlyhelper.net"].notes == []
    assert all(isinstance(i, LinkInfo) for i in out)


def test_age_and_dns_notes_and_the_established_status():
    out, *_ = info_for("go to old-shop.com and new-shop.xyz and gone-shop.top",
                       domain_age={"old-shop.com": {"age_days": 4000}, "new-shop.xyz": {"age_days": 3}, "gone-shop.top": {"age_days": None}},
                       dns_check={"old-shop.com": {"status": "ok"}, "gone-shop.top": {"status": "nxdomain"}})
    by = {i.host: i for i in out}
    assert by["old-shop.com"].status == "established" and by["old-shop.com"].age_days == 4000 and "Registered about 10 years ago" in by["old-shop.com"].notes
    assert by["new-shop.xyz"].status == "suspicious" and "Registered 3 days ago" in by["new-shop.xyz"].notes and by["new-shop.xyz"].age_days == 3
    assert by["gone-shop.top"].status == "suspicious" and any("doesn't exist" in n for n in by["gone-shop.top"].notes)


def test_punycode_and_a_raw_ip_are_suspicious_with_plain_notes():
    out, *_ = info_for("open http://xn--pple-43d.com/id and http://203.0.113.9/login")
    by = {i.host: i for i in out}
    assert by["xn--pple-43d.com"].status == "suspicious" and any("punycode" in n for n in by["xn--pple-43d.com"].notes)
    assert by["203.0.113.9"].status == "suspicious" and any("raw IP" in n for n in by["203.0.113.9"].notes)


def test_a_throwaway_ending_is_noted():
    out, *_ = info_for("pay at fastpay-now.top")
    assert out[0].status == "suspicious" and any("ends in .top" in n for n in out[0].notes)


def test_a_short_link_and_where_it_goes():
    ing = ingest("Rebook: bit.ly/3xK9pQ2")
    f = Findings(hosts=list(ing.entities.hosts), shorts={"bit.ly/3xK9pQ2": ""})
    f.apply("domain_check", "bit.ly", domain_check("bit.ly"))
    out = linkinfo.build(ing, f, "en")
    assert out[0].host == "bit.ly" and out[0].status == "shortener" and out[0].expanded_to == "" and "hides where it really goes" in out[0].label
    f.apply("expand_link", "bit.ly/3xK9pQ2", {"url": "bit.ly/3xK9pQ2", "dest": "fastpay-now.top", "status": "expanded"})
    f.apply("domain_check", "fastpay-now.top", domain_check("fastpay-now.top"))
    out = linkinfo.build(ing, f, "en")
    assert [i.host for i in out] == ["bit.ly", "fastpay-now.top"]
    assert out[0].expanded_to == "fastpay-now.top" and out[0].label == "A short link that goes to fastpay-now.top"
    assert out[1].status == "suspicious" and out[1].notes[0] == "This is where the short link really goes"


def test_the_panel_speaks_the_reply_language():
    out, *_ = info_for("see dhl-parcel-uk.com/track", reply="zh")
    assert out[0].label == "看起来像 dhl.com，但不是" and out[0].notes[0].startswith("这个网址")
    out, *_ = info_for("see dhl-parcel-uk.com/track", reply="zh-Hant")
    assert out[0].label == "看起來像 dhl.com，但不是"
    out, *_ = info_for("see mystery-site.net", reply="zh-Hant", domain_age={"mystery-site.net": {"age_days": 12}})
    assert out[0].notes == ["12 天前注冊"]


def test_the_result_of_a_check_carries_the_links_and_no_links_means_an_empty_list():
    r = check_message("DHL: parcel on hold. Pay now at https://dhl-fee-pay.xyz/track", store=False, log=False)
    assert r.verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM) and r.links and r.links[0].host == "dhl-fee-pay.xyz" and r.links[0].status == "lookalike"
    assert check_message("See you at lunch tomorrow", store=False, log=False).links == []
    assert check_message("Pay now at https://fastpay-now.top/track", store=False, log=False, lang="zh").links[0].label == "看起来可疑"


def test_more_links_than_the_panel_shows_are_capped():
    r = check_message("links " + " ".join(f"https://site{i}-pay.xyz/a" for i in range(12)), store=False, log=False)
    assert len(r.links) <= linkinfo.MAX_LINKS


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
