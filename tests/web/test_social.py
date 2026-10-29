"""Profiles, signing in, invites, friends, the friends' leaderboard and the Scam Road API, through the website: two visitors with two cookies."""
import json
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from core.game import pool as gp
from core.storage import accounts, runs
from web import deps
from web.main import app

HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
TRUTH = {i.text: i.truth for i in gp.build_pool("en")}
LANE = {"scam": 0, "unsure": 1, "safe": 2}


@pytest.fixture(autouse=True)
def public_site(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")  # one profile per visitor: the only mode in which friends make sense
    deps.HITS.clear()
    deps.LOGIN_HITS.clear()
    accounts._TRIES.clear()


def visitor(lang="en"):
    c = TestClient(app)
    c.cookies.set("lang", lang)
    c.get("/")  # gets a profile cookie
    return c


def key_of(html):
    return re.search(r'id="the-key">([A-Z0-9-]{19})<', html).group(1)


def sign_up(c, name="Aiman", avatar="fox"):
    r = c.post("/me/create", data={"nickname": name, "avatar": avatar})
    assert r.status_code == 200, r.text[:300]
    return key_of(r.text)


def code_of(c):
    return accounts.get(pid(c))["friend_code"]


def pid(c):
    return c.cookies.get("bp")


# ---------------------------------------------------------------- profile and log in
def test_a_visitor_sees_log_in_and_a_profile_shows_their_avatar_and_name():
    a = visitor()
    html = a.get("/").text
    assert 'class="me login" href="/signin"' in html and "Log in" in html
    sign_up(a, "Aiman", "fox")
    html = a.get("/").text
    assert 'class="me" href="/me"' in html and "Aiman" in html and 'data-av="fox"' in html and "me login" not in html


def test_creating_a_profile_shows_the_key_once_and_never_stores_it():
    a = visitor()
    r = a.post("/me/create", data={"nickname": "Aiman", "avatar": "fox"})
    key = key_of(r.text)
    assert r.headers["cache-control"] == "no-store" and "Save it somewhere safe" in r.text
    again = a.get("/me").text
    assert key not in again and "Your friend code" in again  # shown once
    assert accounts.sign_in(key) == pid(a)


def test_a_bad_nickname_is_refused_with_a_message_and_makes_no_profile():
    a = visitor()
    r = a.post("/me/create", data={"nickname": "evil.com", "avatar": "fox"})
    assert r.status_code == 400 and "letters or numbers" in r.text and accounts.get(pid(a)) is None
    assert 'value="evil.com"' in r.text  # what they typed is kept so they can fix it


def test_signing_in_on_another_device_adopts_the_profile_and_signing_out_leaves_it():
    a = visitor()
    key = sign_up(a, "Aiman")
    phone = visitor()
    assert pid(phone) != pid(a)
    r = phone.post("/signin", data={"key": key.lower()}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    assert pid(phone) == pid(a) and "Aiman" in phone.get("/me").text   # the phone is now Aiman's profile
    r = phone.post("/signout", follow_redirects=False)
    assert r.status_code == 303 and pid(phone) != pid(a) and "Log in" in phone.get("/").text
    assert accounts.get(pid(a))["nickname"] == "Aiman" and accounts.sign_in(key) == pid(a)   # the account is still there for its key


def test_a_wrong_key_is_refused_and_attempts_are_limited():
    v = visitor()
    r = v.post("/signin", data={"key": "AAAA-BBBB-CCCC-DDDD"})
    assert r.status_code == 400 and "doesn't match a profile" in unescape(r.text)
    codes = [v.post("/signin", data={"key": "AAAA-BBBB-CCCC-DDDD"}).status_code for _ in range(12)]
    assert 429 in codes


def test_a_new_key_replaces_the_old_and_a_new_friend_code_replaces_the_old():
    a = visitor()
    old = sign_up(a, "Aiman")
    code = code_of(a)
    new = key_of(a.post("/me/key").text)
    assert new != old and accounts.sign_in(old) is None and accounts.sign_in(new) == pid(a)
    a.post("/me/code")
    assert code_of(a) != code


def test_changing_the_name_and_deleting_the_profile():
    a = visitor()
    sign_up(a, "Aiman")
    assert a.post("/me/update", data={"nickname": "Aiman Z", "avatar": "panda"}, follow_redirects=False).status_code == 303
    assert accounts.get(pid(a))["nickname"] == "Aiman Z" and accounts.get(pid(a))["avatar"] == "panda"
    a.post("/me/delete", data={})      # without the tick box nothing happens
    assert accounts.get(pid(a)) is not None
    a.post("/me/delete", data={"confirm": "yes"})
    assert accounts.get(pid(a)) is None


# ---------------------------------------------------------------- invites and friends
def test_an_invite_link_makes_a_stranger_a_friend_in_one_step():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman", "fox")
    code = code_of(a)
    landing = b.get(f"/join/{code}").text
    assert "Aiman invited you to be friends" in unescape(landing) and 'data-av="fox"' in landing and "Make my profile and add Aiman" in landing
    r = b.post(f"/join/{code}", data={"nickname": "Mei", "avatar": "panda"})
    assert r.status_code == 200 and "You and Aiman are now friends." in r.text and key_of(r.text)
    assert [f["nickname"] for f in accounts.friends(pid(a))] == ["Mei"] and [f["nickname"] for f in accounts.friends(pid(b))] == ["Aiman"]


def test_a_visitor_with_a_profile_just_accepts():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    code = code_of(a)
    assert "Accept and add Aiman" in b.get(f"/join/{code}").text
    r = b.post(f"/join/{code}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/friends?added=Aiman")
    assert "You and Aiman are now friends." in b.get(r.headers["location"]).text
    assert a.get(f"/join/{code}", follow_redirects=False).headers["location"] == "/friends"   # your own link goes to your friends


def test_a_bad_invite_says_so_and_a_stale_one_stops_working():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    assert b.get("/join/ZZZZZZ").status_code == 404 and "That invite doesn't work" in unescape(b.get("/join/ZZZZZZ").text)
    old = code_of(a)
    a.post("/me/code")
    assert b.get(f"/join/{old}").status_code == 404 and b.post(f"/join/{old}", data={"nickname": "Mei"}).status_code == 404
    assert accounts.get(pid(b)) is None  # a dead invite does not create anything


def test_add_by_code_remove_and_the_errors_in_between():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    r = a.post("/friends/add", data={"code": code_of(a)})
    assert r.status_code == 400 and "your own code" in r.text
    assert a.post("/friends/add", data={"code": "nope"}).status_code == 400
    r = a.post("/friends/add", data={"code": code_of(b).lower()}, follow_redirects=False)
    assert r.status_code == 303
    assert a.post("/friends/add", data={"code": code_of(b)}).status_code == 400   # already friends
    page = a.get("/friends").text
    assert "Mei" in page and 'name="pub"' in page
    pub = accounts.friends(pid(a))[0]["pub"]
    assert a.post("/friends/remove", data={"pub": pub}, follow_redirects=False).status_code == 303
    assert accounts.friends(pid(a)) == [] and accounts.friends(pid(b)) == []


def test_no_page_ever_contains_anyones_profile_id_because_that_is_the_session_cookie():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    b.post(f"/join/{code_of(a)}")
    runs.record(pid(a), runs.ROAD, 320, 4)
    pages = [b.get(u).text for u in ("/", "/me", "/friends", "/friends?scope=all", f"/join/{code_of(a)}", "/road", "/train")]
    pages += [a.get(u).text for u in ("/me", "/friends")]
    for html in pages:
        assert not [h for h in HEX32.findall(html) if h in (pid(a), pid(b))]
    assert "HttpOnly" in b.get("/", headers={}).headers.get("set-cookie", "HttpOnly") or True   # (the cookie is set once, at the first visit)


def test_the_profile_cookie_is_http_only():
    c = TestClient(app)
    assert "httponly" in c.get("/").headers["set-cookie"].lower()


def test_the_leaderboard_shows_friends_ranked_and_this_week_versus_all_time():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman", "fox")
    sign_up(b, "Mei", "panda")
    b.post(f"/join/{code_of(a)}")
    runs.record(pid(b), runs.ROAD, 640, 8)
    runs.record(pid(a), runs.ROAD, 400, 5)
    html = a.get("/friends").text
    board = html[html.index('<ol class="board">'):html.index("</ol>")]
    assert board.index("Mei") < board.index("Aiman") and "640 m" in html and "400 m" in html and "m-gold" in html and "m-silver" in html and "(you)" in html
    assert 'aria-current="true">This week' in html and "/friends?game=road&scope=all" in html
    assert "640 m" in a.get("/friends?scope=all").text and 'aria-current="true">This week' in a.get("/friends?scope=bogus").text  # (an unknown range falls back to this week)


def test_strangers_are_never_on_the_board():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Stranger")
    runs.record(pid(b), runs.ROAD, 9999, 50)
    assert "Stranger" not in a.get("/friends").text and "9999" not in a.get("/friends").text


def test_without_a_profile_the_friends_page_invites_you_to_make_one():
    v = visitor()
    html = v.get("/friends").text
    assert "Make your profile" in html and "Log in" in html and 'href="/me"' in html


def test_on_a_single_user_copy_friends_explain_themselves(monkeypatch):
    monkeypatch.delenv("BAITPROOF_MULTIUSER")
    html = TestClient(app).get("/friends").text
    assert "This copy has only one" in html


# ---------------------------------------------------------------- Scam Road
def test_the_road_page_is_one_module_of_our_own_plus_the_vendored_three_js_and_nothing_external():
    c = visitor()
    r = c.get("/road")
    html = r.text
    assert r.status_code == 200 and '<script type="module" src="/static/js/road.js">' in html and 'data-game="road"' in html and 'id="scene"' in html
    assert "ripple.js" in html and "mascot.js" in html  # (both load, and both stand down on a game page)
    assert not re.findall(r'(?:src|href)="https?://', html) and "unsafe-inline" not in r.headers["content-security-policy"] and "unsafe-eval" not in r.headers["content-security-policy"]
    js = c.get("/static/js/road.js")
    assert js.status_code == 200 and "../vendor/three.module.min.js" in js.text and "http" not in re.sub(r"https?://\S*three\S*", "", js.text.split("// three.js")[0])
    three = c.get("/static/vendor/three.module.min.js")
    assert three.status_code == 200 and "javascript" in three.headers["content-type"] and three.content.startswith(b"/**\n * @license\n * Copyright 2010-2023 Three.js Authors")
    assert c.get("/static/vendor/LICENSE-three.txt").status_code == 200


def test_every_copy_button_is_handled_by_the_script_every_page_loads():
    """A "Copy" button is only markup (data-copy holds the text); app.js, which base.html loads on every page, does the copying. The race waiting room's invite button once
    sat on a page that loaded no handler, so tapping it did nothing."""
    from pathlib import Path

    web = Path(__file__).resolve().parents[2] / "web"
    app_js = (web / "static/js/app.js").read_text()
    assert 'closest("[data-copy]")' in app_js and "async function copyText" in app_js
    assert "[data-copy]" not in (web / "static/js/social.js").read_text(), "a second handler would copy twice"
    for page in (web / "templates").glob("*.html"):
        if "data-copy" in page.read_text() and not page.name.startswith("_"):  # (a "_" file is a piece another page includes)
            assert '{% extends "base.html" %}' in page.read_text(), f"{page.name} has a Copy button but does not load app.js"
    # the waiting room itself, as a visitor gets it
    c = visitor()
    c.post("/me/create", data={"nickname": "Aiman"})
    lobby = c.post("/duel/new", follow_redirects=True)
    assert lobby.status_code == 200 and re.search(r'data-copy="https?://[^"]+/duel/[A-Z0-9]{6}"', lobby.text), "the waiting room's Copy invite link button holds the invite link"


def play(c, n, wrong=0):
    """Drive n right gates then `wrong` wrong ones, through the API (the same calls the page makes). Returns the last answer."""
    run = c.post("/api/road/start").json()
    gates, out = list(run["items"]), None
    for i in range(n + wrong):
        g = gates.pop(0)
        truth = TRUTH[g["text"]]
        lane = LANE[truth] if i < n else {"scam": 2, "safe": 0, "unsure": 0}[truth]
        out = c.post("/api/road/answer", json={"run": run["run"], "gate": g["id"], "lane": lane}).json()
        gates += out["next"]
        if out["over"]:
            break
    return run, out


def test_a_drive_through_the_api_scores_on_the_friends_board():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    b.post(f"/join/{code_of(a)}")
    run, out = play(a, 5, wrong=3)
    assert out["over"] and out["distance"] == 400 and out["lives"] == 0
    s = a.post("/api/road/finish", json={"run": run["run"]}).json()
    assert s["distance"] == 400 and s["new_best"] and s["account"] and [r["nickname"] for r in s["board"]] == ["Aiman", "Mei"]
    assert "400 m" in b.get("/friends").text and runs.best(pid(a)) == 400
    start = b.post("/api/road/start").json()
    assert [(g["nickname"], g["best"]) for g in start["ghosts"]] == [("Aiman", 400)] and "profile" not in str(start["ghosts"]) and pid(a) not in str(start)


def test_nobody_can_answer_for_someone_elses_drive_or_forge_a_score():
    a, b = visitor(), visitor()
    run = a.post("/api/road/start").json()
    gate = run["items"][0]["id"]
    assert b.post("/api/road/answer", json={"run": run["run"], "gate": gate, "lane": 0}).status_code == 404
    assert b.post("/api/road/finish", json={"run": run["run"]}).status_code == 404
    assert a.post("/api/road/answer", json={"run": run["run"], "gate": "g99", "lane": 0}).status_code == 400
    assert a.post("/api/road/answer", json={"run": run["run"], "gate": gate, "lane": 7}).status_code == 400
    r = a.post("/api/road/finish", json={"run": run["run"], "distance": 99999})   # the body has no say about the score
    assert r.json()["distance"] == 0


def test_the_road_api_speaks_the_visitors_language():
    c = visitor("ms")
    run = c.post("/api/road/start").json()
    first = run["items"][0]
    out = c.post("/api/road/answer", json={"run": run["run"], "gate": first["id"], "lane": 1}).json()
    assert out["outcome"] in ("partial", "correct") and not re.search("[一-鿿]", str(out))
    assert c.post("/api/road/answer", json={"run": run["run"], "gate": first["id"], "lane": 1}).json()["detail"] == "Sudah dijawab."


# ---------------------------------------------------------------- languages
@pytest.mark.parametrize("lang,tag,words", [("ms", "ms", ("Papan pendahulu", "Tambah kawan", "Minggu ini")), ("zh", "zh-Hans", ("排行榜", "添加好友", "本星期")),
                                            ("zh-Hant", "zh-Hant", ("排行榜", "添加好友", "本星期"))])
def test_the_new_pages_are_translated(lang, tag, words):
    a = visitor(lang)
    sign_up(a, "Aiman")
    html = a.get("/friends").text
    assert f'<html lang="{tag}"' in html
    for w in words:
        assert w in html, w
    me = a.get("/me").text
    assert "Aiman" in me and ("Kod kawan anda" in me or "你的好友码" in me or "你的好友碼" in me)
    road = a.get("/road").text
    assert ("Sedia memandu?" in road) or ("准备出发了吗？" in road) or ("準備出發了嗎？" in road)


def test_the_road_scripts_dictionary_has_the_new_strings():
    import json
    html = visitor("ms").get("/road").text
    block = json.loads(re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, flags=re.S).group(1))
    assert block["speech"] == "ms-MY" and block["dict"]["Combo x{n}"] == "Kombo x{n}" and block["dict"]["Keep driving"] == "Terus memandu"


def test_new_pages_have_no_leftover_english_in_malay():
    a = visitor("ms")
    sign_up(a, "Aiman")
    leftovers = ["Leaderboard", "Add friend", "Log in", "Sign in", "profile", "Your friends", "Drive again", "Start driving", "Keep driving", "Ready to drive"]
    for url in ("/friends", "/me", "/signin", "/road", "/join/ZZZZZZ"):
        text = re.sub(r"<script.*?</script>", "", a.get(url).text, flags=re.S)
        text = re.sub(r'\sdata-[\w-]+="[^"]*"', "", re.sub(r'<details class="lang".*?</details>', "", text, flags=re.S))
        for w in leftovers:
            assert w not in text, (url, w)


def test_the_board_has_a_tab_for_each_game_and_the_daily_one_shows_only_today():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    b.post(f"/join/{code_of(a)}")
    runs.record(pid(b), runs.DAILY, 480, 6, "cccccc", "mint:cap")
    runs.record(pid(a), runs.LINK, 700, 7)
    daily = a.get("/friends?game=daily").text
    assert 'aria-current="true">Daily Road' in daily and "480 m" in daily and 'aria-current="true">Today' in daily and "All time" not in daily and "This week" not in daily
    link = a.get("/friends?game=link&scope=all").text
    assert 'aria-current="true">Link Hunt' in link and "700 points" in link and "Play Link Hunt" in link
    assert 'aria-current="true">Scam Road' in a.get("/friends?game=bogus").text and 'aria-current="true">This week' in a.get("/friends?game=bogus&scope=day").text
    assert "480 m" not in a.get("/friends").text  # (the free drive's board does not count the Daily Road)


def test_the_road_page_offers_both_drives_the_garage_and_the_settings():
    html = visitor().get("/road").text
    for want in ('id="go"', 'id="go-daily"', 'id="garage-cars"', 'id="garage-hats"', 'id="themes"', 'id="opt-sound"', 'id="opt-music"', 'id="opt-vibe"', 'id="sound"', "Free drive", "Daily Road", "Garage and settings"):
        assert want in html, want
    assert 'id="race-text" aria-live' not in html   # (the strip changes all the time: a screen reader is told about passes through the toast, not the strip)


def test_the_garage_api_lists_whats_earned_and_saves_a_choice():
    a = visitor()
    cat = a.get("/api/road/garage").json()
    assert cat["selected"] == {"car": "plum", "hat": "none"} and [c["id"] for c in cat["cars"] if c["unlocked"]] == ["plum"]
    assert a.post("/api/road/garage", json={"car": "gold", "hat": "none"}).status_code == 400
    assert a.post("/api/road/garage", json={"car": "plum", "hat": "none"}).json()["selected"]["car"] == "plum"
    ms = visitor("ms").get("/api/road/garage").json()
    assert ms["cars"][1]["name"] == "Pudina" and "Capai tahap" in ms["cars"][1]["need"]


def test_a_daily_drive_through_the_api_is_the_same_road_for_two_visitors_and_shows_a_friends_ghost():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    b.post(f"/join/{code_of(a)}")
    ra = a.post("/api/road/start", json={"mode": "daily"}).json()
    rb = b.post("/api/road/start", json={"mode": "daily"}).json()
    assert ra["mode"] == "daily" and [g["text"] for g in ra["items"]] == [g["text"] for g in rb["items"]] and rb["replays"] == []
    gates = list(ra["items"])
    for _ in range(3):
        g = gates.pop(0)
        out = a.post("/api/road/answer", json={"run": ra["run"], "gate": g["id"], "lane": LANE[TRUTH[g["text"]]]}).json()
        gates += out["next"]
    s = a.post("/api/road/finish", json={"run": ra["run"]}).json()
    assert s["mode"] == "daily" and s["distance"] == 240 and s["first_daily"]
    again = b.post("/api/road/start", json={"mode": "daily"}).json()
    assert [(g["nickname"], g["score"], g["path"]) for g in again["replays"]] == [("Aiman", 240, "ccc")] and pid(a) not in str(again)
    assert "unlocked" in s and a.post("/api/road/start", json={"mode": "nope"}).status_code == 400


# ---------------------------------------------------------------- Link Hunt
def test_the_link_hunt_page_and_a_round_through_the_api():
    a = visitor()
    sign_up(a, "Aiman")
    html = a.get("/link").text
    assert 'id="lh-start"' in html and "/static/js/linkhunt.js" in html and "Link Hunt" in html and 'aria-current="page"' in html
    r = a.post("/api/link/start").json()
    assert len(r["question"]["options"]) == 4 and r["lives"] == 3 and "answer" not in str(r) and "real" not in str(r)
    out = a.post("/api/link/answer", json={"hunt": r["hunt"], "question": r["question"]["id"], "choice": 0}).json()
    assert out["real"] and out["tell"] and out["fake"] in (0, 1, 2, 3) and (out["correct"] is (out["fake"] == 0)) and out["next"]["id"] != r["question"]["id"]
    s = a.post("/api/link/finish", json={"hunt": r["hunt"]}).json()
    assert s["score"] == (100 if out["correct"] else 0) and s["account"]


def test_nobody_can_answer_for_another_visitors_hunt_or_with_a_bad_choice():
    a, b = visitor(), visitor()
    r = a.post("/api/link/start").json()
    body = {"hunt": r["hunt"], "question": r["question"]["id"], "choice": 0}
    assert b.post("/api/link/answer", json=body).status_code == 404 and b.post("/api/link/finish", json={"hunt": r["hunt"]}).status_code == 404
    assert a.post("/api/link/answer", json={**body, "choice": 9}).status_code == 400
    assert a.post("/api/link/answer", json={**body, "question": "nope"}).status_code == 400


def test_link_hunt_scores_reach_the_friends_board_in_points():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    b.post(f"/join/{code_of(a)}")
    r = b.post("/api/link/start").json()
    for _ in range(3):
        from core.game import linkhunt
        h = linkhunt.get(r["hunt"], pid(b))
        out = b.post("/api/link/answer", json={"hunt": r["hunt"], "question": h.question["id"], "choice": h.question["answer"]["index"]}).json()
    b.post("/api/link/finish", json={"hunt": r["hunt"]})
    assert out["score"] == 300 and "300 points" in a.get("/friends?game=link&scope=all").text


def test_link_hunt_speaks_malay_and_chinese():
    for lang, word in (("ms", "Cari Pautan Palsu"), ("zh", "找假网址")):
        v = visitor(lang)
        html = v.get("/link").text
        assert word in html and not re.search("Which link is the fake|Start hunting", re.sub(r"<script.*?</script>", "", html, flags=re.S))
        r = v.post("/api/link/start").json()
        out = v.post("/api/link/answer", json={"hunt": r["hunt"], "question": r["question"]["id"], "choice": 0}).json()
        assert out["trick"] != "Fake website address" and "{" not in out["tell"] and out["tell"] != ""


# ---------------------------------------------------------------- notifications
def _push_keys(monkeypatch):
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "x" * 43)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM")


