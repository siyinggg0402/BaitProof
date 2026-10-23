"""With concurrent updates, two chats handled at the same moment must never see each other's profile, records or quiz."""
from concurrent.futures import ThreadPoolExecutor
import re
import threading
import time

from bot import handlers
from bot.handlers import on_callback, on_challenge
from core.lang.text import CJK
from core.pipelines import challenge
from core.storage import model
from core.storage import links
from core.storage import db, history


def test_bot_check_and_score(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    out = handlers.on_text(111, "Buy 4 gift cards and send me the numbers please.")
    assert out.startswith("🚨") and "giveaway" in out and "Added to your practice" in out
    assert "score" in handlers.on_score(111).lower()
    # a different chat has its own, untouched profile
    assert "Weakest" not in handlers.on_score(222) and model.baitproof_score() == 0
    assert handlers.on_text(111, "   ") == "Send me the message you want checked. 🐟"


def test_nudge_only_when_due(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert handlers.nudge_text(5) is None
    handlers.bind_chat(5)
    model.record_result("urgency-pressure", "incorrect")  # incorrect => due immediately
    assert "due" in handlers.nudge_text(5)


def test_bot_answers_in_the_users_language(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    scam = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。"
    zh = handlers.on_text(901, scam)  # no preference: the message's own language
    assert zh.startswith("🚨") and "骗局" in zh.splitlines()[0] and "破绽：" in zh and "该怎么做：" in zh and "已加入你的练习" in zh
    en = handlers.on_text(902, scam, lang_hint="en")  # Telegram says this user reads English
    assert "SCAM" in en.splitlines()[0] and "The giveaway:" in en and "破绽" not in en
    hant = handlers.on_text(903, scam, lang_hint="zh-hant")
    assert "騙局" in hant.splitlines()[0] and "破綻：" in hant


def test_lang_command_is_remembered_per_chat(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert "English" in handlers.on_lang(910, "en")
    assert handlers.on_lang(911, "zh") == "已切换为简体中文。" and handlers.on_lang(912, "zh-Hant") == "已切換為繁體中文。"
    assert "/lang" in handlers.on_lang(913, "klingon")
    scam = "Buy 4 gift cards and send me the numbers please."
    assert "骗局" in handlers.on_text(911, scam).splitlines()[0]            # chose Simplified Chinese: even an English message is explained in Chinese
    assert "SCAM" in handlers.on_text(910, scam).splitlines()[0]
    assert handlers.on_start(911).startswith("你好！我是 Finn") and handlers.on_start(910).startswith("Hi! I'm Finn")
    assert "分数" in handlers.on_score(911) and "score" in handlers.on_score(910).lower()
    assert "最近的检查" in handlers.on_history(911) and "Your latest checks" in handlers.on_history(910)


def test_start_with_a_code_links_and_start_alone_welcomes():
    assert handlers.on_start(1, "").startswith("Hi! I'm Finn") and "/link CODE" in handlers.WELCOME
    code = links.new_code("local")
    assert handlers.on_start(1, code).startswith("✅ Linked") and links.profile_for_chat(1) == "local"


def test_link_command_messages_are_helpful():
    assert "6-character code" in handlers.on_link(2, "")
    assert "didn't work" in handlers.on_link(2, "ABCDEF")


def test_guessing_codes_is_limited():
    handlers.ATTEMPTS.clear()
    replies = [handlers.on_link(3, "ABCDEF") for _ in range(7)]
    assert "didn't work" in replies[4] and "Too many tries" in replies[5] and "Too many tries" in replies[6]
    # even a correct code is refused while locked out, so brute force gains nothing
    assert "Too many tries" in handlers.on_link(3, links.new_code("local"))


def test_unlink_and_history_messages():
    handlers.ATTEMPTS.clear()
    handlers.on_link(4, links.new_code("local"))
    assert "Disconnected" in handlers.on_unlink(4) and "wasn't linked" in handlers.on_unlink(4)
    assert "No checks yet" in handlers.on_history(4)


def test_linked_replies_point_to_the_records_page_when_a_url_is_set(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", "https://baitproof.example")
    handlers.ATTEMPTS.clear()
    assert "https://baitproof.example/records" in handlers.on_link(5, links.new_code("local"))
    assert "🗂 Saved to your records: https://baitproof.example/records" in handlers.on_text(5, "Buy 4 gift cards and send me the codes now.")


def test_many_chats_checked_at_once_each_keep_their_own_records(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    real = handlers.check_message
    seen: dict[int, str] = {}
    barrier = threading.Barrier(6, timeout=10)  # all six are inside the (slow) check at the same time

    def slow_check(text, *a, **k):
        chat = int(text.split("#")[1])
        seen[chat] = db.db_path()  # the file this chat's profile points at, while the others are mid-check
        barrier.wait()
        time.sleep(0.05)
        return real(text, *a, **k)

    monkeypatch.setattr(handlers, "check_message", slow_check)
    chats = list(range(7001, 7007))
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda c: handlers.on_text(c, f"Buy 4 gift cards and send me the numbers please. #{c}"), chats))
    assert len(set(seen.values())) == 6  # six different profile files
    for c in chats:
        handlers.bind_chat(c)
        rows = history.list_checks(10)
        assert len(rows) == 1 and f"#{c}" in (rows[0]["preview"] or "")  # only this chat's own check


def test_two_quizzes_at_once_do_not_cross(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    with ThreadPoolExecutor(2) as ex:
        a, b = list(ex.map(lambda c: handlers.on_quiz(c), (7101, 7102)))
    qa, qb = a[0], b[0]
    assert qa.buttons and qb.buttons
    assert qa.buttons[0][0].data.split(":")[1] != qb.buttons[0][0].data.split(":")[1]  # two different rounds
    res = handlers.on_callback(7102, qa.buttons[0][0].data)  # chat 7102 taps a button from chat 7101's quiz
    assert res.toast or "expired" in " ".join(r.text for r in res.replies)  # refused, graded nothing


URL = "https://baitproof.example"


def count_challenges() -> int:
    with db.connect(shared=True) as c:
        return c.execute("SELECT COUNT(*) AS n FROM challenges").fetchone()["n"]


def test_challenge_gives_a_message_to_forward_with_a_link_that_opens_a_real_challenge(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL + "/")  # a trailing slash is fine
    intro, forward = on_challenge(300)
    assert "Forward the next message" in intro.text and not intro.buttons and not intro.preview
    assert forward.text.startswith("Can you spot the scam?") and "2 minutes" in forward.text and "no account" in forward.text
    assert forward.preview and not forward.buttons and len(forward.text) < 400  # short, and the site's card may unfurl
    cid = re.search(rf"{re.escape(URL)}/challenge/([0-9a-f]{{8}})(?!\w)", forward.text).group(1)
    assert forward.text.count("http") == 1 and f"{URL}//" not in forward.text
    items = challenge.get(cid)  # what the web page loads
    assert items and len(items) == 6 and {i["is_scam"] for i in items} == {True, False}
    assert count_challenges() == 1


def test_each_call_makes_a_new_challenge(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    first, second = on_challenge(301)[1].text, on_challenge(301)[1].text
    assert first != second and count_challenges() == 2


def test_without_baitproof_url_it_says_the_operator_must_set_it_and_makes_nothing():
    reply = on_challenge(302)
    assert len(reply) == 1 and "BAITPROOF_URL" in reply[0].text and "http" not in reply[0].text and reply[0].buttons == []
    assert count_challenges() == 0
    handlers.on_lang(303, "zh")
    zh = on_challenge(303)[0].text
    assert "BAITPROOF_URL" in zh and CJK.search(zh) and "Please ask" not in zh
    handlers.on_lang(304, "zh-Hant")
    assert "運營" in on_challenge(304)[0].text
    assert count_challenges() == 0 and handlers.RATE == {}  # a missing setting does not use up the chat's allowance


def test_challenge_is_in_the_chats_language(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")  # each chat has its own settings
    handlers.on_lang(305, "zh")
    intro, forward = on_challenge(305)
    assert "转发" in intro.text and forward.text.startswith("你能识破骗局吗？") and f"{URL}/challenge/" in forward.text and "2分钟" in forward.text
    cid = re.search(r"/challenge/([0-9a-f]{8})", forward.text).group(1)
    assert all(CJK.search(i["text"]) for i in challenge.get(cid))  # the messages are Chinese too
    handlers.on_lang(306, "zh-Hant")
    assert on_challenge(306)[1].text.startswith("你能識破騙局嗎？")
    assert on_challenge(307, "zh-hans")[1].text.startswith("你能识破骗局吗？")  # Telegram's own language, when the chat has not chosen


def test_challenges_are_rate_limited_per_chat_and_nothing_is_created_when_refused(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    for _ in range(5):
        assert len(on_challenge(308)) == 2
    refused = on_challenge(308)
    assert len(refused) == 1 and refused[0].text == "You've made a few challenges already. Please wait a bit before making another one." and "http" not in refused[0].text
    assert count_challenges() == 5
    assert len(on_challenge(309)) == 2  # another chat is fine
    handlers.on_lang(308, "zh")
    assert on_challenge(308)[0].text.startswith("你已经创建了好几个挑战了")


def test_the_challenge_button_works_like_the_command(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    res = on_callback(310, handlers.CHALLENGE)
    assert res.toast == "" and len(res.replies) == 2 and f"{URL}/challenge/" in res.replies[1].text and not any(r.edit for r in res.replies)
    assert count_challenges() == 1


def test_a_linked_chats_own_scams_can_appear_in_its_challenge(monkeypatch):
    """The challenge is built from the chat's profile like the website's button: a scam it forwarded earlier may be one of the six."""
    monkeypatch.setenv("BAITPROOF_URL", URL)
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_check(311, "Buy 4 gift cards and send me the numbers please.")
    cid = re.search(r"/challenge/([0-9a-f]{8})", on_challenge(311)[1].text).group(1)
    assert any("gift cards" in i["text"] for i in challenge.get(cid))
    assert links.current_profile() != "local"
