"""Family groups: one per person, a dozen people at most, shared scams that are only ever the redacted library text, and ownership that passes on. The family dashboard: only what each person chose to share, soft spots from the sharers, nudges for people who have gone quiet, and a summary for the chat."""
import pytest

from core.domain.tactics import TACTICS
from core.game import pool as gp
from core.storage import accounts, db, groups
from core.storage import dashboard, model, push
from core.storage.groups import GroupError


A, B, C = "a" * 32, "b" * 32, "c" * 32


@pytest.fixture(autouse=True)
def people(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")  # every person has a library of their own
    for pid, name in ((A, "Mum"), (B, "Aiman"), (C, "Mei")):
        accounts.create(pid, name)


def family(owner=A, name="The Lims"):
    return groups.create(owner, name)


def test_a_group_needs_a_profile_and_a_good_name_and_one_per_person():
    with pytest.raises(GroupError, match="Create your profile"):
        groups.create("d" * 32, "Nobody")
    for bad in ("", "x", "y" * 25, "a/b", "http://x.top"):
        with pytest.raises(GroupError, match="2 to 24"):
            groups.create(A, bad)
    g = family()
    assert g["name"] == "The Lims" and g["is_owner"] and len(g["code"]) == 6 and [m["nickname"] for m in g["members"]] == ["Mum"]
    with pytest.raises(GroupError, match="already in a family group"):
        family(A, "Another")


def test_joining_by_code_and_what_an_invite_shows():
    g = family()
    assert groups.by_code(g["code"].lower()) == {"name": "The Lims", "members": 1} and groups.by_code("nope") is None and groups.by_code("ZZZZZZ") is None
    joined = groups.join(B, g["code"])
    assert [m["nickname"] for m in joined["members"]] == ["Mum", "Aiman"] and joined["is_owner"] is False and not joined["members"][1]["owner"] and joined["members"][1]["you"]
    with pytest.raises(GroupError, match="already in a family group"):
        groups.join(B, g["code"])
    with pytest.raises(GroupError, match="doesn't match"):
        groups.join(C, "ZZZZZZ")


def test_a_group_holds_twelve(monkeypatch):
    monkeypatch.setattr(groups, "MAX_MEMBERS", 2)
    g = family()
    groups.join(B, g["code"])
    with pytest.raises(GroupError, match="full"):
        groups.join(C, g["code"])


def test_nothing_a_member_can_see_holds_a_profile_id_or_the_code_of_another_group():
    g = family()
    groups.join(B, g["code"])
    view = repr(groups.of(B)) + repr(groups.by_code(g["code"]))
    assert A not in view and B not in view and C not in view and groups.of(C) is None


def test_leaving_hands_the_group_on_and_the_last_one_out_closes_it():
    g = family()
    groups.join(B, g["code"])
    groups.leave(A)
    assert groups.of(B)["is_owner"] is True and [m["nickname"] for m in groups.of(B)["members"]] == ["Aiman"] and groups.of(A) is None
    groups.leave(B)
    assert groups.of(B) is None and groups.by_code(g["code"]) is None
    groups.leave(C)  # (not in one: nothing to do)


def test_only_the_owner_closes_removes_and_changes_the_code():
    g = family()
    groups.join(B, g["code"])
    pub_b = groups.of(A)["members"][1]["pub"]
    for call in (lambda: groups.delete(B), lambda: groups.remove_member(B, pub_b), lambda: groups.new_code(B)):
        with pytest.raises(GroupError, match="Only the person who started"):
            call()
    assert groups.remove_member(A, groups.of(A)["members"][0]["pub"]) is False  # (the owner cannot remove themselves: they leave or close)
    fresh = groups.new_code(A)
    assert fresh != g["code"] and groups.by_code(g["code"]) is None and groups.by_code(fresh)
    assert groups.remove_member(A, pub_b) and groups.of(B) is None
    groups.delete(A)
    assert groups.of(A) is None


def own_scam(profile, text, tactics=("urgency-pressure",)):
    """A scam this person checked: it is in their own library, redacted."""
    db.set_profile(profile)
    with db.connect() as c:
        c.execute("INSERT INTO library(text,tactics,tell_phrase,tell,action,created) VALUES(?,?,?,?,?,?)",
                  (text, '["' + '","'.join(tactics) + '"]', "pay now", "A deadline and a fee.", "Ignore it.", db.iso(db.now())))


def test_sharing_a_scam_shares_the_redacted_text_and_shows_who_shared_it():
    g = family()
    groups.join(B, g["code"])
    own_scam(A, "Pay the fee now at fee-pay.xyz or lose your parcel")
    item = groups.share(A, "latest")
    assert item["text"].startswith("Pay the fee now")
    view = groups.of(B)
    assert [(s["text"], s["by"], s["mine"]) for s in view["scams"]] == [(item["text"], "Mum", False)] and groups.of(A)["scams"][0]["mine"] is True
    with pytest.raises(GroupError, match="already has"):
        groups.share(A, "latest")


def test_you_can_only_share_what_is_in_your_own_list_and_only_from_a_group():
    own_scam(A, "A scam in the library")
    with pytest.raises(GroupError, match="family group first"):
        groups.share(A, "latest")
    family()
    with pytest.raises(GroupError, match="isn't in your list"):
        groups.share(A, "u9999")
    with db.connect() as c:
        c.execute("UPDATE library SET created=?", ("2020-01-01T00:00:00+00:00",))
    with pytest.raises(GroupError, match="nothing recent"):
        groups.share(A, "latest")


def test_the_one_who_shared_it_and_the_owner_can_take_it_out_and_nobody_else():
    g = family()
    groups.join(B, g["code"])
    groups.join(C, g["code"])
    own_scam(B, "Aiman's scam text here")
    groups.share(B, "latest")
    sid = groups.of(B)["scams"][0]["id"]
    assert groups.unshare(C, sid) is False and groups.of(C)["scams"]
    assert groups.unshare(A, sid) is True and groups.of(C)["scams"] == []
    groups.share(B, "latest")
    assert groups.unshare(B, groups.of(B)["scams"][0]["id"]) is True


def test_the_bank_keeps_the_newest_sixty(monkeypatch):
    monkeypatch.setattr(groups, "MAX_SCAMS", 3)
    family()
    for i in range(5):
        own_scam(A, f"Scam number {i} with a fee")
        groups.share(A, "latest")
    assert [s["text"] for s in groups.of(A)["scams"]] == ["Scam number 4 with a fee", "Scam number 3 with a fee", "Scam number 2 with a fee"]


def test_leaving_takes_you_out_of_the_shared_scams_but_the_group_keeps_what_you_shared():
    g = family()
    groups.join(B, g["code"])
    own_scam(B, "Aiman's scam text here")
    groups.share(B, "latest")
    groups.leave(B)
    assert [s["text"] for s in groups.of(A)["scams"]] == ["Aiman's scam text here"] and groups.scams_for(B) == []


def test_the_pool_marks_family_scams_for_everyone_in_the_group_and_only_them():
    g = family()
    groups.join(B, g["code"])
    own_scam(A, "A scam that reached Mum's phone with a fee")
    groups.share(A, "latest")
    db.set_profile(B)
    fam = [i for i in gp.build_pool("en") if i.source == "family"]
    assert len(fam) == 1 and fam[0].truth == "scam" and fam[0].tactics == ["urgency-pressure"] and not [i for i in gp.build_pool("en") if i.source == "yours"]
    db.set_profile(C)
    assert not [i for i in gp.build_pool("en") if i.source in ("family", "yours")]
    db.set_profile(A)   # the one who shared it has it as their own scam, once
    assert [i.source for i in gp.build_pool("en") if i.text.startswith("A scam that reached")] == ["yours"]


EP = "https://fcm.googleapis.com/fcm/send/abc123"
KEY, AUTH = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "tBHItJI5svbpez7KI4CCXg"


def practise(profile, tactic, wins):
    db.set_profile(profile)
    for _ in range(wins):
        model.record_result(tactic, "correct")


def family_of_three(share_b=True, share_c=True):
    g = groups.create(A, "The Lims")
    groups.join(B, g["code"], share_b)
    groups.join(C, g["code"], share_c)
    return g


def test_a_persons_progress_is_read_from_their_own_database():
    practise(A, "urgency-pressure", 3)
    practise(B, "lookalike-link", 1)
    a, b = dashboard.member_stats(A), dashboard.member_stats(B)
    assert a["levels"]["urgency-pressure"] == "strong" and a["levels"]["lookalike-link"] == "untested" and a["score"] > b["score"] > 0
    assert a["drills_week"] == 3 and b["drills_week"] == 1 and a["days_since"] == 0 and a["last_active"]
    assert dashboard.member_stats(C)["days_since"] is None and dashboard.member_stats(C)["score"] == 0
    db.set_profile(C)   # (nothing leaked from one person's database into another's)
    assert dashboard.member_stats(C)["levels"]["urgency-pressure"] == "untested"


def test_those_who_do_not_share_appear_as_a_name_and_nothing_else():
    family_of_three(share_b=False)
    practise(A, "urgency-pressure", 3)
    practise(B, "lookalike-link", 2)
    practise(C, "lookalike-link", 2)
    fam = dashboard.family(A, "en")
    by = {m["nickname"]: m for m in fam["members"]}
    assert by["Aiman"]["stats"] is None and by["Aiman"]["shares"] is False and not by["Aiman"]["needs_nudge"]
    assert by["Mum"]["stats"] and by["Mei"]["stats"]
    link = next(t for t in fam["tactics"] if t["id"] == "lookalike-link")
    assert link["cells"] == ["untested", None, "strong"]      # Aiman's cell is empty: he keeps it private
    assert fam["summary"]["sharing"] == 2 and fam["summary"]["members"] == 3


def test_you_always_see_your_own_progress_even_when_you_keep_it_private_from_the_family():
    family_of_three(share_b=False)
    practise(B, "urgency-pressure", 3)
    mine = {m["nickname"]: m for m in dashboard.family(B, "en")["members"]}["Aiman"]
    assert mine["stats"]["levels"]["urgency-pressure"] == "strong" and mine["shares"] is False
    assert {m["nickname"]: m for m in dashboard.family(A, "en")["members"]}["Aiman"]["stats"] is None
    groups.set_share(B, True)
    assert {m["nickname"]: m for m in dashboard.family(A, "en")["members"]}["Aiman"]["stats"]["score"] > 0


def test_soft_spots_come_from_the_people_who_share_and_only_when_they_really_are_weak():
    family_of_three(share_c=False)
    for t in list(TACTICS)[:10]:
        practise(A, t, 3)
        practise(B, t, 3)
    fam = dashboard.family(A, "en")
    assert [s["id"] for s in fam["soft"]] == list(TACTICS)[10:12]
    assert all(t["soft"] == (t["id"] in {s["id"] for s in fam["soft"]}) for t in fam["tactics"])
    assert all(t["avg"] == 100 for t in fam["tactics"][:10]) and all(t["avg"] == 0 for t in fam["tactics"][10:])
    for t in TACTICS:   # when everyone is strong at everything there is nothing to flag
        practise(A, t, 3)
        practise(B, t, 3)
    assert dashboard.family(A, "en")["soft"] == []


def test_somebody_who_has_gone_quiet_can_be_nudged_but_not_you_and_not_a_private_person():
    family_of_three(share_c=False)
    practise(A, "urgency-pressure", 3)
    fam = {m["nickname"]: m for m in dashboard.family(A, "en")["members"]}
    assert fam["Aiman"]["needs_nudge"] is True          # (never started)
    assert fam["Mum"]["needs_nudge"] is False            # (you)
    assert fam["Mei"]["needs_nudge"] is False            # (private)
    practise(B, "urgency-pressure", 1)
    assert not {m["nickname"]: m for m in dashboard.family(A, "en")["members"]}["Aiman"]["needs_nudge"]
    with db.connect() as c:
        c.execute("UPDATE history SET ts=?", ("2020-01-01T00:00:00+00:00",))   # (Aiman's database: his last practice was years ago)
    assert {m["nickname"]: m for m in dashboard.family(A, "en")["members"]}["Aiman"]["needs_nudge"] is True


def test_the_summary_numbers():
    family_of_three()
    practise(A, "urgency-pressure", 2)
    practise(B, "lookalike-link", 1)
    s = dashboard.family(A, "en")["summary"]
    assert s["members"] == 3 and s["sharing"] == 3 and s["practised_week"] == 2 and s["drills_week"] == 3 and s["shared_week"] == 0
    assert 0 < s["avg_score"] < 20


def test_nothing_in_the_dashboard_holds_a_profile_id():
    family_of_three()
    practise(A, "urgency-pressure", 3)
    assert not [x for x in (A, B, C) if x in repr(dashboard.family(A, "en")) + dashboard.summary_text(dashboard.family(A, "en"))]


def test_a_person_in_no_group_has_no_dashboard():
    assert dashboard.family(A, "en") is None


def test_the_weekly_summary_reads_in_each_language():
    family_of_three()
    practise(A, "urgency-pressure", 3)
    en = dashboard.summary_text(dashboard.family(A, "en"), "en")
    assert en.startswith("👪 The Lims on Baitproof this week") and "1 of 3 practised" in en and "Tricks to practise next:" in en and en.endswith("🐟")
    assert "1 daripada 3 berlatih" in dashboard.summary_text(dashboard.family(A, "ms"), "ms") and "3 人中有 1 人练习过" in dashboard.summary_text(dashboard.family(A, "zh"), "zh")
    assert "scams shared" not in en       # (nothing shared this week: the line is left out)


def test_group_defaults_and_choices_about_sharing():
    g = groups.create(A, "The Lims")
    assert groups.of(A)["you_share"] is True
    groups.join(B, g["code"], share=False)
    assert groups.of(B)["you_share"] is False and [m["shares"] for m in groups.of(A)["members"]] == [True, False]
    groups.set_share(B, True)
    assert groups.of(B)["you_share"] is True


# ---------------------------------------------------------------- nudges
@pytest.fixture
def pushing(monkeypatch):
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    import base64

    v = Vapid()
    v.generate_keys()
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
    monkeypatch.setenv("VAPID_PRIVATE_KEY", b64(v.private_key.private_numbers().private_value.to_bytes(32, "big")))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", b64(v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)))
    monkeypatch.setattr(push, "SYNC", True)
    push._nudged.clear()
    sent = []
    monkeypatch.setattr(push, "_send", lambda sub, payload: sent.append((sub, payload)) or True)
    return sent


def test_a_nudge_reaches_the_persons_devices_in_their_language_once_a_day(pushing):
    family_of_three()
    push.subscribe(B, EP, KEY, AUTH, "ms")
    assert push.notify_nudge(A, B) == "sent"
    (sub, payload), = pushing
    assert payload["title"] == "🐟 Mum memikirkan anda" and payload["url"] == "/train" and "Seminit latihan" in payload["body"] and A not in str(payload) and B not in str(payload)
    assert push.notify_nudge(A, B) == "limit" and len(pushing) == 1
    assert push.notify_nudge(C, B) == "sent"     # (a different family member may)


def test_no_devices_or_no_push_means_nothing_is_sent_and_it_says_so(pushing, monkeypatch):
    family_of_three()
    assert push.notify_nudge(A, C) == "nopush" and pushing == []
    push.subscribe(B, EP, KEY, AUTH)
    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    assert push.notify_nudge(A, B) == "nopush"
