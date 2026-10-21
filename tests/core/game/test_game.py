from datetime import datetime, timedelta, timezone

import pytest

from core.domain.tactics import TACTICS
from core.game import engine, pool, state
from core.pipelines.check import check_message
from core.storage import db, model

SCAM, SAFE, UNSURE = "scam", "safe", "unsure"


def item(i, truth, tactic="", phrase="", source="seed", text=None):
    return pool.Item(f"g{i:03d}", text or f"message number {i} with some words to tap", truth, [tactic] if tactic else [], f"tell {i}", phrase, "do this", source)


def mini_pool():
    its = [item(i, SCAM, "urgency-pressure", phrase="number 1 with" if i == 1 else "") for i in range(1, 9)]
    its += [item(i, SAFE) for i in range(20, 26)] + [item(30, UNSURE), item(31, UNSURE)]
    return its


def play_all(r, answer=lambda it: it.truth):
    for it in r.items:
        if r.over:
            break
        engine.answer(r, it.id, answer(it))
    return r


@pytest.fixture
def clock(monkeypatch):
    """A controllable 'now' so streaks and dailies can be tested across days."""
    box = {"t": datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(db, "now", lambda: box["t"])
    return box


# ---------------------------------------------------------------- the pool
def test_pool_is_rich_valid_and_every_trick_has_a_boss():
    p = pool.build_pool()
    assert len({i.id for i in p}) == len(p) and {i.truth for i in p} == {SCAM, SAFE, UNSURE}
    for t in TACTICS:
        assert sum(1 for i in p if i.truth == SCAM and t in i.tactics) >= 3, t
    for i in p:
        if i.tell_phrase:
            assert i.tell_phrase in i.text and i.truth == SCAM


def test_scams_from_the_users_own_circle_join_the_pool_first():
    check_message("Hi from the neighbourhood watch: buy 4 gift cards and send me the numbers please. Don't tell anyone.", store=True, log=False)
    yours = [i for i in pool.build_pool() if i.source == "yours"]
    assert yours and yours[0].truth == SCAM and pool.build_pool()[0].source == "yours"


def test_phrase_span_for_highlighting():
    assert pool.phrase_span("Pay the fee now", "the FEE") == (4, 11) and pool.phrase_span("x", "") is None and pool.phrase_span("x", "zzz") is None


# ---------------------------------------------------------------- levels, streaks
def test_level_curve_and_titles():
    assert [state.level_for(x) for x in (0, 99, 100, 299, 300, 600, 1000)] == [1, 1, 2, 2, 3, 4, 5]
    assert state.xp_for(2) == 100 and state.xp_for(3) == 300 and state.title_for(1) == "Rookie" and state.title_for(99) == "Scam Slayer"


def test_streak_grows_daily_resets_after_a_gap_and_is_not_double_counted(clock):
    s = state.get()
    state.touch_streak(s)
    state.touch_streak(s)
    assert s["streak"] == 1
    clock["t"] += timedelta(days=1)
    state.touch_streak(s)
    assert s["streak"] == 2
    clock["t"] += timedelta(days=3)
    state.touch_streak(s)
    assert s["streak"] == 1 and s["best_streak"] == 2
    state.save(s)
    clock["t"] += timedelta(days=5)
    assert state.summary()["streak"] == 0  # a lapsed streak shows as 0 rather than a stale number


# ---------------------------------------------------------------- choosing messages
def test_a_rush_round_mixes_scams_genuine_and_check_first():
    r = engine.start("rush", items=mini_pool())
    truths = [i.truth for i in r.items]
    assert len(r.items) == 8 and truths.count(SCAM) >= 4 and SAFE in truths and UNSURE in truths and len({i.id for i in r.items}) == 8


def test_rush_prefers_the_tricks_you_are_weakest_at_and_your_own_scams(monkeypatch):
    real, seeds = engine.random.Random, iter(range(15))  # fifteen fixed seeds: the selection is random by design, and an unseeded version of this test failed ~3% of runs
    monkeypatch.setattr(engine.random, "Random", lambda *a: real(next(seeds)))
    its = mini_pool() + [item(50 + n, SCAM, "otp-credential-phish") for n in range(3)] + [item(60, SCAM, "advance-fee", source="yours")]
    for _ in range(3):
        model.record_result("otp-credential-phish", "incorrect")
    rounds = [engine.start("rush", items=its) for _ in range(15)]
    assert all(any(i.source == "yours" for i in r.items) for r in rounds)  # your own family's scam always makes the cut
    assert sum(any("otp-credential-phish" in i.tactics for i in r.items) for r in rounds) >= 12  # the weak trick shows up almost every time


def test_recently_seen_messages_are_rotated_out():
    big = [item(i, SCAM, "urgency-pressure") for i in range(1, 40)] + [item(i, SAFE) for i in range(100, 110)] + [item(200, UNSURE)]
    first = {i.id for i in engine.start("rush", items=big).items}
    s = state.get()
    s["seen"] = list(first)
    state.save(s)
    assert len(first & {i.id for i in engine.start("rush", items=big).items}) <= 2


def test_boss_round_has_the_tricks_messages_two_decoys_and_three_lives():
    r = engine.start("boss", "urgency-pressure", items=mini_pool())
    assert r.lives == 3 and sum(i.truth == SCAM for i in r.items) == 6 and sum(i.truth == SAFE for i in r.items) == 2 and all("urgency-pressure" in i.tactics for i in r.items if i.truth == SCAM)
    with pytest.raises(engine.GameError):
        engine.start("boss", "no-such-trick", items=mini_pool())


def test_daily_challenge_is_the_same_for_everyone_all_day_and_changes_tomorrow(clock):
    p = mini_pool() + [item(300 + n, SCAM, "advance-fee") for n in range(10)]
    a, b = [i.id for i in engine.start("daily", items=p).items], [i.id for i in engine.start("daily", items=list(reversed(p))).items]
    assert a == b
    clock["t"] += timedelta(days=1)
    assert [i.id for i in engine.start("daily", items=p).items] != a


def test_tell_mode_uses_only_messages_that_have_a_giveaway():
    p = [item(i, SCAM, "urgency-pressure", phrase="some words") for i in range(1, 8)] + [item(50, SCAM, "urgency-pressure")]
    assert all(i.tell_phrase for i in engine.start("tell", items=p).items)


def test_your_circle_needs_your_own_scams():
    with pytest.raises(engine.GameError):
        engine.start("yours", items=mini_pool())
    p = mini_pool() + [item(70 + n, SCAM, "advance-fee", source="yours") for n in range(3)]
    assert all(i.source == "yours" for i in engine.start("yours", items=p).items)


def test_unknown_mode_and_too_few_messages():
    with pytest.raises(engine.GameError):
        engine.start("nonsense", items=mini_pool())
    with pytest.raises(engine.GameError):
        engine.start("rush", items=mini_pool()[:2])


# ---------------------------------------------------------------- answers never leak
def test_the_browser_never_sees_the_answers_before_revealing():
    r = engine.start("rush", items=mini_pool())
    shown = engine.public(r)
    blob = str(shown)
    assert "truth" not in blob and "tell" not in blob.replace("tell_", "") and all(set(i) <= {"id", "text", "yours", "words"} for i in shown["items"])
    assert all(i.tell not in blob for i in r.items)


# ---------------------------------------------------------------- scoring
def test_grading_and_partial_credit_for_being_careful():
    r = engine.start("rush", items=mini_pool())
    scam = next(i for i in r.items if i.truth == SCAM)
    safe = next(i for i in r.items if i.truth == SAFE)
    unsure = next(i for i in r.items if i.truth == UNSURE)
    assert engine.answer(r, scam.id, SCAM)["outcome"] == "correct"
    res = engine.answer(r, safe.id, "unsure")
    assert res["outcome"] == "partial" and res["xp"] == engine.XP_PARTIAL  # caution is never punished
    assert engine.answer(r, unsure.id, SAFE)["outcome"] == "wrong"


def test_calling_a_genuine_message_a_scam_is_flagged_as_a_false_alarm_not_just_wrong():
    r = engine.start("rush", items=mini_pool())
    safe = next(i for i in r.items if i.truth == SAFE)
    res = engine.answer(r, safe.id, SCAM)
    assert res["outcome"] == "wrong" and res["false_alarm"] is True and res["tell"] == safe.tell


def test_combo_raises_xp_up_to_a_cap_and_a_slip_resets_it():
    r = engine.start("rush", items=mini_pool())
    scams = [i for i in r.items if i.truth == SCAM]
    gains = [engine.answer(r, i.id, SCAM)["xp"] for i in scams[:4]]
    assert gains == [10, 12, 14, 16] and r.combo == 4
    engine.answer(r, next(i for i in r.items if i.truth == SAFE).id, SCAM)
    assert r.combo == 0 and engine.answer(r, scams[4].id, SCAM)["xp"] == 10


def test_speed_bonus_only_when_asked_for():
    r = engine.start("rush", items=mini_pool())
    a, b = [i for i in r.items if i.truth == SCAM][:2]
    assert engine.answer(r, a.id, SCAM, fast=True)["xp"] == 10 + engine.XP_FAST + 0
    assert engine.answer(r, b.id, SCAM, fast=False)["xp"] == 12


def test_invalid_answers_are_rejected():
    r = engine.start("rush", items=mini_pool())
    it = r.items[0]
    with pytest.raises(engine.GameError):
        engine.answer(r, it.id, "maybe")
    with pytest.raises(engine.GameError):
        engine.answer(r, "nope", SCAM)
    engine.answer(r, it.id, it.truth)
    with pytest.raises(engine.GameError):
        engine.answer(r, it.id, it.truth)  # no answering twice (no XP farming)


def test_spot_the_tell_grading():
    p = [item(i, SCAM, "urgency-pressure", phrase="pay the fee now", text="Please pay the fee now or lose it today") for i in range(1, 8)] + mini_pool()[8:]
    r = engine.start("tell", items=p)
    it = r.items[0]
    words = it.text.split()
    full = [words.index("pay"), words.index("the"), words.index("fee"), words.index("now")]
    assert engine.answer(r, r.items[0].id, picked=full)["outcome"] == "correct"
    assert engine.answer(r, r.items[1].id, picked=full[:3])["outcome"] == "correct"  # most of the phrase is enough
    assert engine.answer(r, r.items[2].id, picked=[words.index("fee")])["outcome"] == "partial"
    assert engine.answer(r, r.items[3].id, picked=[words.index("Please"), words.index("lose"), words.index("today")])["outcome"] == "wrong"
    assert engine.answer(r, r.items[4].id, picked=[])["outcome"] == "wrong"
    r2 = engine.start("tell", items=p)
    assert engine.answer(r2, r2.items[0].id, picked=list(range(len(r2.items[0].text.split()))))["outcome"] != "correct"  # selecting everything is not finding the tell


def test_reveal_includes_the_highlight_and_the_explanation():
    p = [item(1, SCAM, "urgency-pressure", phrase="number 1 with")] + mini_pool()[1:]
    r = engine.start("rush", items=p)
    res = engine.answer(r, "g001", SCAM) if any(i.id == "g001" for i in r.items) else None
    if res:
        t = r.items[[i.id for i in r.items].index("g001")].text
        s, e = res["highlight"]
        assert t[s:e].lower() == "number 1 with" and res["tell"] and res["tricks"] == [TACTICS["urgency-pressure"]["label"]]


# ---------------------------------------------------------------- the personal model learns from the game
def test_playing_updates_the_same_trick_map_practice_uses():
    r = engine.start("rush", items=mini_pool())
    scams = [i for i in r.items if i.truth == SCAM]
    engine.answer(r, scams[0].id, SCAM)
    lv = {m["tactic"]: m["level"] for m in model.all_mastery()}
    assert lv["urgency-pressure"] == "learning"
    engine.answer(r, scams[1].id, SAFE)  # fooled
    assert {m["tactic"]: m["level"] for m in model.all_mastery()}["urgency-pressure"] == "weak"
    engine.answer(r, scams[2].id, "unsure")  # careful: no demotion, no promotion
    assert {m["tactic"]: m["level"] for m in model.all_mastery()}["urgency-pressure"] == "weak"


def test_genuine_and_check_first_messages_do_not_touch_the_trick_map():
    r = engine.start("rush", items=mini_pool())
    before = [m["level"] for m in model.all_mastery()]
    engine.answer(r, next(i for i in r.items if i.truth == SAFE).id, SAFE)
    assert [m["level"] for m in model.all_mastery()] == before


# ---------------------------------------------------------------- lives, bonuses, badges
def test_boss_loses_a_life_per_slip_and_ends_at_zero():
    r = engine.start("boss", "urgency-pressure", items=mini_pool())
    scams = [i for i in r.items if i.truth == SCAM]
    for n in range(3):
        res = engine.answer(r, scams[n].id, SAFE)
    assert res["lives"] == 0 and res["over"] is True
    with pytest.raises(engine.GameError):
        engine.answer(r, scams[3].id, SCAM)
    s = engine.finish(r)
    assert s["defeated"] is True and not s["won_boss"] and "boss:urgency-pressure" not in [b["id"] for b in s["badges_new"]]


def test_beating_a_boss_earns_its_badge_and_a_bonus_once():
    r = engine.start("boss", "urgency-pressure", items=mini_pool())
    play_all(r)
    s = engine.finish(r)
    assert s["won_boss"] and s["perfect"] and "boss:urgency-pressure" in [b["id"] for b in s["badges_new"]]
    assert s["xp_gained"] >= engine.XP_BOSS + engine.XP_PERFECT + engine.XP_FINISH
    again = engine.start("boss", "urgency-pressure", items=mini_pool())
    play_all(again)
    assert "boss:urgency-pressure" not in [b["id"] for b in engine.finish(again)["badges_new"]]  # already owned


def test_a_finished_round_awards_first_steps_perfect_and_a_streak_day():
    r = engine.start("rush", items=mini_pool())
    play_all(r)
    s = engine.finish(r)
    ids = [b["id"] for b in s["badges_new"]]
    assert {"first-round", "perfect-round"} <= set(ids) and s["perfect"] and s["state"]["streak"] == 1 and s["state"]["rounds"] == 1


def test_a_slip_means_no_perfect_bonus_but_still_a_finish_bonus():
    r = engine.start("rush", items=mini_pool())
    play_all(r, lambda it: SAFE if it.truth == SCAM else it.truth)
    s = engine.finish(r)
    assert not s["perfect"] and s["wrong"] > 0 and "perfect-round" not in [b["id"] for b in s["badges_new"]]


def test_finish_is_idempotent_so_xp_cannot_be_farmed_by_calling_it_twice():
    r = engine.start("rush", items=mini_pool())
    play_all(r)
    first = engine.finish(r)
    xp = state.get()["xp"]
    assert engine.finish(r) == first and state.get()["xp"] == xp


def test_daily_bonus_only_the_first_time_each_day(clock):
    r = engine.start("daily", items=mini_pool())
    play_all(r)
    assert engine.finish(r)["daily_bonus"] is True and state.summary()["daily_done"] is True
    r2 = engine.start("daily", items=mini_pool())
    play_all(r2)
    assert engine.finish(r2)["daily_bonus"] is False
    clock["t"] += timedelta(days=1)
    r3 = engine.start("daily", items=mini_pool())
    play_all(r3)
    assert engine.finish(r3)["daily_bonus"] is True and state.get()["streak"] == 2


def test_levelling_up_is_reported_with_the_old_level():
    s = state.get()
    s["xp"] = 95
    state.save(s)
    r = engine.start("rush", items=mini_pool())
    play_all(r)
    out = engine.finish(r)
    assert out["level_up"] is True and out["level_before"] == 1 and out["state"]["level"] >= 2


def test_abandoning_a_round_keeps_xp_earned_but_gives_no_finish_bonus():
    r = engine.start("rush", items=mini_pool())
    engine.answer(r, r.items[0].id, r.items[0].truth)
    out = engine.finish(r)
    assert out["completed"] is False and not out["badges_new"] and out["state"]["rounds"] == 0 and state.get()["xp"] > 0


def test_a_round_belongs_to_the_profile_that_started_it():
    r = engine.start("rush", items=mini_pool(), owner="alice")
    assert engine.get(r.id, "alice") is r
    with pytest.raises(engine.GameError):
        engine.get(r.id, "mallory")
    with pytest.raises(engine.GameError):
        engine.get("doesnotexist", "alice")


def test_overview_describes_hub_state():
    o = engine.overview()
    assert o["level"] == 1 and len(o["tricks"]) == 12 and all(t["messages"] >= 3 for t in o["tricks"]) and o["yours_available"] == 0
    assert o["badges_total"] == len(state.BADGES) and o["resilience"] == 0 and o["daily_done"] is False
