import ast
import inspect
import re
import string
from concurrent.futures import ThreadPoolExecutor

import pytest

from bot import handlers
from bot.handlers import on_callback, on_check, on_quiz
from core.game import engine
from core.game import state as game_state
from core.lang import i18n
from core.storage import db, links, model
from tests.bot.helpers import datas, labels, play, right, round_of, tap, wrong

ANSWER_DATA = re.compile(r"q:[0-9a-f]{12}:[0-9]:[sfu]")
EXPIRED = "That quiz expired. Send /quiz to start a new one."
MISUNDERSTOOD = "Sorry, I didn't understand that button."


# ---------------------------------------------------------------- starting
def test_a_quiz_starts_with_one_question_and_three_buttons_that_carry_no_answer():
    replies = on_quiz(10)
    assert len(replies) == 1
    q = replies[0]
    assert "Quick quiz" in q.text and "1 of 5" in q.text and "What is this message?" in q.text and not q.edit
    assert len(q.buttons) == 1 and labels(q) == ["🚨 Scam", "✅ Looks fine", "🤔 Check first"]
    r, i = round_of(10, datas(q)[0])
    item = r.items[i]
    assert f"“{item.text}”".replace("​", "") in q.text.replace("​", "")
    assert r.owner == links.current_profile() and len(r.items) == 5
    for d in datas(q):
        assert ANSWER_DATA.fullmatch(d) and len(d.encode()) <= 64
        assert item.id not in d and item.truth not in d  # what the buttons say is only which button it is
    assert len({d[:-1] for d in datas(q)}) == 1  # the three differ only in the last letter, the same for every question
    for hidden in (item.tell, item.action):
        assert not hidden or hidden not in q.text  # the giveaway is not shown before the answer


def test_play_and_quiz_are_the_same_command_and_the_round_is_five_messages_with_some_that_are_not_scams():
    for chat in range(50, 56):
        r, _ = round_of(chat, datas(on_quiz(chat)[0])[0])
        assert len(r.items) == handlers.QUIZ_LEN == 5
        assert sum(i.truth != "scam" for i in r.items) >= 2  # "scam" is not always the right answer


def test_quiz_uses_the_games_rush_mode_and_daily_uses_the_daily_challenge(monkeypatch):
    calls, real = [], engine.start

    def spy(mode, trick="", items=None, owner="", lang="en"):
        calls.append((mode, owner, lang))
        return real(mode, trick, items, owner, lang)

    monkeypatch.setattr(engine, "start", spy)
    on_quiz(60)
    on_quiz(60, "daily")
    on_quiz(60, "something else")
    handlers.on_lang(61, "zh-Hant")
    on_quiz(61)
    handlers.bind_chat(60)
    assert calls == [("rush", links.current_profile(), "en"), ("daily", links.current_profile(), "en"), ("rush", links.current_profile(), "en"), ("rush", "local", "zh-Hant")]


def test_each_chat_has_one_quiz_and_starting_again_replaces_it():
    first = on_quiz(70)[0]
    second = on_quiz(70)[0]
    assert datas(first)[0][:15] != datas(second)[0][:15]  # a different round
    res = on_callback(70, datas(first)[0])  # the old question's button
    assert res.replies[0].text == EXPIRED and not res.replies[0].edit
    assert on_callback(70, right(70, second)).replies[0].edit  # the new one works


# ---------------------------------------------------------------- playing
def test_a_flawless_round_gives_feedback_each_time_then_a_summary_with_xp_level_streak_and_badges():
    q = on_quiz(80)[0]
    results = play(80, q)
    assert len(results) == 5
    for n, res in enumerate(results):
        fb = res.replies[0]
        assert fb.edit and fb.buttons == [] and f"{n + 1} of 5" in fb.text and "✅ Nice catch!" in fb.text and "+" in fb.text and "XP" in fb.text
        assert "The giveaway:" in fb.text or "Why it's fine:" in fb.text
        if n < 4:
            nxt = results[n].replies[1]
            assert f"{n + 2} of 5" in nxt.text and not nxt.edit and len(nxt.buttons[0]) == 3 and len(results[n].replies) == 2
    scams = [r for r in results if "This one is a scam." in r.replies[0].text]
    assert scams and all("What to do:" in r.replies[0].text for r in scams)  # a scam says what to do instead
    summary = results[-1].replies[1]
    t = summary.text
    assert t.startswith("🌟 Flawless round!") and "5/5 right" in t and "+100 XP" in t  # 70 for five in a row, +10 finished, +20 flawless
    assert "Level 2 · Spotter" in t and "Level up! You're now level 2: Spotter" in t and "1-day streak" in t
    assert "First steps" in t and "Flawless" in t and "Baitproof score" in t
    assert labels(summary) == ["🎮 Play again", "👪 Challenge my family"] and datas(summary) == ["qn", "ch"]
    assert len(summary.text) < 4096
    assert handlers._ACTIVE == {}  # the round is over
    assert game_state.get()["xp"] == 100 and game_state.get()["rounds"] == 1


