"""Link Hunt: four links, one fake. The answer stays on the server, the fakes use the real tricks, every round trains the fake-address trick, and three wrong picks end the run."""
import random
import re

import pytest

from core.game import linkhunt as lh
from core.game import state as gs
from core.storage import accounts, model, runs

ME, MEI = "a" * 32, "b" * 32
HOST = re.compile(r"[a-z0-9.\-]+\.[a-z]{2,}")


def begin(seed=1, owner=ME):
    out = lh.start(owner, rng=random.Random(seed))
    return lh.get(out["hunt"], owner), out


def pick(h, right=True):
    q = h.question
    idx = q["answer"]["index"] if right else (q["answer"]["index"] + 1) % 4
    return lh.answer(h, q["id"], idx)


def test_a_question_shows_four_links_and_gives_nothing_away():
    h, out = begin()
    q = out["question"]
    assert len(q["options"]) == 4 and {"brand", "host"} == set(q["options"][0]) and out["lives"] == 3 and set(q) == {"id", "options"}
    blob = str(out)
    assert "answer" not in blob and "real" not in blob and "trick" not in blob
    assert len({o["brand"] for o in q["options"]}) == 4
    a = h.question["answer"]
    assert q["options"][a["index"]]["host"] == a["fake"] != a["real"]
    others = [o for i, o in enumerate(q["options"]) if i != a["index"]]
    real = dict(lh.BRANDS)
    assert all(real[o["brand"]] == o["host"] for o in others)      # the other three are the companies' real addresses


@pytest.mark.parametrize("seed", range(6))
def test_every_fake_is_a_plausible_address_that_is_not_a_real_one_and_every_trick_turns_up(seed):
    rng = random.Random(seed)
    real = {h for _, h in lh.BRANDS}
    seen = set()
    for _, host in lh.BRANDS:
        for _ in range(8):
            fake, trick, vals = lh.fake_of(host, rng)
            seen.add(trick)
            assert fake != host and fake not in real and HOST.fullmatch(fake) and trick in lh.TRICKS
            text = lh.explain(trick, vals, fake, host, "en")
            assert fake in text and host in text and "{" not in text
    assert seen == set(lh.TRICKS)


def test_each_trick_does_what_it_says():
    rng = random.Random(0)
    f = lambda host, trick: next(x for x in (lh.fake_of(host, rng) for _ in range(400)) if x[1] == trick)   # noqa: E731
    fake, _, v = f("paypal.com", "extra-word")
    assert fake == f"paypal-{v['word']}.com"
    fake, _, v = f("shopee.com.my", "bad-tld")
    assert fake == f"shopee.{v['tld']}" and v["tld"] in lh.BAD_TLDS
    fake, _, v = f("maybank2u.com.my", "subdomain-trick")
    assert fake == f"maybank2u.com.my.{v['tail']}" and fake.endswith(tuple("." + t for t in lh.BAD_TLDS))
    fake, _, _ = f("netflix.com", "hyphen-split")
    assert "-" in fake.split(".")[0] and fake.replace("-", "") == "netflix.com"
    fake, _, _ = f("netflix.com", "swapped-letters")
    assert sorted(fake.split(".")[0]) == sorted("netflix") or len(fake.split(".")[0]) == len("netflix") - 1
    fake, _, _ = f("paypal.com", "lookalike-letters")
    assert fake != "paypal.com" and len(fake.split(".")[0]) in (6, 7)


def test_a_right_pick_scores_and_chains_a_combo_and_trains_the_trick():
    h, out = begin()
    first_id = out["question"]["id"]
    a = pick(h)
    assert a["correct"] and a["score"] == 100 and a["combo"] == 1 and a["lives"] == 3 and a["xp"] == 10 and not a["over"]
    assert a["next"]["id"] != first_id and a["real"] and a["brand"] and a["tell"] and a["trick"] == "Fake website address"
    b = pick(h)
    assert b["score"] == 200 and b["combo"] == 2 and b["xp"] == 12
    assert [m["success"] for m in model.all_mastery() if m["tactic"] == "lookalike-link"] == [2]


def test_a_wrong_pick_costs_a_heart_and_shows_which_link_was_fake_and_why():
    h, out = begin()
    fake_at = h.question["answer"]["index"]
    a = pick(h, right=False)
    assert not a["correct"] and a["lives"] == 2 and a["score"] == 0 and a["combo"] == 0 and a["fake"] == fake_at   # (it says which one was the fake)
    assert a["tell"] and a["real"] in a["tell"] and out["question"]["options"][fake_at]["host"] in a["tell"]
    assert [m["fail"] for m in model.all_mastery() if m["tactic"] == "lookalike-link"] == [1]


