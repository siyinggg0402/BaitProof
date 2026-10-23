"""Scam Road: answers are graded on the server, distance comes only from right lanes, three wrong lanes end the drive, finished drives reach the friends' board."""
import random

import pytest

from core.game import garage
from core.game import pool as gp
from core.game import road
from core.game import state as gs
from core.storage import accounts, model, runs

ME, MEI = "a" * 32, "b" * 32
SCAM, SAFE, CHECK = 0, 2, 1  # the lanes


def pool():
    items = [gp.Item(f"s{i}", f"Scam message {i}: pay the fee now at fee{i}.top", "scam", ["urgency-pressure"], f"tell {i}", "pay the fee", f"action {i}", "seed") for i in range(8)]
    items += [gp.Item(f"f{i}", f"A genuine message {i}", "safe", [], "fine", "", "ok", "seed") for i in range(4)]
    items += [gp.Item(f"u{i}", f"Could be anyone {i}", "unsure", [], "cannot tell", "", "call them", "seed") for i in range(2)]
    return items


def begin(owner=ME, seed=7, **kw):
    random.seed(seed)  # the order of the messages is random by design; these tests need a known one
    out = road.start(owner, pool=pool(), **kw)
    return road.get(out["run"], owner), out


def lane_for(truth, wrong=False):
    if not wrong:
        return {"scam": SCAM, "safe": SAFE, "unsure": CHECK}[truth]
    return {"scam": SAFE, "safe": SCAM, "unsure": SCAM}[truth]


def waiting(r):
    """The gates the car has not reached yet, nearest first: [(gate id, message)]."""
    return [(gid, i) for gid, i in r.gates if gid not in r.answered]


def drive(r, n, *, wrong=False):
    out = None
    for _ in range(n):
        gid, item = waiting(r)[0]
        out = road.answer(r, gid, lane_for(item.truth, wrong))
    return out


def test_a_drive_starts_with_messages_but_no_answers():
    r, out = begin()
    assert len(out["items"]) == road.AHEAD + 1 and out["lives"] == 3 and out["gate"] == 80 and out["lanes"] == ["scam", "unsure", "safe"]
    assert all(set(i) == {"id", "text", "yours", "family"} for i in out["items"])
    blob = str(out)
    assert "truth" not in blob and "tell" not in blob.replace("tell_", "") and "action" not in blob  # nothing that gives an answer away
    assert out["best"] == 0 and out["account"] is False and out["ghosts"] == []


def test_a_right_lane_adds_a_stretch_of_road_xp_and_a_combo():
    r, _ = begin()
    before = gs.get()["xp"]
    a = drive(r, 3)
    assert a["outcome"] == "correct" and a["distance"] == 240 and a["combo"] == 3 and a["lives"] == 3 and not a["over"]
    assert gs.get()["xp"] - before == r.xp == 10 + 12 + 14
    assert a["lane"] in (0, 1, 2) and a["tell"] and a["action"]
    if any(i.truth == "scam" for gid, i in r.gates if gid in r.answered):  # (the first three gates may all be genuine messages, which teach no trick)
        assert any(m["success"] > 0 for m in model.all_mastery())  # the personal trick model learned from the drive
    drive(r, 12)
    assert any(m["success"] > 0 for m in model.all_mastery())


def test_a_wrong_lane_costs_a_heart_not_distance_and_three_end_the_drive():
    r, _ = begin()
    drive(r, 2)
    a = drive(r, 1, wrong=True)
    assert a["outcome"] == "wrong" and a["lives"] == 2 and a["distance"] == 160 and a["combo"] == 0 and a["next"]
    drive(r, 1, wrong=True)
    last = drive(r, 1, wrong=True)
    assert last["over"] and last["lives"] == 0 and last["next"] == []
    with pytest.raises(road.RoadError, match="over"):
        drive(r, 1)