def test_wrong_answers_show_the_tell_and_the_summary_is_honest():
    q = on_quiz(81)[0]
    results = play(81, q, wrong)
    shown = {"scam": [], "safe": [], "unsure": []}
    for res in results:
        fb = res.replies[0].text
        truth = next(k for k, v in (("scam", "This one is a scam."), ("safe", "This one is genuine."), ("unsure", "worth checking first")) if v in fb)
        shown[truth].append(fb)
    assert all("💡 Here's the tell" in f and "The giveaway:" in f and "What to do:" in f for f in shown["scam"])
    assert all("💡 That one was genuine" in f and "Why it's fine:" in f and "What to do:" not in f for f in shown["safe"])
    t = results[-1].replies[1].text
    assert t.startswith("🎉 Round complete!") and "0/5 right" in t and "+10 XP" in t and "Flawless" not in t and "Level up" not in t


def test_being_careful_earns_partial_credit_unless_check_first_was_the_right_answer():
    q = on_quiz(82)[0]
    r, i = round_of(82, datas(q)[0])
    fb = on_callback(82, tap(q, "unsure")).replies[0].text
    assert ("✅ Nice catch!" in fb) if r.items[i].truth == "unsure" else ("🟡 Careful is good! +5 XP" in fb)


def test_progress_goes_to_the_chats_own_profile_and_the_trick_model(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    play(90, on_quiz(90)[0])
    handlers.bind_chat(90)
    assert game_state.get()["xp"] == 100 and model.baitproof_score() > 0
    assert sum(m["success"] for m in model.all_mastery()) > 0  # the same model Practice and the website's game feed
    handlers.bind_chat(91)
    assert game_state.get()["xp"] == 0 and model.baitproof_score() == 0


def test_a_linked_chat_plays_into_the_web_profile(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    web_profile = "ab" * 16
    assert handlers.on_link(92, links.new_code(web_profile)).startswith("✅ Linked")
    q = on_quiz(92)[0]
    r, _ = round_of(92, datas(q)[0])
    assert r.owner == web_profile
    play(92, q)
    db.set_profile(web_profile)
    assert game_state.get()["xp"] == 100 and game_state.get()["rounds"] == 1


def test_play_again_and_quick_quiz_buttons_start_a_fresh_round():
    summary = play(93, on_quiz(93)[0])[-1].replies[1]
    res = on_callback(93, datas(summary)[0])
    assert res.toast == "" and len(res.replies) == 1 and "1 of 5" in res.replies[0].text
    assert len(handlers._ACTIVE) == 1
    assert on_callback(93, right(93, res.replies[0])).replies[0].edit


# ---------------------------------------------------------------- refusing bad buttons
@pytest.mark.parametrize("data", [None, "", "q", "q:", "qn ", "ch\n", "QN", "x" * 500, "q:" + "a" * 12 + ":0:x", "q:" + "A" * 12 + ":0:s", "q:" + "a" * 11 + ":0:s",
                                  "q:" + "a" * 12 + ":123:s", "q:" + "a" * 12 + ":-1:s", "q:" + "a" * 12 + ":٣:s", "q:" + "a" * 12 + ":0:s:more", "{}", "../../etc/passwd"])
def test_a_malformed_button_is_refused_politely_and_grades_nothing(data):
    q = on_quiz(100)[0]
    res = on_callback(100, data)
    assert res.replies == [] and res.toast == MISUNDERSTOOD
    r, _ = round_of(100, datas(q)[0])
    assert r.answered == {} and game_state.get()["xp"] == 0


def test_a_button_for_a_question_that_does_not_exist_or_is_not_next_grades_nothing():
    q = on_quiz(101)[0]
    rid = datas(q)[0].split(":")[1]
    for i in (5, 99, 3):
        assert on_callback(101, f"q:{rid}:{i}:s") == handlers.CallbackResult(toast=MISUNDERSTOOD)
    r, _ = round_of(101, datas(q)[0])
    assert r.answered == {}


def test_another_chat_cannot_answer_my_quiz():
    mine = on_quiz(110)[0]
    stolen = right(110, mine)
    for chat in (111, 112):
        if chat == 112:
            on_quiz(112)  # a chat with a quiz of its own gets the same answer
        res = on_callback(chat, stolen)
        assert [m.text for m in res.replies] == [EXPIRED] and res.toast == ""
    r, _ = round_of(110, datas(mine)[0])
    assert r.answered == {}
    assert on_callback(110, stolen).replies[0].edit  # the owner still can


def test_a_round_that_belongs_to_another_profile_is_refused_even_if_the_chat_points_at_it(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    mine = on_quiz(120)[0]
    rid = datas(mine)[0].split(":")[1]
    handlers._ACTIVE[121] = handlers._Quiz(rid, "en")  # forged: chat 121 believes it is playing chat 120's round
    res = on_callback(121, f"q:{rid}:0:s")
    assert [m.text for m in res.replies] == [EXPIRED]
    r, _ = round_of(120, datas(mine)[0])
    assert r.answered == {} and 121 not in handlers._ACTIVE


def test_a_quiz_the_engine_has_forgotten_or_that_timed_out_says_so_politely():
    q = on_quiz(130)[0]
    engine._rounds.clear()  # the bot was restarted
    res = on_callback(130, datas(q)[0])
    assert [m.text for m in res.replies] == [EXPIRED]
    q = on_quiz(130)[0]
    r, _ = round_of(130, datas(q)[0])
    r.created -= engine.TTL + 1
    assert [m.text for m in on_callback(130, datas(q)[0]).replies] == [EXPIRED]
    assert 130 not in handlers._ACTIVE
    assert "1 of 5" in on_quiz(130)[0].text  # and /quiz starts over


def test_a_double_tap_does_not_score_twice():
    q = on_quiz(140)[0]
    data = right(140, q)
    first = on_callback(140, data)
    xp = game_state.get()["xp"]
    again = on_callback(140, data)
    assert first.replies and again.replies == [] and again.toast == "Already answered." and game_state.get()["xp"] == xp


def test_a_tap_after_the_round_finished_is_expired():
    q = on_quiz(141)[0]
    last = play(141, q)[-1]
    assert on_callback(141, datas(q)[0]).replies[0].text == EXPIRED and last.replies[1].text.startswith("🌟")


def test_an_engine_error_becomes_a_polite_toast(monkeypatch):
    q = on_quiz(142)[0]

    def boom(*a, **k):
        raise engine.GameError("Already answered.")

    monkeypatch.setattr(engine, "answer", boom)
    assert on_callback(142, datas(q)[0]) == handlers.CallbackResult(toast="Already answered.")
    monkeypatch.setattr(engine, "answer", lambda *a, **k: 1 / 0)  # a bug must not escape either
    res = on_callback(142, datas(q)[0])
    assert res.replies == [] and res.toast == "Something went wrong. Please try again."


# ---------------------------------------------------------------- the daily challenge
def ids(chat: int, question) -> list[str]:
    return [i.id for i in round_of(chat, datas(question)[0])[0].items]


def test_daily_is_the_same_messages_for_everyone_in_a_language_and_pays_its_bonus_once(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    a, b = on_quiz(150, "daily")[0], on_quiz(151, "daily")[0]
    assert "Daily Challenge" in a.text and "1 of 6" in a.text and a.text == b.text
    assert ids(150, a) == ids(151, b) and len(ids(150, a)) == 6
    res = play(150, a)
    summary = res[-1].replies[1].text
    assert "Daily Challenge complete: +50 XP bonus!" in summary and "Daily challenger" in summary
    again = on_quiz(150, "Daily")[0]  # the same six again, for fun
    assert again.text.splitlines()[0] == a.text.splitlines()[0] and "Done today ✓. You can replay it for fun." in again.text
    assert "Daily Challenge complete" not in play(150, again)[-1].replies[1].text
    assert "Daily Challenge complete: +50 XP bonus!" in play(151, b)[-1].replies[1].text  # chat 151 has not played it yet


def test_daily_differs_by_language_but_is_stable_within_one(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_lang(160, "zh")
    handlers.on_lang(161, "zh")
    en = on_quiz(162, "daily")[0]
    zh1, zh2 = on_quiz(160, "daily")[0], on_quiz(161, "daily")[0]
    assert zh1.text == zh2.text and zh1.text != en.text
    assert "每日挑战" in zh1.text and re.search(r"[一-鿿]{6}", zh1.text.split("\n", 2)[2])  # the message itself is Chinese
    assert not re.search(r"[一-鿿]", en.text)


# ---------------------------------------------------------------- other languages
def test_the_chinese_path_is_chinese_from_the_question_to_the_summary():
    assert handlers.on_lang(170, "zh") == "已切换为简体中文。"
    q = on_quiz(170)[0]
    assert "快速测验" in q.text and "第1题，共5题" in q.text and "这条消息是什么？" in q.text and "先核实" in q.text
    assert labels(q) == ["🚨 骗局", "✅ 看起来没问题", "🤔 先核实"]
    results = play(170, q, wrong)
    fb = [r.replies[0].text for r in results]
    assert any("破绽：" in f and "该怎么做：" in f and "这条是骗局。" in f for f in fb)
    assert not any(re.search(r"The giveaway|What to do|Nice catch|Here's the tell", f) for f in fb)
    summary = results[-1].replies[1]
    assert "这一局完成了" in summary.text and "答对" in summary.text and "新手" in summary.text and "Level" not in summary.text and "XP" in summary.text
    assert labels(summary) == ["🎮 再玩一局", "👪 挑战我的家人"]
    zh_expired = on_callback(170, datas(q)[0]).replies[0].text
    assert zh_expired == "这个测验已过期。发送 /quiz 开始新的一局。"
    assert on_callback(170, "nonsense").toast == "抱歉，我不明白这个按钮。"


def test_traditional_chinese_is_derived():
    handlers.on_lang(171, "zh-Hant")
    q = on_quiz(171)[0]
    assert labels(q) == ["🚨 騙局", "✅ 看起來沒問題", "🤔 先核實"] and "快速測驗" in q.text
    summary = play(171, q)[-1].replies[1].text
    assert "答對" in summary and "留心人" in summary and "升級啦" in summary


def test_telegrams_language_hint_is_used_until_the_chat_chooses():
    assert "快速测验" in on_quiz(172, "", "zh-hans")[0].text
    assert "Quick quiz" in on_quiz(173, "", "en")[0].text
    assert "Quick quiz" in on_quiz(174)[0].text  # nothing to go on: English


def test_a_round_keeps_the_language_it_started_in_and_the_next_one_follows_the_chat():
    handlers.on_lang(175, "zh")
    q = on_quiz(175)[0]
    handlers.on_lang(175, "en")
    assert "答对" in play(175, q)[-1].replies[1].text
    assert "Quick quiz" in on_quiz(175)[0].text


# ---------------------------------------------------------------- limits and safety
def test_starting_quizzes_is_rate_limited_per_chat(monkeypatch):
    monkeypatch.setattr(handlers, "QUIZ_LIMIT", (3, 600.0))
    for _ in range(3):
        assert "1 of 5" in on_quiz(180)[0].text
    kept = dict(handlers._ACTIVE)
    refused = on_quiz(180)
    assert [m.text for m in refused] == ["You're playing fast! Please wait a few minutes before starting another quiz."] and refused[0].buttons == []
    assert handlers._ACTIVE == kept  # the quiz in progress is untouched
    assert "1 of 5" in on_quiz(181)[0].text  # another chat is not affected
    assert on_callback(180, "qn").replies[0].text.startswith("You're playing fast")  # the Play again button is limited too
    handlers.on_lang(180, "zh")
    assert on_quiz(180)[0].text.startswith("你玩得太快啦")


def test_the_limiter_forgets_old_starts(monkeypatch):
    monkeypatch.setattr(handlers, "QUIZ_LIMIT", (1, 600.0))
    assert "1 of 5" in on_quiz(182)[0].text
    assert on_quiz(182)[0].text.startswith("You're playing fast")
    handlers.RATE["quiz:182"] = [t - 601 for t in handlers.RATE["quiz:182"]]
    assert "1 of 5" in on_quiz(182)[0].text


def test_links_in_quiz_messages_are_broken_so_they_cannot_be_tapped():
    inert = handlers._inert("Pay now: dhl-fee-pay.xyz/track or http://sf-express.top/a 谢谢")
    assert "dhl-fee-pay.xyz" not in inert and "http://" not in inert and "sf-express.top" not in inert
    assert inert.replace(handlers.ZWSP, "") == "Pay now: dhl-fee-pay.xyz/track or http://sf-express.top/a 谢谢"
    assert handlers._inert("No links here, price 3.5 today.") == "No links here, price 3.5 today."
    for chat in range(190, 196):  # and the real questions carry no clickable address
        q = on_quiz(chat)[0]
        assert not re.search(r"https?://|[a-z0-9-]\.(xyz|top|com|info|cc)\b", q.text, re.I)


def test_simultaneous_taps_on_the_same_button_score_once():
    q = on_quiz(196)[0]
    data = right(196, q)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: on_callback(196, data), range(8)))
    assert sum(bool(r.replies) for r in results) == 1 and sum(r.toast == "Already answered." for r in results) == 7
    r, _ = round_of(196, data)
    assert len(r.answered) == 1 and game_state.get()["xp"] == 10


def test_callback_data_never_exceeds_telegrams_limit():
    with pytest.raises(ValueError):
        handlers.Button("x", "q:" + "a" * 70)
    summary = play(197, on_quiz(197)[0])[-1].replies[1]
    for d in datas(summary) + [handlers.QUIZ_NEW, handlers.CHALLENGE]:
        assert len(d.encode()) <= 64


# ---------------------------------------------------------------- the check result, /help and the wording
def test_check_buttons_appear_only_when_a_trick_was_added_to_practice():
    scam = on_check(200, "Buy 4 gift cards and send me the numbers please.")
    assert len(scam) == 1 and "Added to your practice" in scam[0].text
    assert labels(scam[0]) == ["🎮 Quick quiz", "👪 Challenge my family"] and datas(scam[0]) == ["qn", "ch"]
    fine = on_check(201, "Hi, this is Dr. Lee's clinic. Reminder: your appointment is tomorrow at 10:30am. Please call the number on your appointment card to reschedule.")
    assert "Added to your practice" not in fine[0].text and fine[0].buttons == []
    assert on_check(202, "   ")[0].buttons == []
    # the tap on that button starts a quiz for the same chat
    assert "1 of 5" in on_callback(200, datas(scam[0])[0]).replies[0].text
    # on_text still gives just the text
    assert handlers.on_text(200, "Buy 4 gift cards and send me the numbers please.").startswith("🚨")


def test_check_buttons_are_in_the_users_language():
    handlers.on_lang(203, "zh")
    scam = on_check(203, "Buy 4 gift cards and send me the numbers please.")[0]
    assert labels(scam) == ["🎮 快速测验", "👪 挑战我的家人"]


def test_help_mentions_the_new_commands_in_every_language():
    assert "/quiz" in handlers.on_start(210) and "/challenge" in handlers.on_start(210)
    handlers.on_lang(211, "zh")
    zh = handlers.on_start(211)
    assert zh.startswith("你好！") and "/quiz" in zh and "/challenge" in zh and "每日挑战" in zh
    handlers.on_lang(212, "zh-Hant")
    assert "每日挑戰" in handlers.on_start(212)


def _literals(node: ast.AST) -> set[str]:
    """The English texts an expression can be: a string, or either branch of an `a if c else b`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _literals(node.body) | _literals(node.orelse)
    return set()


def _tr_texts() -> set[str]:
    """Every English text handlers.py passes to tr() (or defines as WELCOME), plus the three answer-button words that it looks up from a table."""
    found = {handlers.WELCOME, "Scam", "Looks fine", "Check first"}
    for node in ast.walk(ast.parse(inspect.getsource(handlers))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "tr" and node.args:
            found |= _literals(node.args[0])
    return found


def test_every_text_the_bot_says_has_a_chinese_version_with_the_same_placeholders():
    def fields(s: str) -> list[str]:
        return sorted(f for _, f, _, _ in string.Formatter().parse(s) if f)

    assert len(_tr_texts()) > 40  # the scan finds the texts
    missing = [t for t in _tr_texts() if t not in i18n.ZH]
    assert missing == []
    for en in _tr_texts():
        assert fields(i18n.ZH[en]) == fields(en), en
    # game wording reused from the website is not copied into the bot's dictionary
    from core.lang.i18n_bot import BOT_ZH
    from core.lang.i18n_ui import UI_ZH
    assert not set(BOT_ZH) & set(UI_ZH)
