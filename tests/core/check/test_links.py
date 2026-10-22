"""Links written to dodge a filter, spoken links, short-link detection, and the Links panel."""
import pytest

from core.domain.schemas import LinkInfo, Verdict
from core.pipelines.check import check_message
from core.pipelines.check import links as LK
from core.pipelines.check import linkinfo
from core.pipelines.check.ingest import ingest
from core.pipelines.check.tools import Findings, domain_check


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
