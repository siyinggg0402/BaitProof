from core.pipelines import challenge, train
from core.storage import model


def test_drill_session_moves_map():
    drills = train.build_session()
    assert len(drills) == 4
    before = model.baitproof_score()
    for d in drills:
        g = train.grade(d, d.correct_index, "I would ignore it and call the real bank")
        assert g.result == "correct"
    assert model.baitproof_score() > before
    levels = {r["tactic"]: r["level"] for r in model.all_mastery()}
    assert {levels[d.tactic] for d in drills} == {"learning"}


def test_wrong_answer_is_encouraging_and_demotes():
    d = train.build_session()[0]
    wrong = next(i for i in range(len(d.options)) if i != d.correct_index) if d.options else None
    g = train.grade(d, wrong, "here is my code 1234")
    assert g.result == "incorrect" and "wrong" not in g.note.lower()


def test_challenge_roundtrip():
    cid = challenge.create()
    items = challenge.get(cid)
    assert len(items) == 6
    res = challenge.score(items, [i["is_scam"] for i in items])
    assert res["pct"] == 100