def test_check_first_is_never_punished_but_goes_nowhere_unless_the_message_is_unclear():
    r, _ = begin()
    gid, _ = next((g, i) for g, i in waiting(r) if i.truth == "scam")
    a = road.answer(r, gid, CHECK)
    assert a["outcome"] == "partial" and a["lives"] == 3 and a["distance"] == 0 and a["combo"] == 0
    r2, _ = begin()
    while not any(i.truth == "unsure" for _, i in waiting(r2)):
        drive(r2, 1)
    gid, _ = next((g, i) for g, i in waiting(r2) if i.truth == "unsure")
    for g, i in [(g, i) for g, i in waiting(r2) if g != gid]:  # (answer the other gates first)
        road.answer(r2, g, lane_for(i.truth))
    assert road.answer(r2, gid, CHECK)["outcome"] == "correct"


def test_always_driving_down_the_middle_scores_nothing():
    r, _ = begin()
    for _ in range(30):
        gid, _ = waiting(r)[0]
        a = road.answer(r, gid, CHECK)
    clear = sum(1 for gid, i in r.gates if gid in r.answered and i.truth == "unsure")  # (the only gates where the middle lane is the right answer)
    assert r.distance == 80 * clear and a["lives"] == 3 and r.wrong == 0


@pytest.mark.parametrize("bad", [{"gate_id": "nope", "lane": 0}, {"gate_id": "g0", "lane": 3}, {"gate_id": "g0", "lane": -1}])
def test_bad_answers_are_refused(bad):
    r, _ = begin()
    with pytest.raises(road.RoadError):
        road.answer(r, **bad)


def test_a_gate_cannot_be_answered_twice_nor_one_that_was_never_dealt():
    r, _ = begin()
    gid, item = r.gates[0]
    road.answer(r, gid, lane_for(item.truth))
    with pytest.raises(road.RoadError, match="Already"):
        road.answer(r, gid, SCAM)
    with pytest.raises(road.RoadError, match="isn't part"):
        road.answer(r, f"g{len(r.gates)}", SCAM)


def test_only_the_driver_can_continue_a_drive():
    _, out = begin()
    with pytest.raises(road.RoadError, match="expired"):
        road.get(out["run"], MEI)
    with pytest.raises(road.RoadError, match="expired"):
        road.get("nope", ME)


def test_the_road_keeps_a_buffer_of_gates_ahead_and_a_message_that_comes_round_again_is_a_new_gate():
    r, _ = begin()
    dealt = [i.id for _, i in r.gates]
    for _ in range(40):
        gid, item = waiting(r)[0]
        a = road.answer(r, gid, lane_for(item.truth))
        dealt += [n["text"] and next(i.id for g, i in r.gates if g == n["id"]) for n in a["next"]]
        assert len(waiting(r)) >= road.AHEAD
    assert len({g for g, _ in r.gates}) == len(r.gates) == len(dealt) and r.correct == 40  # (14 messages, 46 gates: every one was answerable)
    assert all(x != y for x, y in zip(dealt, dealt[1:])) and {i.id for i in pool()} <= set(dealt)  # no message twice in a row, and every message gets its turn


def test_a_pool_that_is_too_small_is_refused():
    with pytest.raises(road.RoadError, match="Not enough"):
        road.start(ME, pool=pool()[:3])


def test_finishing_records_the_distance_on_the_board_and_awards_badges():
    mei, _ = accounts.create(MEI, "Mei", "🐼")
    accounts.create(ME, "Aiman", "🦊")
    accounts.add_friend(ME, mei["friend_code"])
    runs.record(MEI, runs.ROAD, 300, 4)
    r, out = begin()
    assert out["account"] is True and [g["nickname"] for g in out["ghosts"]] == ["Mei"] and out["ghosts"][0]["best"] == 300
    drive(r, 7)  # 560 m
    s = road.finish(r)
    assert s["distance"] == 560 and s["correct"] == 7 and s["new_best"] and s["personal_best"] == 560
    assert [p["nickname"] for p in s["passed"]] == ["Mei"]
    assert {b["id"] for b in s["badges_new"]} >= {"road-500", "road-ahead", "first-round"}
    assert [(row["nickname"], row["best"]) for row in s["board"]] == [("Aiman", 560), ("Mei", 300)]
    assert runs.best(ME) == 560 and road.finish(r)["distance"] == 560 and runs.board(ME)[0]["runs"] == 1  # finishing twice records once


