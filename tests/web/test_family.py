"""Family groups through the website: start, invite, share a scam you just checked, see it as a gate, race each other, leave."""
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from core.storage import accounts, groups, runs
from web import deps
from web.main import app

HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
SCAM1 = "DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Call 0800-555-0199 or pay now: dhl-fee-pay.xyz/track/9981"
SCAM2 = "Buy 4 gift cards and send me the numbers please. Do not tell anyone, this is urgent."
SCAM3 = "Your bank account is frozen. Send the OTP code we just texted you to unfreeze it within one hour."


@pytest.fixture(autouse=True)
def public_site(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    deps.HITS.clear()
    deps.LOGIN_HITS.clear()
    accounts._TRIES.clear()


def visitor(lang="en"):
    c = TestClient(app)
    c.cookies.set("lang", lang)
    c.get("/")
    return c


def pid(c):
    return c.cookies.get("bp")


def sign_up(c, name):
    r = c.post("/me/create", data={"nickname": name, "avatar": "🦊"})
    assert r.status_code == 200
    return r


def family_code(c):
    return groups.of(pid(c))["code"]


def start(c, name="The Lims"):
    r = c.post("/family/create", data={"name": name}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/family"


def test_without_a_profile_the_family_page_asks_for_one_and_with_one_offers_start_or_join():
    v = visitor()
    assert "Make a profile first" in v.get("/family").text
    sign_up(v, "Mum")
    html = v.get("/family").text
    assert "Start a family group" in html and "Join with a code" in html and "Only the scam" in unescape(html) and "redacted text" in html


def test_starting_a_group_and_a_bad_name():
    mum = visitor()
    sign_up(mum, "Mum")
    r = mum.post("/family/create", data={"name": "x"})
    assert r.status_code == 400 and "2 to 24" in r.text
    start(mum)
    html = mum.get("/family").text
    assert "👪 The Lims" in html and family_code(mum) in html and "/family/join/" in html and "(started the group)" in html
    assert mum.post("/family/create", data={"name": "Second"}).status_code == 400   # one group each


def test_an_invite_link_makes_a_new_person_a_member_in_one_step_and_shows_their_key_once():
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    start(mum)
    code = family_code(mum)
    landing = kid.get(f"/family/join/{code}").text
    assert "Join The Lims?" in unescape(landing) and "Make my profile and join The Lims" in landing
    r = kid.post(f"/family/join/{code}", data={"nickname": "Aiman", "avatar": "🐼"})
    assert r.status_code == 200 and "the-key" in r.text and "You and The Lims are now friends." in unescape(r.text)
    assert [m["nickname"] for m in groups.of(pid(kid))["members"]] == ["Mum", "Aiman"]
    assert "Aiman" in mum.get("/family").text


def test_a_person_with_a_profile_just_joins_and_a_bad_or_stale_code_is_refused():
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    start(mum)
    code = family_code(mum)
    assert kid.get("/family/join/ZZZZZZ").status_code == 404 and "That invite doesn't work" in unescape(kid.get("/family/join/ZZZZZZ").text)
    assert kid.post(f"/family/join/{code}", follow_redirects=False).headers["location"] == "/family"
    assert kid.get(f"/family/join/{code}", follow_redirects=False).headers["location"] == "/family"   # already in: straight to the group
    mum.post("/family/code")
    other = visitor()
    sign_up(other, "Mei")
    assert other.post(f"/family/join/{code}").status_code == 404   # the old code stopped working


def test_a_scam_you_just_checked_can_be_shared_in_one_tap_and_it_shows_redacted_to_the_family():
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    start(mum)
    kid.post(f"/family/join/{family_code(mum)}")
    result = mum.post("/check", data={"message": SCAM1}).text
    assert "Share with The Lims" in unescape(result) and 'action="/family/share"' in result
    assert "Share with" not in kid.post("/check", data={"message": "Hi, how are you today my friend?"}).text   # a genuine message has nothing to share
    r = mum.post("/family/share", data={"ex": "latest"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/family?shared=1"
    page = kid.get("/family").text
    assert "Scams your family shared" in page and "Shared by Mum" in page and "dhl-fee-pay.xyz" in page
    assert "0800-555-0199" not in page and "/track/9981" not in page and "0800" not in page   # the phone number and the link path are gone
    assert "Shared!" in mum.get("/family?shared=1").text
    assert mum.post("/family/share", data={"ex": "latest"}).status_code == 400     # the same one twice


def test_a_scam_checked_by_someone_without_a_group_offers_no_share_button():
    v = visitor()
    sign_up(v, "Solo")
    assert "Share with" not in v.post("/check", data={"message": SCAM2}).text


def test_the_family_sees_the_shared_scam_as_a_gate_in_their_own_games():
    mum, kid, stranger = visitor(), visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    start(mum)
    kid.post(f"/family/join/{family_code(mum)}")
    for m in (SCAM1, SCAM2, SCAM3):
        mum.post("/check", data={"message": m})
        mum.post("/family/share", data={"ex": "latest"})
    rnd = kid.post("/api/game/start", json={"mode": "yours"}).json()
    assert len(rnd["items"]) == 3 and all(i["yours"] for i in rnd["items"])    # "Your circle": three scams, all from the family
    assert stranger.post("/api/game/start", json={"mode": "yours"}).status_code == 400
    free = kid.post("/api/road/start", json={"mode": "road"}).json()
    daily = kid.post("/api/road/start", json={"mode": "daily"}).json()
    assert all(set(g) == {"id", "text", "yours", "family"} for g in free["items"] + daily["items"])
    assert not [g for g in daily["items"] if g["family"] or g["yours"]]   # (the Daily Road is the same for everyone: no private messages)


def test_the_family_board_ranks_members_only_and_not_other_friends():
    mum, kid, friend = visitor(), visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    sign_up(friend, "Outsider")
    start(mum)
    kid.post(f"/family/join/{family_code(mum)}")
    mum.post("/friends/add", data={"code": accounts.get(pid(friend))["friend_code"]})
    runs.record(pid(kid), runs.ROAD, 560, 7)
    runs.record(pid(mum), runs.ROAD, 240, 3)
    runs.record(pid(friend), runs.ROAD, 9000, 99)
    html = mum.get("/family").text
    board = html[html.index('<ol class="board">'):html.index("</ol>")]
    assert board.index("Aiman") < board.index("Mum") and "560 m" in board and "Outsider" not in board and "9000" not in board
    assert 'href="/family?game=daily"' in html


def test_only_the_owner_removes_members_and_closes_and_anyone_can_leave():
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    start(mum)
    kid.post(f"/family/join/{family_code(mum)}")
    assert "Remove Aiman" in unescape(mum.get("/family").text) and "Remove Aiman" not in unescape(kid.get("/family").text)
    assert "Close the group" not in kid.get("/family").text and "Close the group" in mum.get("/family").text
    pub = groups.of(pid(mum))["members"][1]["pub"]
    assert kid.post("/family/remove", data={"pub": pub}, follow_redirects=False).status_code == 303 and groups.of(pid(kid)) is not None   # not allowed: nothing happens
    assert kid.post("/family/delete", data={"confirm": "yes"}).status_code == 400
    kid.post("/family/leave")
    assert groups.of(pid(kid)) is None and [m["nickname"] for m in groups.of(pid(mum))["members"]] == ["Mum"]
    mum.post("/family/delete", data={})
    assert groups.of(pid(mum)) is not None
    mum.post("/family/delete", data={"confirm": "yes"})
    assert groups.of(pid(mum)) is None


def test_the_family_pages_never_contain_a_profile_id():
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    start(mum)
    kid.post(f"/family/join/{family_code(mum)}")
    mum.post("/check", data={"message": SCAM2})
    mum.post("/family/share", data={"ex": "latest"})
    for c, url in ((mum, "/family"), (kid, "/family"), (kid, f"/family/join/{family_code(mum)}"), (mum, "/friends"), (mum, "/me")):
        assert not [h for h in HEX32.findall(c.get(url).text) if h in (pid(mum), pid(kid))], url


def test_the_family_pages_are_translated():
    for lang, words in (("ms", ("Kumpulan keluarga", "Mulakan kumpulan")), ("zh", ("家庭群组", "建立群组"))):
        v = visitor(lang)
        sign_up(v, "Mum")
        html = v.get("/family").text
        for w in words:
            assert w in html, (lang, w)
        start(v)
        page = v.get("/family").text
        assert ("Jemput keluarga anda" in page) or ("邀请你的家人" in page)
        assert not re.search(r"Invite your family|Who is in|Scams your family shared", re.sub(r"<script.*?</script>", "", page, flags=re.S))


# ---------------------------------------------------------------- the dashboard
def practise(c, tactic, wins):
    from core.storage import db, model

    db.set_profile(pid(c))
    for _ in range(wins):
        model.record_result(tactic, "correct")


def make_family(share_kid=True):
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    start(mum)
    body = {"consent_asked": "1", **({"share": "yes"} if share_kid else {})}
    kid.post(f"/family/join/{family_code(mum)}", data=body)
    return mum, kid


def test_the_start_and_join_forms_ask_about_sharing_and_a_plain_post_defaults_to_sharing():
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    html = mum.get("/family").text
    assert 'name="share"' in html and "Share my practice progress with the family" in html and 'name="consent_asked"' in html and "checked" in html
    start(mum)                                         # (a post with no tick-box field at all: sharing on)
    assert groups.of(pid(mum))["you_share"] is True
    assert "Share my practice progress with the family" in kid.get(f"/family/join/{family_code(mum)}").text
    kid.post(f"/family/join/{family_code(mum)}", data={"consent_asked": "1"})      # ticked nothing: private
    assert groups.of(pid(kid))["you_share"] is False


def test_the_dashboard_shows_the_family_what_they_chose_to_share_and_nothing_more():
    mum, kid = make_family(share_kid=False)
    practise(mum, "urgency-pressure", 3)
    practise(kid, "lookalike-link", 2)
    page = mum.get("/family/dashboard").text
    assert "📊 The Lims" in page and "Who is ready for which trick" in page and 'stat muted">keeps their progress private' in page and "Your progress is visible to your family." in page
    assert page.count('class="lv lv-') >= 12 and 'class="matrix"' in page and "Aiman" in page
    assert "Hide my progress" in page and "Family score, out of 100" in page
    kid_page = kid.get("/family/dashboard").text
    assert "Your progress is private. Your family sees only your name." in kid_page and "Share my progress" in kid_page
    assert kid.post("/family/share-progress", data={"on": "yes"}, follow_redirects=False).headers["location"] == "/family/dashboard"
    assert 'stat muted">keeps their progress private' not in mum.get("/family/dashboard").text
    mum_view = mum.get("/family/dashboard").text
    assert "Aiman" in mum_view and re.search(r"<b>\d+</b>/100", mum_view)
    kid.post("/family/share-progress", data={"on": ""})
    assert 'stat muted">keeps their progress private' in mum.get("/family/dashboard").text


def test_no_dashboard_without_a_group_and_no_profile_id_in_it():
    solo = visitor()
    sign_up(solo, "Solo")
    r = solo.get("/family/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/family"
    mum, kid = make_family()
    practise(mum, "urgency-pressure", 3)
    for c in (mum, kid):
        assert not [h for h in HEX32.findall(c.get("/family/dashboard").text) if h in (pid(mum), pid(kid))]


def test_a_quiet_family_member_can_be_nudged_and_the_answer_says_what_happened(monkeypatch):
    from core.storage import push

    mum, kid = make_family()
    practise(mum, "urgency-pressure", 2)
    page = mum.get("/family/dashboard").text
    assert "👋 Nudge" in page and "hasn't started yet" in unescape(page)
    assert "👋 Nudge" not in kid.get("/family/dashboard").text      # (Mum is active: the kid has nobody to nudge)
    pub = groups.of(pid(mum))["members"][1]["pub"]
    r = mum.post("/family/nudge", data={"pub": pub}, follow_redirects=False)
    assert r.headers["location"] == "/family/dashboard?nudged=nopush"
    assert "haven't turned on notifications" in unescape(mum.get("/family/dashboard?nudged=nopush").text) and "Copy summary" in mum.get("/family/dashboard").text
    sent = []
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    import base64
    v = Vapid()
    v.generate_keys()
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
    monkeypatch.setenv("VAPID_PRIVATE_KEY", b64(v.private_key.private_numbers().private_value.to_bytes(32, "big")))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", b64(v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)))
    monkeypatch.setattr(push, "SYNC", True)
    monkeypatch.setattr(push, "_send", lambda sub, payload: sent.append(payload) or True)
    push._nudged.clear()
    push.subscribe(pid(kid), "https://fcm.googleapis.com/fcm/send/abc", "k" * 40, "a" * 20)
    assert mum.post("/family/nudge", data={"pub": pub}, follow_redirects=False).headers["location"] == "/family/dashboard?nudged=sent" and len(sent) == 1
    assert "Nudge sent" in mum.get("/family/dashboard?nudged=sent").text
    assert mum.post("/family/nudge", data={"pub": pub}, follow_redirects=False).headers["location"] == "/family/dashboard?nudged=limit"
    assert "already nudged them today" in mum.get("/family/dashboard?nudged=limit").text
    assert mum.post("/family/nudge", data={"pub": "nobody"}, follow_redirects=False).headers["location"] == "/family/dashboard?nudged=nopush"
    assert mum.get("/family/dashboard?nudged=<script>").text.count("<script>alert") == 0 and "nudged=" not in mum.get("/family/dashboard?nudged=bogus").text.split("<main")[1][:200]


def test_the_weekly_summary_is_there_to_copy_and_share():
    mum, kid = make_family()
    practise(mum, "urgency-pressure", 3)
    page = unescape(mum.get("/family/dashboard").text)
    assert "👪 The Lims on Baitproof this week" in page and "1 of 2 practised" in page and 'data-copy="👪 The Lims' in page and "https://wa.me/?text=" in page


def test_the_dashboard_is_translated():
    for lang, words in (("ms", ("Papan pemuka keluarga", "Siapa bersedia untuk helah yang mana")), ("zh", ("家庭仪表板", "谁对哪种套路有准备"))):
        mum = visitor(lang)
        sign_up(mum, "Mum")
        start(mum)
        html = mum.get("/family/dashboard").text
        for w in words:
            assert w in html, (lang, w)
        assert not re.search(r"Who is ready|Tricks to practise|keeps their progress private</span>", re.sub(r"<script.*?</script>", "", html, flags=re.S))
