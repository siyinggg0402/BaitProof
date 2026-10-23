"""Live head-to-head races: the lobby, the shared countdown, the same twelve gates for everybody, live progress for the rivals, the ranking and its tie-breaks, forfeits, XP and badges, and the record between two people."""
import pytest

from core.game import duel, road
from core.game import pool as gp
from core.game import state as gs
from core.storage import accounts, db, runs

A, B, C, D = "a" * 32, "b" * 32, "c" * 32, "d" * 32
LANE = {"scam": 0, "unsure": 1, "safe": 2}


class Clock:
    t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def arena(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    clock = Clock()
    monkeypatch.setattr(road, "_now", clock)
    duel.reset()
    monkeypatch.setattr(gp, "build_pool", lambda lang="en": pool())
    for pid, name in ((A, "Mum"), (B, "Aiman"), (C, "Mei"), (D, "Raj")):
        accounts.create(pid, name, "🦊")
    return clock


def pool():
    items = [gp.Item(f"s{i}", f"Scam message {i}: pay the fee now", "scam", ["urgency-pressure"], f"tell {i}", "pay the fee", f"action {i}", "seed") for i in range(10)]
    items += [gp.Item(f"f{i}", f"A genuine message {i}", "safe", [], "fine", "", "ok", "seed") for i in range(5)]
    items += [gp.Item("y1", "Mum's own scam", "scam", ["urgency-pressure"], "t", "scam", "a", "yours")]
    return items


def befriend(*pairs):
    for x, y in pairs:
        accounts.add_friend(x, accounts.get(y)["friend_code"])


def lobby(*players, host=A):
    d = duel.create(host, "en")
    for p in players:
        duel.join(d.code, p, "en")
    return d


def go(d, clock):
    duel.start(d.code, d.host)
    clock.t += duel.COUNTDOWN + 0.1
    return d


def waiting(r):
    return [(g, i) for g, i in r.gates if g not in r.answered]


def drive(d, profile, right=True, n=1, clock=None, dt=3.0):
    """`n` gates for one driver; time passes between them, during which everybody's browser keeps polling (so nobody is counted out)."""
    p = duel._player(d, profile)
    for _ in range(n):
        gid, item = waiting(p.run)[0]
        truth = {"scam": 0, "unsure": 1, "safe": 2}[item.truth]
        lane = truth if right else {"scam": 2, "safe": 0, "unsure": 0}[item.truth]
        if clock:
            clock.t += dt
            for q in d.players:
                duel.heard_from(d, q.profile)
        with db.as_profile(profile):
            road.answer(p.run, gid, lane)


def test_a_lobby_needs_a_profile_and_holds_up_to_four():
    with pytest.raises(duel.DuelError, match="profile first"):
        duel.create("z" * 32, "en")
    d = duel.create(A, "en")
    assert len(d.code) == 6 and d.state == "lobby" and [p.nickname for p in d.players] == ["Mum"]
    for who in (B, C, D):
        duel.join(d.code, who, "en")
    accounts.create("e" * 32, "Extra")
    with pytest.raises(duel.DuelError, match="full"):
        duel.join(d.code, "e" * 32, "en")
    assert duel.join(d.code.lower(), B, "en") is d and len(d.players) == 4   # (joining twice is fine)
    with pytest.raises(duel.DuelError, match="isn't open"):
        duel.join("ZZZZZZ", B, "en")


def test_only_the_host_starts_and_needs_someone_to_race():
    d = duel.create(A, "en")
    with pytest.raises(duel.DuelError, match="at least one more"):
        duel.start(d.code, A)
    duel.join(d.code, B, "en")
    with pytest.raises(duel.DuelError, match="Only the person who opened"):
        duel.start(d.code, B)
    duel.start(d.code, A)
    assert d.state == "countdown"
    with pytest.raises(duel.DuelError, match="already started"):
        duel.start(d.code, A)
    with pytest.raises(duel.DuelError, match="already started"):
        duel.join(d.code, C, "en")


def test_three_open_races_at_most():
    for _ in range(3):
        duel.create(A, "en")
    with pytest.raises(duel.DuelError, match="three races open"):
        duel.create(A, "en")
    duel.create(B, "en")


def test_the_countdown_runs_on_the_servers_clock(arena):
    d = lobby(B)
    duel.start(d.code, A)
    v = duel.view(d, B)
    assert v["state"] == "countdown" and v["start_at"] - v["now"] == duel.COUNTDOWN
    arena.t += duel.COUNTDOWN - 0.5
    assert duel.view(d, B)["state"] == "countdown"
    arena.t += 0.6
    assert duel.view(d, B)["state"] == "racing"


def test_every_driver_gets_the_very_same_gates_and_none_is_private():
    d = lobby(B, C)
    duel.start(d.code, A)
    seqs = []
    for who in (A, B, C):
        p = duel._player(d, who)
        for _ in range(duel.GATES - 6):
            drive(d, who)
        seqs.append([i.id for _, i in p.run.gates])
    assert seqs[0] == seqs[1] == seqs[2] and len(seqs[0]) == duel.GATES and "y1" not in seqs[0]
    first = duel.view(d, A, with_run=True)["you_run"]
    assert first["mode"] == "duel" and first["limit"] == duel.GATES and len(first["items"]) == road.AHEAD + 1 and "truth" not in str(first)


def test_a_drive_in_a_race_is_a_fixed_length_and_over_at_twelve_or_no_hearts(arena):
    d = go(lobby(B), arena)
    r = duel._player(d, A).run
    drive(d, A, n=duel.GATES)
    assert r.over and len(r.gates) == duel.GATES and r.distance == 12 * road.GATE
    with pytest.raises(road.RoadError, match="over"):
        road.answer(r, "g0", 0)
    rb = duel._player(d, B).run
    drive(d, B, right=False, n=3)
    assert rb.over and rb.lives == 0 and len(rb.answered) == 3


def test_answers_are_timed_from_the_start_and_rivals_see_progress_but_no_answers(arena):
    d = go(lobby(B), arena)
    arena.t += 0.9    # (0.1 + 0.9 after the "go")
    drive(d, A, n=2, clock=arena, dt=2.0)
    drive(d, A, right=False, n=1, clock=arena, dt=2.0)
    v = duel.view(d, B)
    mine, rival = v["players"][1], v["players"][0]
    assert rival["nickname"] == "Mum" and rival["progress"]["path"] == "ccw" and rival["progress"]["times"] == [3.0, 5.0, 7.0] and rival["progress"]["lives"] == 2 and not rival["progress"]["finished"]
    assert mine["you"] and mine["progress"]["n"] == 0
    blob = str(v)
    assert "truth" not in blob and "tell" not in blob.replace("tell_", "") and A not in blob and B not in blob and rival["progress"]["correct"] == 2 and "lane" not in blob


def test_most_right_answers_wins_then_hearts_then_who_finished_first(arena):
    d = go(lobby(B, C), arena)
    drive(d, A, n=12, clock=arena)                      # Mum: 12 right
    drive(d, B, n=11, clock=arena)                      # Aiman: 11 right, then a wrong one
    drive(d, B, right=False, n=1, clock=arena)
    drive(d, C, n=11, clock=arena)                      # Mei: 11 right, a wrong one, but she finishes later
    arena.t += 5
    drive(d, C, right=False, n=1, clock=arena)
    v = duel.view(d, A)
    assert v["state"] == "done"
    assert [(x["nickname"], x["correct"], x["rank"]) for x in v["result"]["ranking"]] == [("Mum", 12, 1), ("Aiman", 11, 2), ("Mei", 11, 3)]
    assert v["result"]["winner"] == duel._player(d, A).pub and v["result"]["you"]["won"] and v["result"]["you"]["rank"] == 1


def test_more_hearts_left_breaks_a_tie_in_right_answers(arena):
    d = go(lobby(B), arena)
    drive(d, A, n=6, clock=arena)                   # Mum: 11 right and 1 wrong: two hearts left
    drive(d, A, right=False, n=1, clock=arena)
    drive(d, A, n=5, clock=arena)
    drive(d, B, n=10, clock=arena)                  # Aiman: 10 right and 2 wrong
    drive(d, B, right=False, n=2, clock=arena)
    assert [x["nickname"] for x in duel.view(d, A)["result"]["ranking"]] == ["Mum", "Aiman"]
    d2 = go(lobby(B), arena)
    drive(d2, B, n=12, clock=arena)                                   # the same twelve right: whoever finished first wins
    drive(d2, A, n=12, clock=arena)
    assert [x["nickname"] for x in duel.view(d2, A)["result"]["ranking"]] == ["Aiman", "Mum"]


def test_the_winner_gets_xp_a_badge_and_a_record_and_everyone_who_finished_gets_something(arena):
    d = go(lobby(B), arena)
    drive(d, A, n=12, clock=arena)
    drive(d, B, n=5, clock=arena)
    drive(d, B, right=False, n=3, clock=arena)
    v = duel.view(d, A)
    assert v["result"]["you"] == {"rank": 1, "won": True, "xp": 35, "badges": [{"id": "duel-win", "title": "Duelist", "desc": "Win a live race"}]}
    assert duel.view(d, A, lang="ms")["result"]["you"]["badges"][0]["title"] != "Duelist"
    vb = duel.view(d, B)
    assert vb["result"]["you"]["won"] is False and vb["result"]["you"]["xp"] == 10 and vb["result"]["you"]["badges"] == []
    db.set_profile(A)
    s = gs.get()
    assert s["duel_wins"] == 1 and s["duels_played"] == 1 and "duel-win" in s["badges"]
    assert duel.record(A, B) == [1, 0] and duel.record(B, A) == [0, 1] and duel.view(d, A)["players"][1]["record"] == [1, 0]


def test_five_wins_make_a_race_champion(arena):
    for _ in range(5):
        d = go(lobby(B), arena)
        drive(d, A, n=12, clock=arena)
        drive(d, B, right=False, n=3, clock=arena)
    db.set_profile(A)
    assert {"duel-win", "duel-5"} <= set(gs.get()["badges"]) and duel.record(A, B) == [5, 0]


def test_a_driver_who_goes_quiet_is_counted_out_so_nobody_waits(arena):
    d = go(lobby(B), arena)
    drive(d, A, n=12, clock=arena)
    drive(d, B, n=4, clock=arena)
    assert duel.view(d, A)["state"] == "racing"
    arena.t += duel.FORFEIT_AFTER - 5
    duel.view(d, A)                       # (Mum keeps polling; Aiman does not)
    arena.t += 10
    v = duel.view(d, A)
    assert v["state"] == "done" and [(x["nickname"], x["forfeit"], x["rank"]) for x in v["result"]["ranking"]] == [("Mum", False, 1), ("Aiman", True, 2)]
    db.set_profile(B)
    assert gs.get()["duels_played"] == 0      # (no XP for leaving)


def test_leaving_in_the_race_is_a_forfeit_and_in_the_lobby_just_leaves(arena):
    d = lobby(B, C)
    duel.leave(d.code, C)
    assert [p.nickname for p in d.players] == ["Mum", "Aiman"]
    go(d, arena)
    duel.leave(d.code, B)
    assert duel._player(d, B).forfeited
    drive(d, A, n=12, clock=arena)
    assert duel.view(d, A)["state"] == "done" and duel.record(A, B) == [1, 0]
    d2 = duel.create(A, "en")
    duel.join(d2.code, B, "en")
    duel.leave(d2.code, A)
    assert d2.state == "closed" and duel.view_by_code(d2.code, B)["state"] == "closed"
    with pytest.raises(duel.DuelError, match="isn't open"):
        duel.join(d2.code, C, "en")


def test_a_race_nobody_finishes_ends_by_itself_and_an_unstarted_lobby_closes(arena):
    d = go(lobby(B), arena)
    drive(d, A, n=3, clock=arena)
    drive(d, B, n=3, clock=arena)
    for who in (A, B):
        duel._player(d, who).last_seen = arena.t + 10_000     # (still polling: only the race clock can end it)
    arena.t += duel.RACE_MAX + 1
    v = duel.view(d, A)
    assert v["state"] == "done" and all(x["forfeit"] for x in v["result"]["ranking"]) and v["result"]["winner"] == ""
    lonely = duel.create(C, "en")
    duel.join(lonely.code, D, "en")
    arena.t += duel.LOBBY_TTL + 1
    assert duel.view_by_code(lonely.code, D)["state"] == "closed"      # (the people waiting in it are told)
    with pytest.raises(duel.DuelError, match="isn't open"):
        duel.join(lonely.code, B, "en")


def test_only_friends_are_asked_in_and_the_invites_show_up_for_them():
    befriend((A, B))
    d = duel.create(A, "en", invite_pubs=[accounts.get(B)["pub"], accounts.get(C)["pub"]])
    assert d.invited == [accounts.get(B)["pub"]]                      # (Mei is not Mum's friend)
    assert duel.invites_for(B) == [{"code": d.code, "host": "Mum", "avatar": "🦊", "players": 1}] and duel.invites_for(C) == [] and duel.invites_for(A) == []
    assert duel.invited_profiles(d, A) == [B]
    duel.join(d.code, B, "en")
    assert duel.invites_for(B) == [] and [m["code"] for m in duel.mine(B)] == [d.code]


def test_a_stranger_cannot_watch_a_race_they_are_not_in():
    d = lobby(B)
    with pytest.raises(duel.DuelError, match="not in that race"):
        duel.view(d, C)


def test_nothing_a_driver_sees_holds_a_profile_id(arena):
    d = go(lobby(B, C), arena)
    drive(d, A, n=3, clock=arena)
    seen = repr([duel.view(d, who, with_run=True) for who in (A, B, C)]) + repr(duel.invites_for(B)) + repr(duel.mine(A))
    assert not [x for x in (A, B, C, D) if x in seen]


def test_each_drive_is_recorded_as_a_live_race_drive_and_not_on_the_road_boards(arena):
    d = go(lobby(B), arena)
    drive(d, A, n=12, clock=arena)
    drive(d, B, right=False, n=3, clock=arena)
    with db.as_profile(A):
        s = road.finish(duel._player(d, A).run)
    assert s["mode"] == "duel" and s["distance"] == 960 and s["badges_new"] == [] and s["passed"] == []
    assert runs.best(A, runs.DUEL) == 960 and runs.best(A, runs.ROAD) == 0 and runs.best(A, runs.DAILY) == 0
    with db.as_profile(A):
        assert road.finish(duel._player(d, A).run)["distance"] == 960      # (finishing twice records once)