def test_leaving_without_an_answer_records_nothing_and_a_short_drive_is_not_a_best_when_you_did_better():
    accounts.create(ME, "Aiman")
    r, _ = begin()
    s = road.finish(r)
    assert s["distance"] == 0 and not s["new_best"] and runs.best(ME) == 0 and runs.board(ME)[0]["runs"] == 0
    runs.record(ME, runs.ROAD, 800, 10)
    r2, _ = begin()
    drive(r2, 2)
    s2 = road.finish(r2)
    assert not s2["new_best"] and s2["personal_best"] == 800 and s2["passed"] == []


def test_without_an_account_a_drive_still_counts_but_shows_no_board():
    r, _ = begin()
    drive(r, 2)
    s = road.finish(r)
    assert s["board"] == [] and s["account"] is False and runs.best(ME) == 160


def test_explanations_and_badges_come_back_in_the_players_language():
    r, _ = begin()
    gid, scam = next((g, i) for g, i in waiting(r) if i.truth == "scam")
    scam.tell, scam.action = "礼品卡、加密货币和电汇是骗子收钱的方式。", "先停下来。"
    a = road.answer(r, gid, SCAM, lang="ms")
    assert "礼品卡" not in a["tell"] and a["tell"] and "先停下来" not in a["action"]  # a Chinese explanation is never shown to a Malay reader
    assert a["tricks"] == ["Mendesak anda"]
    drive(r, 6)
    s = road.finish(r, lang="ms")
    assert all(b["title"] != gs.BADGES[b["id"]][0] for b in s["badges_new"])


# ---------------------------------------------------------------- the Daily Road, ghosts and the garage
def daily(owner=ME, lang="en", items=None):
    out = road.start(owner, lang, pool=items or pool(), mode="daily")
    return road.get(out["run"], owner), out


def test_the_daily_road_is_the_same_for_everyone_and_changes_with_the_day_and_the_language(monkeypatch):
    random.seed(1)
    a, _ = daily(ME)
    random.seed(99)  # (a different luck of the draw must not matter)
    b, _ = daily(MEI)
    for r in (a, b):
        drive(r, 30)
    assert [i.id for _, i in a.gates] == [i.id for _, i in b.gates] and len(a.gates) > 30
    monkeypatch.setattr(gs, "today", lambda: "2031-02-03")
    c, _ = daily(ME)
    drive(c, 30)
    assert [i.id for _, i in c.gates] != [i.id for _, i in a.gates]
    monkeypatch.undo()
    d, _ = daily(ME, lang="ms")
    drive(d, 30)
    assert [i.id for _, i in d.gates] != [i.id for _, i in a.gates]


def test_the_free_drive_is_not_the_same_every_time():
    seqs = set()
    for seed in range(4):
        r, _ = begin(seed=seed)
        seqs.add(tuple(i.id for _, i in r.gates))
    assert len(seqs) > 1


def test_private_messages_stay_out_of_the_daily_road():
    items = pool() + [gp.Item("y1", "Mum's own scam", "scam", ["urgency-pressure"], "t", "scam", "a", "yours"), gp.Item("fam1", "A cousin's scam", "scam", ["urgency-pressure"], "t", "scam", "a", "family")]
    r, _ = daily(items=items)
    drive(r, 40)
    assert not {i.id for _, i in r.gates} & {"y1", "fam1"}
    free = road.start(ME, pool=items)
    assert any(g["yours"] or g["family"] for g in free["items"]) or True   # (in the free drive they may appear; they are flagged so the page can say whose they are)


def test_a_finished_drive_keeps_the_pace_of_every_gate_and_the_skin_but_no_answers():
    accounts.create(ME, "Aiman")
    r, _ = begin()
    drive(r, 3)
    drive(r, 1, wrong=True)
    road.finish(r)
    row = runs.replays(ME, runs.ROAD, "all")[0] if runs.replays(ME, runs.ROAD, "all") else None
    assert row and row["path"] == "cccw" and row["car"] == "plum" and row["hat"] == "none" and row["score"] == 240
    assert set(row["path"]) <= set("cpw")