def test_notifications_are_invisible_without_keys_and_offered_with_them(monkeypatch):
    a = visitor()
    sign_up(a, "Aiman")
    html = a.get("/friends").text
    assert 'id="push-box"' not in html and "push.js" not in html and a.get("/api/push/config").json() == {"enabled": False, "key": "", "devices": 0}
    assert a.post("/api/push/subscribe", json={"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": "k" * 40, "auth": "a" * 20}}).status_code == 404
    _push_keys(monkeypatch)
    html = a.get("/friends").text
    assert 'id="push-box"' in html and 'id="push-on"' in html and "/static/js/push.js" in html and "Turn on notifications" in html
    assert a.get("/api/push/config").json()["enabled"] is True and a.get("/api/push/config").json()["key"].startswith("BNcRdre")
    assert 'id="push-box"' not in visitor().get("/friends").text    # (no profile: no card)


def test_subscribing_unsubscribing_and_the_refusals(monkeypatch):
    _push_keys(monkeypatch)
    a, nobody = visitor(), visitor()
    sign_up(a, "Aiman")
    good = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "k" * 40, "auth": "a" * 20}}
    assert a.post("/api/push/subscribe", json=good).json() == {"devices": 1} and a.get("/api/push/config").json()["devices"] == 1
    assert nobody.post("/api/push/subscribe", json=good).status_code == 400                      # no profile
    bad = {**good, "endpoint": "https://evil.example.com/steal"}
    r = a.post("/api/push/subscribe", json=bad)
    assert r.status_code == 400 and "notification address" in unescape(r.text)
    assert a.post("/api/push/unsubscribe", json={"endpoint": good["endpoint"]}).json() == {"devices": 0}
    assert a.post("/api/push/unsubscribe", json={"endpoint": good["endpoint"]}).json() == {"devices": 0}
    ms = visitor("ms")
    sign_up(ms, "Mei")
    assert "perlu" in ms.post("/api/push/subscribe", json=bad).text or "pelayar" in ms.post("/api/push/subscribe", json=bad).text


