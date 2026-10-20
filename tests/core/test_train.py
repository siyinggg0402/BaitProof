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


def test_unfair_generated_distractors_are_rejected(monkeypatch):
    from core.ai import llm
    from core.storage import library

    ex = next(e for e in library.seed_examples() if e["id"] == "s07")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"question": "What now?", "wrong_options": [
        "Buy the gift cards and send the numbers", "Tell Mom right away", "Ignore the message and do nothing"]})
    q, wrong = train._wrong_options(ex, "emotional-manipulation")
    assert not any("ignore" in w.lower() or "tell mom" in w.lower() for w in wrong) and len(wrong) == 3  # unfair ones dropped
    assert q == "What is the safest thing to do?"  # only 1 valid option left: whole generation replaced by vetted templates
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"question": "What now?", "wrong_options": [
        "Buy the gift cards and send the numbers", "Reply and ask which store to go to", "Click the link they sent"]})
    assert train._wrong_options(ex, "emotional-manipulation")[1][0].startswith("Buy the gift")  # good ones are kept


def test_scammer_framing_with_the_word_verify_is_a_valid_distractor(monkeypatch):
    from core.ai import llm
    from core.storage import library

    ex = next(e for e in library.seed_examples() if e["id"] == "s07")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"question": "What now?", "wrong_options": [
        "Click on any link they send to verify the request", "Buy the gift cards", "Reply asking for more details"]})
    q, wrong = train._wrong_options(ex, "emotional-manipulation")
    assert q == "What now?" and "Click on any link they send to verify the request" in wrong
