"""Practice, the challenge and the game's texts in Chinese: questions, options, feedback, the model's prompts, titles and badges."""
import re

from core.ai import llm
from core.ai.prompts import GRADE_SYSTEM, WWYD_SYSTEM, grade_system, wwyd_system
from core.domain.schemas import Drill
from core.domain.tactics import TACTICS
from core.game import engine, state
from core.game import pool as gp
from core.pipelines import challenge, train
from core.storage import model
from core.storage import library


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


CJK = re.compile(r"[一-鿿]")
SIMPLIFIED_ONLY = re.compile("[骗这个们来说对错还没关发开练习记录]")


def test_a_chinese_practice_session_is_entirely_in_chinese():
    drills = train.build_session(lang="zh")
    assert len(drills) == 4
    for d in drills:
        assert CJK.search(d.scenario) and CJK.search(d.question) and CJK.search(d.reason) and CJK.search(d.explanation)
        if d.format == "spot-trick":
            assert d.options[d.correct_index] == i18n_label(d.tactic, "zh") and all(CJK.search(o) for o in d.options)
        if d.format == "what-to-do":
            assert all(CJK.search(o) for o in d.options)


def i18n_label(tid, lang):
    from core.lang.i18n import tactic_text

    return tactic_text(tid, "label", lang, TACTICS)


def test_traditional_practice_is_traditional():
    for d in train.build_session(lang="zh-Hant"):
        assert not SIMPLIFIED_ONLY.search(d.question + d.reason + d.explanation + d.scenario)
        if d.format == "spot-trick":
            assert d.options[d.correct_index] == i18n_label(d.tactic, "zh-Hant")


def test_english_practice_is_unchanged():
    for d in train.build_session():
        assert not CJK.search(d.scenario + d.question + d.reason + d.explanation + "".join(d.options))
    assert train._wrong_options({"text": "x", "action": "y"}, "urgency-pressure")[0] == "What is the safest thing to do?"
    assert train._encourage(True, "T") == "Nice catch! T" and train._encourage(False, "T").endswith("The giveaway: T")


def test_feedback_is_in_the_learners_language():
    d = Drill(id="a", tactic="urgency-pressure", format="spot-trick", scenario="s", question="q", options=["a", "b"], correct_index=0, explanation="破绽在这里。")
    assert train.grade(d, 0, record=False, lang="zh").note == "答对了！破绽在这里。"
    wrong = train.grade(d, 1, record=False, lang="zh")
    assert wrong.result == "incorrect" and wrong.note.startswith("没关系。") and wrong.note.endswith("破绽在这里：破绽在这里。")
    assert train.grade(d, 0, record=False, lang="zh-Hant").note == "答對了！破绽在这里。"  # the wording follows the reader; the explanation is the drill's own text
    assert train.grade(d, 0, record=False).note == "Nice catch! 破绽在这里。"


def test_a_free_text_reply_in_chinese_is_graded():
    d = Drill(id="a", tactic="urgency-pressure", format="safe-reply", scenario="s", question="q", options=[], correct_index=None, explanation="E")
    assert train.grade(d, text="我会忽略它，然后打电话给银行核实", record=False, lang="zh").result == "correct"
    assert train.grade(d, text="我會忽略它，然後打電話給銀行核實", record=False, lang="zh-Hant").result == "correct"  # Traditional works the same
    assert train.grade(d, text="好的，我的密码是123456", record=False, lang="zh").result == "incorrect"
    assert train.grade(d, text="hmm maybe", record=False, lang="zh").result == "partial" and "方向对了" in train.grade(d, text="hmm maybe", record=False, lang="zh").note
    assert train.grade(d, text="hmm maybe", record=False).note.startswith("You're on the right track.")


def test_an_explanation_always_comes_in_the_readers_language():
    loc = train.localized
    assert loc("Real companies give you time.", "urgency-pressure", "tell", "en") == "Real companies give you time."
    assert loc("Real companies give you time.", "urgency-pressure", "tell", "zh") == TACTIC_TELL_ZH      # English text: the trick's own Chinese one
    assert loc("正規公司會給你時間", "urgency-pressure", "tell", "zh") == "正规公司会给你时间"          # Chinese text: in the reader's script
    assert loc("正规公司会给你时间", "urgency-pressure", "tell", "zh-Hant") == "正規公司會給你時間"
    assert loc("Real companies give you time.", "", "tell", "zh") == ""                                  # nothing to stand in for it
    assert loc("Real companies give you time.", "urgency-pressure", "tell", "zh", safe=True) == ""
    assert loc("Nothing here asks for money, codes, passwords or a rush, so this one is fine.", "", "tell", "zh", safe=True).startswith("这条消息没有要钱")
    assert loc("", "urgency-pressure", "tell", "zh") == ""


TACTIC_TELL_ZH = "正规公司会给你时间。只给几个小时的期限，是施压的手段。"


def test_chinese_text_is_split_into_sentences():
    assert train._sentences("您好。请点击链接！不然将停用；速办") == ["您好。", "请点击链接！", "不然将停用；", "速办"]
    assert train._sentences("Hello there. Click now! Please") == ["Hello there.", "Click now!", "Please"]