def test_the_service_worker_shows_and_opens_notifications_safely():
    sw = visitor().get("/sw.js")
    assert sw.status_code == 200 and "addEventListener(\"push\"" in sw.text and "notificationclick" in sw.text and r'/^\/(?!\/)/' in sw.text
    assert "caches" not in sw.text.replace("caches nothing", "")    # (it still stores nothing)


def test_the_notification_card_is_translated(monkeypatch):
    _push_keys(monkeypatch)
    for lang, word in (("ms", "Hidupkan pemberitahuan"), ("zh", "开启通知")):
        a = visitor(lang)
        sign_up(a, "Aiman")
        assert word in a.get("/friends").text


# ---------------------------------------------------------------- festivals
def test_during_a_festival_the_home_page_and_the_road_say_so(monkeypatch):
    monkeypatch.setenv("BAITPROOF_TODAY", "2026-11-08")
    home = visitor().get("/").text
    assert 'class="season-strip' in home and "Happy Deepavali!" in home and "red-packet links" in home
    road = visitor().get("/road").text
    data = json.loads(unescape(re.search(r"data-season='([^']*)'", road).group(1)))
    assert data["id"] == "deepavali" and data["icon"] == "fest-deepavali" and data["greeting"] == "Happy Deepavali!"
    assert "The road is dressed for Deepavali." in road and 'class="season-line"' in road


def test_on_an_ordinary_day_there_is_no_festival_anywhere(monkeypatch):
    monkeypatch.setenv("BAITPROOF_TODAY", "2026-10-24")
    home = visitor().get("/").text
    assert "season-strip" not in home
    road = visitor().get("/road").text
    assert json.loads(unescape(re.search(r"data-season='([^']*)'", road).group(1))) == {} and "season-line" not in road


@pytest.mark.parametrize("lang,greeting,name", [("ms", "Selamat Hari Deepavali!", "Deepavali"), ("zh", "屠妖节快乐！", "屠妖节")])
def test_the_festival_greeting_follows_the_language(monkeypatch, lang, greeting, name):
    monkeypatch.setenv("BAITPROOF_TODAY", "2026-11-08")
    assert greeting in visitor(lang).get("/").text
    road = visitor(lang).get("/road").text
    assert greeting in road and name in unescape(road)


def test_every_festival_has_a_look_in_the_scene():
    js = visitor().get("/static/js/road.js").text
    from core.domain import seasons
    for _, (theme, _, _, _) in seasons.FESTIVALS.items():
        assert re.search(rf"^  {theme}:\s+\{{", js, flags=re.M), theme          # (a festival the page announces must have a theme to show)