def test_three_wrong_picks_end_the_run_and_nothing_more_is_accepted():
    h, _ = begin()
    pick(h)
    for _ in range(2):
        pick(h, right=False)
    last = pick(h, right=False)
    assert last["over"] and last["lives"] == 0 and last["next"] is None
    with pytest.raises(lh.LinkError, match="over"):
        lh.answer(h, "x", 0)


def test_a_stale_question_a_bad_choice_and_another_players_round_are_refused():
    h, out = begin()
    with pytest.raises(lh.LinkError, match="current one"):
        lh.answer(h, "nope", 0)
    with pytest.raises(lh.LinkError, match="four"):
        lh.answer(h, out["question"]["id"], 4)
    with pytest.raises(lh.LinkError, match="expired"):
        lh.get(out["hunt"], MEI)
    pick(h)
    with pytest.raises(lh.LinkError, match="current one"):
        lh.answer(h, out["question"]["id"], 0)   # (the first question was already answered)


def test_questions_do_not_repeat_a_company_in_a_row_and_the_fake_can_be_in_any_place():
    h, _ = begin(seed=5)
    asked, places = [], set()
    for _ in range(25):
        asked.append(h.question["answer"]["brand"])
        places.add(h.question["answer"]["index"])
        pick(h)
    assert all(x != y for x, y in zip(asked, asked[1:])) and places == {0, 1, 2, 3}
    assert len(set(asked[-8:])) == 8     # (not the same company within eight rounds)


def test_finishing_records_the_score_for_the_board_and_awards_a_badge_for_ten():
    accounts.create(ME, "Aiman")
    h, _ = begin()
    for _ in range(10):
        pick(h)
    pick(h, right=False)
    s = lh.finish(h)
    assert s["score"] == 1000 and s["correct"] == 10 and s["wrong"] == 1 and s["new_best"] and runs.best(ME, runs.LINK) == 1000
    assert {b["id"] for b in s["badges_new"]} >= {"link-10", "first-round"} and [(r["nickname"], r["best"]) for r in s["board"]] == [("Aiman", 1000)]
    assert lh.finish(h) is s and runs.board(ME, "week", runs.LINK)[0]["runs"] == 1     # once
    assert gs.get()["xp"] >= 100


def test_leaving_before_a_single_answer_records_nothing():
    accounts.create(ME, "Aiman")
    h, _ = begin()
    s = lh.finish(h)
    assert s["score"] == 0 and not s["new_best"] and runs.best(ME, runs.LINK) == 0


def test_the_link_board_is_separate_from_the_road_boards():
    mei, _ = accounts.create(MEI, "Mei")
    accounts.create(ME, "Aiman")
    accounts.add_friend(ME, mei["friend_code"])
    runs.record(MEI, runs.ROAD, 900, 11)
    h, _ = begin()
    pick(h)
    lh.finish(h)
    assert [(r["nickname"], r["best"]) for r in runs.board(ME, "week", runs.LINK) if r["runs"]] == [("Aiman", 100)]
    assert runs.best(MEI, runs.LINK) == 0


def test_the_explanations_come_in_the_players_language():
    zh = lh.explain("bad-tld", {"tld": "top"}, "shopee.top", "shopee.com.my", "zh")
    ms = lh.explain("extra-word", {"word": "secure"}, "paypal-secure.com", "paypal.com", "ms")
    assert "以 .top 结尾" in zh and "shopee.com.my" in zh and "menambah perkataan" in ms and "paypal.com" in ms and "{" not in zh + ms
    h, _ = begin()
    assert re.search("[一-鿿]", lh.answer(h, h.question["id"], 0, lang="zh")["tell"])


def test_what_the_game_teaches_is_what_the_checker_catches():
    """The fakes in the game are the tricks real scam sites use; the checker should call most of them out (hard evidence or a weak flag), tricks included."""
    from core.pipelines.check import tools

    rng = random.Random(11)
    total = flagged = 0
    by_trick: dict[str, list[int]] = {t: [0, 0] for t in lh.TRICKS}
    for _, host in lh.BRANDS:
        for _ in range(10):
            fake, trick, _vals = lh.fake_of(host, rng)
            c = tools.domain_check(fake)
            hit = bool(c["hard"] or c["soft"])
            total += 1
            flagged += hit
            by_trick[trick][0] += 1
            by_trick[trick][1] += hit
    assert flagged / total >= 0.78, (flagged, total, by_trick)
    for trick, (n, hit) in by_trick.items():
        assert hit / n >= (0.4 if trick == "hyphen-split" else 0.6), (trick, hit, n)