def test_the_models_prompts_name_the_language_and_english_is_byte_identical(monkeypatch):
    assert wwyd_system("en") == WWYD_SYSTEM and grade_system("en") == GRADE_SYSTEM and wwyd_system() == WWYD_SYSTEM
    assert wwyd_system("zh").startswith(WWYD_SYSTEM) and "Simplified Chinese" in wwyd_system("zh") and "question" in wwyd_system("zh")
    assert "Traditional Chinese" in grade_system("zh-Hant") and grade_system("zh").startswith(GRADE_SYSTEM)
    seen = []
    ex = next(e for e in library.seed_examples() if e["id"] == "s07")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, *a, **k: seen.append(system) or {"question": "该怎么办？", "wrong_options": ["把礼品卡的卡号发给他", "忽略这条消息，什么都不做", "点击他发来的链接"]})
    q, wrong = train._wrong_options(ex, "emotional-manipulation", "zh")
    assert "Simplified Chinese" in seen[-1] and q == "该怎么办？"
    assert "忽略这条消息，什么都不做" not in wrong and "把礼品卡的卡号发给他" in wrong and len(wrong) == 3  # the unfair option is replaced by a vetted one
    assert all(CJK.search(w) for w in wrong)
    train._wrong_options(ex, "emotional-manipulation")
    assert seen[-1] == WWYD_SYSTEM


def test_the_vetted_wrong_answers_are_all_translated():
    from core.lang.i18n import tr

    for a in train.BAD_ACTIONS:
        assert CJK.search(tr(a, "zh")) and not train.SAFE_SOUNDING_ZH.search(tr(a, "zh")) and not train.GOOD_ZH.search(tr(a, "zh")), a


def test_a_chinese_challenge_uses_chinese_messages():
    items = challenge.get(challenge.create(lang="zh"))
    assert len(items) == 6 and all(CJK.search(i["text"]) for i in items) and any(i["is_scam"] for i in items) and any(not i["is_scam"] for i in items)
    assert not any(CJK.search(i["text"]) for i in challenge.get(challenge.create()))


def test_the_map_and_levels_in_chinese():
    zh = model.resilience_map("zh")["tactics"]
    assert zh[0]["label"] == "催你马上行动" and {t["level_text"] for t in zh} == {"还没练过"}
    model.record_result("urgency-pressure", "incorrect")
    assert model.resilience_map("zh")["tactics"][0]["level_text"] == "需加强" and model.resilience_map("zh-Hant")["tactics"][0]["level_text"] == "需加強"
    assert model.resilience_map()["tactics"][0]["level_text"] == "weak" and model.resilience_map("en")["tactics"][0]["label"] == "Rushing you"


def test_game_titles_and_badges_in_chinese():
    assert state.title_for(1) == "Rookie" and state.title_for(1, "zh") == "新手" and state.title_for(7, "zh-Hant") == "騙局克星"
    assert state.badge_text("first-round") == ("First steps", "Finish your first round") and state.badge_text("first-round", "zh") == ("迈出第一步", "完成你的第一局")
    assert state.badge_text("boss:urgency-pressure") == ("Master of “Rushing you”", "Beat the rushing you boss")
    assert state.badge_text("boss:urgency-pressure", "zh") == ("“催你马上行动”大师", "击败“催你马上行动”关主")
    assert state.badge_text("boss:urgency-pressure", "zh-Hant")[1] == "擊敗“催你馬上行動”關主"
    assert all(state.badge_text(b, "zh")[0] != state.badge_text(b)[0] for b in state.BADGES)  # every badge has a Chinese name


def test_the_games_explanation_is_in_the_readers_language():
    en = gp.Item("g1", "Pay now or else", "scam", ["urgency-pressure"], "A deadline is pressure.", "Pay now", "Do not pay.")
    assert engine._explain(en, "en") == ("A deadline is pressure.", "Do not pay.")
    tell, action = engine._explain(en, "zh")
    assert CJK.search(tell) and CJK.search(action)
    zh = gp.Item("g2", "立即付款", "scam", ["urgency-pressure"], "催你付款就是施压。", "立即付款", "不要付款。")
    assert engine._explain(zh, "zh") == ("催你付款就是施压。", "不要付款。") and engine._explain(zh, "zh-Hant") == ("催你付款就是施壓。", "不要付款。")
    safe = gp.Item("g3", "明天见", "safe", [], gp.SAFE_TELL, "", "")
    assert engine._explain(safe, "zh")[0].startswith("这条消息没有要钱") and engine._explain(safe, "zh")[1] == ""


def test_a_chinese_game_round_gets_chinese_text_and_names():
    r = engine.start("boss", "urgency-pressure", lang="zh")
    pub = engine.public(r, "zh")
    assert pub["trick_label"] == "催你马上行动" and all(CJK.search(i["text"]) for i in pub["items"]) and engine.public(r)["trick_label"] == "Rushing you"
    first = r.items[0]
    res = engine.answer(r, first.id, "unsure", lang="zh")
    assert all(CJK.search(t) for t in res["tricks"]) and (CJK.search(res["tell"]) or first.truth != "scam")
    ov = engine.overview("zh")
    assert ov["title"] == "新手" and ov["tricks"][0]["label"] == "催你马上行动" and CJK.search(ov["tricks"][0]["blurb"]) and engine.overview()["title"] == "Rookie"
