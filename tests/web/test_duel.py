"""Live races through the website: the hub, challenges, the lobby, a whole race driven through the API by two visitors, the result, the record, and who may see what."""
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from core.game import duel, road
from core.game import pool as gp
from core.storage import accounts, push
from web import deps
from web.main import app

HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
LANE = {"scam": 0, "unsure": 1, "safe": 2}
WRONG = {"scam": 2, "safe": 0, "unsure": 0}


class Clock:
    t = 2_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def arena(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    deps.HITS.clear()
    deps.LOGIN_HITS.clear()
    accounts._TRIES.clear()
    duel.reset()
    clock = Clock()
    monkeypatch.setattr(road, "_now", clock)
    return clock


TRUTH = {}


def visitor(lang="en"):
    c = TestClient(app)
    c.cookies.set("lang", lang)
    c.get("/")
    return c


def pid(c):
    return c.cookies.get("bp")


def sign_up(c, name):
    assert c.post("/me/create", data={"nickname": name, "avatar": "🦊"}).status_code == 200


def friends(a, b):
    a.post("/friends/add", data={"code": accounts.get(pid(b))["friend_code"]})


def code_from(r):
    return r.headers["location"].rsplit("/", 1)[1]


def truth_of(text):
    if not TRUTH:
        TRUTH.update({i.text: i.truth for i in gp.build_pool("en")})
    return TRUTH[text]


def drive(c, run, gates, n, right=True):
    out = None
    for _ in range(n):
        g = gates.pop(0)
        t = truth_of(g["text"])
        out = c.post("/api/road/answer", json={"run": run["run"], "gate": g["id"], "lane": LANE[t] if right else WRONG[t]}).json()
        gates += out["next"]
        if out["over"]:
            break
    return out


def setup_race(arena, *names):
    """The first person opens the race and asks the rest (who are all her friends); everyone joins; she starts it; the countdown runs out."""
    people = [visitor() for _ in names]
    for c, n in zip(people, names):
        sign_up(c, n)
    for other in people[1:]:
        friends(people[0], other)
    r = people[0].post("/duel/new", data={"pub": [accounts.get(pid(o))["pub"] for o in people[1:]]}, follow_redirects=False)
    assert r.status_code == 303
    code = code_from(r)
    for o in people[1:]:
        assert o.post(f"/api/duel/{code}/join").status_code == 200
    started = people[0].post(f"/api/duel/{code}/start").json()
    arena.t += duel.COUNTDOWN + 0.1
    return people, code, started


def test_the_hub_asks_for_a_profile_and_otherwise_lists_friends_to_challenge():
    v = visitor()
    assert "Make your profile" in v.get("/duel").text
    sign_up(v, "Mum")
    html = v.get("/duel").text
    assert "Race a friend, live" in html and "Add a friend first" in html and 'name="pub"' not in html
    other = visitor()
    sign_up(other, "Aiman")
    friends(v, other)
    html = v.get("/duel").text
    assert 'name="pub"' in html and "Aiman" in html and "Open a race" in html


def test_a_challenge_asks_the_friend_in_and_tells_them_by_notification_when_they_have_them(monkeypatch):
    asked = []
    monkeypatch.setattr(push, "notify_challenge", lambda host, targets, code: asked.append((host, targets, code)) or len(targets))
    mum, kid, stranger = visitor(), visitor(), visitor()
    for c, n in ((mum, "Mum"), (kid, "Aiman"), (stranger, "Mei")):
        sign_up(c, n)
    friends(mum, kid)
    r = mum.post("/duel/new", data={"pub": [accounts.get(pid(kid))["pub"], accounts.get(pid(stranger))["pub"]]}, follow_redirects=False)
    code = code_from(r)
    assert asked == [(pid(mum), [pid(kid)], code)]            # (Mei is not a friend: she is not asked)
    assert f"/duel/{code}" in kid.get("/duel").text and "Mum challenged you" in unescape(kid.get("/duel").text)
    assert "challenged you" not in stranger.get("/duel").text and code in mum.get("/duel").text


def test_the_race_page_is_the_road_in_race_mode_and_a_stale_link_goes_back_to_the_hub():
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    code = code_from(mum.post("/duel/new", follow_redirects=False))
    html = kid.get(f"/duel/{code}").text
    assert f'data-duel="{code}"' in html and 'id="lobby"' in html and 'id="count"' in html and 'id="duel-end"' in html and 'id="scene"' in html and "Waiting room" in html
    assert f"/duel/{code}" in html and 'hidden' in re.search(r'<div class="over" id="intro"[^>]*>', html).group(0)
    r = kid.get("/duel/ZZZZZZ", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/duel?error=")
    assert "That race isn&#39;t open any more." in kid.get(r.headers["location"]).text


def test_the_hub_only_shows_messages_the_race_can_really_say():
    v = visitor()
    sign_up(v, "Mum")
    assert "Totally official: send money" not in v.get("/duel?error=Totally official: send money").text
    assert "That race has already started." in unescape(v.get("/duel?error=That race has already started.").text)


def test_a_whole_race_two_drivers_same_gates_a_winner_a_result_and_a_record(arena):
    (mum, kid), code, started = setup_race(arena, "Mum", "Aiman")
    assert started["state"] == "countdown" and started["you_run"]["limit"] == 12 and started["you_run"]["mode"] == "duel" and "truth" not in str(started)
    run_m = started["you_run"]
    run_k = kid.get(f"/api/duel/{code}?run=1").json()["you_run"]
    assert [g["text"] for g in run_m["items"]] == [g["text"] for g in run_k["items"]]                 # the very same gates
    assert kid.get(f"/api/duel/{code}").json()["state"] == "racing" and "you_run" not in kid.get(f"/api/duel/{code}").json()
    gm, gk = list(run_m["items"]), list(run_k["items"])
    drive(mum, run_m, gm, 12)
    drive(kid, run_k, gk, 7)
    live = mum.get(f"/api/duel/{code}").json()
    rival = [p for p in live["players"] if not p["you"]][0]
    assert rival["nickname"] == "Aiman" and rival["progress"]["path"] == "c" * 7 and len(rival["progress"]["times"]) == 7 and rival["progress"]["finished"] is False
    drive(kid, run_k, gk, 3, right=False)
    assert mum.post("/api/road/finish", json={"run": run_m["run"]}).json()["mode"] == "duel"
    kid.post("/api/road/finish", json={"run": run_k["run"]})
    done = mum.get(f"/api/duel/{code}").json()
    assert done["state"] == "done" and [(x["nickname"], x["correct"], x["rank"]) for x in done["result"]["ranking"]] == [("Mum", 12, 1), ("Aiman", 7, 2)]
    assert done["result"]["you"]["won"] and done["result"]["you"]["xp"] == 35 and done["result"]["you"]["badges"][0]["title"] == "Duelist"
    lost = kid.get(f"/api/duel/{code}").json()
    assert lost["result"]["you"]["won"] is False and lost["result"]["you"]["xp"] == 10 and [p["record"] for p in lost["players"] if not p["you"]] == [[0, 1]]
    assert "you 1–0" in unescape(mum.get("/duel").text) and "you 0–1" in unescape(kid.get("/duel").text)


def test_a_race_of_four_and_a_rematch_that_asks_the_same_people_in(arena, monkeypatch):
    (a, b, c, d), code, _ = setup_race(arena, "Mum", "Aiman", "Mei", "Raj")
    assert len(mum_view(a, code)["players"]) == 4
    r = b.post(f"/api/duel/{code}/rematch")
    assert r.status_code == 200 and len(r.json()["code"]) == 6 and r.json()["code"] != code
    assert "Aiman challenged you" in unescape(a.get("/duel").text)                  # (Aiman hosts the new one and asks the people who are his friends: only Mum is)
    assert "challenged you" not in c.get("/duel").text and "challenged you" not in d.get("/duel").text


def mum_view(c, code):
    return c.get(f"/api/duel/{code}").json()


def test_who_may_see_and_do_what():
    mum, kid, stranger, nobody = visitor(), visitor(), visitor(), visitor()
    for c, n in ((mum, "Mum"), (kid, "Aiman"), (stranger, "Mei")):
        sign_up(c, n)
    code = code_from(mum.post("/duel/new", follow_redirects=False))
    assert stranger.get(f"/api/duel/{code}").status_code == 403                                  # not in the race: cannot watch it
    assert nobody.post(f"/api/duel/{code}/join").status_code == 400 and "Make a profile first to race." in unescape(nobody.post(f"/api/duel/{code}/join").text)
    kid.post(f"/api/duel/{code}/join")
    assert kid.post(f"/api/duel/{code}/start").status_code == 400                                # only the host starts
    assert mum.post(f"/api/duel/{code}/start").status_code == 200
    assert stranger.post(f"/api/duel/{code}/join").status_code == 400 and "already started" in stranger.post(f"/api/duel/{code}/join").text
    assert stranger.get("/api/duel/ZZZZZZ").status_code == 404


def test_leaving_a_lobby_and_a_host_who_closes_it(arena):
    mum, kid = visitor(), visitor()
    sign_up(mum, "Mum")
    sign_up(kid, "Aiman")
    code = code_from(mum.post("/duel/new", follow_redirects=False))
    kid.post(f"/api/duel/{code}/join")
    kid.post(f"/api/duel/{code}/leave")
    assert [p["nickname"] for p in mum_view(mum, code)["players"]] == ["Mum"]
    kid.post(f"/api/duel/{code}/join")
    mum.post(f"/api/duel/{code}/leave")
    assert kid.get(f"/api/duel/{code}").json()["state"] == "closed"                                # (the guest waiting is told)
    assert kid.post(f"/api/duel/{code}/join").status_code == 404


def test_the_lobby_needs_two_and_at_most_three_are_open_at_once():
    mum = visitor()
    sign_up(mum, "Mum")
    code = code_from(mum.post("/duel/new", follow_redirects=False))
    r = mum.post(f"/api/duel/{code}/start")
    assert r.status_code == 400 and "at least one more" in r.text
    for _ in range(2):
        mum.post("/duel/new")
    r = mum.post("/duel/new", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/duel?error=")
    assert "three races open" in unescape(mum.get(r.headers["location"]).text)


def test_nothing_in_a_race_holds_a_profile_id(arena):
    (mum, kid), code, started = setup_race(arena, "Mum", "Aiman")
    seen = [mum.get("/duel").text, kid.get("/duel").text, kid.get(f"/duel/{code}").text, repr(started), repr(mum_view(mum, code)), repr(kid.get(f"/api/duel/{code}?run=1").json())]
    for blob in seen:
        assert not [h for h in HEX32.findall(blob) if h in (pid(mum), pid(kid))]


def test_the_race_pages_and_the_lobby_text_are_translated():
    mum = visitor("ms")
    sign_up(mum, "Mum")
    code = code_from(mum.post("/duel/new", follow_redirects=False))
    html = mum.get(f"/duel/{code}").text
    for w in ("Bilik menunggu", "Mulakan perlumbaan", "Perlumbaan langsung"):
        assert w in html, w
    hub = mum.get("/duel").text
    assert "Berlumba dengan kawan, secara langsung" in hub
    import json
    block = json.loads(re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, flags=re.S).group(1))
    assert block["dict"]["Waiting for friends to join…"] == "Menunggu kawan menyertai…" and block["dict"]["Go!"] == "Mula!"
    zh = visitor("zh")
    sign_up(zh, "Mum")
    assert "等候室" in zh.get(f"/duel/{code_from(zh.post('/duel/new', follow_redirects=False))}").text