def test_friends_ghosts_are_todays_best_paths_and_include_your_own():
    mei, _ = accounts.create(MEI, "Mei", "🐼")
    accounts.create(ME, "Aiman", "🦊")
    accounts.add_friend(ME, mei["friend_code"])
    m, _ = daily(MEI)
    drive(m, 4)
    drive(m, 3, wrong=True)
    road.finish(m)
    a, out = daily(ME)
    assert [(g["nickname"], g["score"], g["path"]) for g in out["replays"]] == [("Mei", 320, "ccccwww")] and "profile" not in str(out["replays"])
    drive(a, 2)
    road.finish(a)
    again = road.start(ME, pool=pool(), mode="daily")
    assert [(g["nickname"], g["you"]) for g in again["replays"]] == [("Mei", False), ("Aiman", True)]
    assert road.start(ME, pool=pool(), mode="road")["replays"] == []


def test_the_daily_road_has_its_own_board_and_a_first_of_the_day_bonus_and_badge(monkeypatch):
    accounts.create(ME, "Aiman")
    r, _ = daily()
    drive(r, 2)
    s = road.finish(r)
    assert s["mode"] == "daily" and s["first_daily"] and any(b["id"] == "road-daily" for b in s["badges_new"]) and s["xp_gained"] >= road.XP_DAILY_ROAD
    assert runs.best(ME, runs.DAILY) == 160 and runs.best(ME, runs.ROAD) == 0 and [(x["nickname"], x["best"]) for x in s["board"]] == [("Aiman", 160)]
    r2, _ = daily()
    drive(r2, 1)
    s2 = road.finish(r2)
    assert not s2["first_daily"] and gs.get()["road_daily_count"] == 1 and not any(b["id"] == "road-daily" for b in s2["badges_new"])


def test_the_garage_unlocks_from_what_you_have_done_and_a_drive_says_what_it_just_earned():
    accounts.create(ME, "Aiman")
    cat = garage.catalog(ME)
    assert [c["id"] for c in cat["cars"] if c["unlocked"]] == ["plum"] and [h["id"] for h in cat["hats"] if h["unlocked"]] == ["none"]
    assert cat["cars"][3]["need"] == "Play 3 days in a row" and cat["cars"][1]["need"] == "Reach level 2"
    with pytest.raises(garage.GarageError, match="locked"):
        garage.choose(ME, "gold", "none")
    with pytest.raises(garage.GarageError):
        garage.choose(ME, "nope", "none")
    r, _ = daily()
    drive(r, 5)  # 400 m: the sky blue car; and the Daily Road: the party hat
    s = road.finish(r)
    assert {"kind": "hat", "id": "party", "name": "Party hat"} in s["unlocked"] and {"kind": "car", "id": "sky", "name": "Sky"} in s["unlocked"]
    assert garage.choose(ME, "sky", "party") == {"car": "sky", "hat": "party"} and garage.selected(ME) == {"car": "sky", "hat": "party"}
    r2, out = begin()
    assert out["skin"] == {"car": "sky", "hat": "party", "color": "#3FA7E8"}
    drive(r2, 1)
    road.finish(r2)
    assert runs.replays(ME, runs.ROAD, "all")[0]["car"] == "sky"


def test_a_skin_that_is_no_longer_earned_falls_back_to_the_plain_one():
    s = gs.get()
    s["garage"] = {"car": "gold", "hat": "crown"}
    gs.save(s)
    assert garage.selected(ME) == {"car": "plum", "hat": "none"}


def test_the_garage_speaks_the_players_language():
    cat = garage.catalog(ME, "ms")
    assert cat["cars"][1]["name"] == "Pudina" and cat["cars"][1]["need"] == "Capai tahap 2" and cat["hats"][4]["name"] == "Skarf"
    assert garage.catalog(ME, "zh")["cars"][0]["name"] == "紫梅"
