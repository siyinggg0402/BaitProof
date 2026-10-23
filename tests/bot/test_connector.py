"""The Telegram connector, driven with plain fakes (no network, and no `telegram` import except where a test says so)."""
import asyncio
from types import SimpleNamespace

import pytest

from bot import handlers, telegram_bot
from bot.handlers import Button, Reply
from tests.bot.helpers import datas, play, right

EXPIRED = "That quiz expired. Send /quiz to start a new one."


REAL_RENDER = telegram_bot.render


def fake_render(reply: Reply) -> dict:
    return {"keyboard": [[b.data for b in row] for row in reply.buttons], "preview": reply.preview}


@pytest.fixture(autouse=True)
def plain_render(monkeypatch):
    monkeypatch.setattr(telegram_bot, "render", fake_render)


class FakeQuery:
    def __init__(self, data, fail_edit=False, fail_answer=False):
        self.data, self.fail_edit, self.fail_answer = data, fail_edit, fail_answer
        self.answers, self.edits = [], []

    async def answer(self, text=None, **kw):
        if self.fail_answer:
            raise RuntimeError("Query is too old")
        self.answers.append(text)

    async def edit_message_text(self, text, **kw):
        if self.fail_edit:
            raise RuntimeError("Message can't be edited")
        self.edits.append((text, kw))


class Outbox:
    """Where new messages go: stands in for bot.send_message / message.reply_text."""
    def __init__(self):
        self.sent = []

    async def __call__(self, text, **kw):
        self.sent.append((text, kw))


def tap(chat_id, data, **query_options):
    query, out = FakeQuery(data, **query_options), Outbox()
    asyncio.run(telegram_bot.handle_button(query, chat_id, out, None))
    return query, out


def test_a_tap_is_answered_the_question_is_edited_and_the_next_one_is_sent():
    q = handlers.on_quiz(400)[0]
    query, out = tap(400, right(400, q))
    assert query.answers == [None]  # the spinner stops, with no pop-up text
    assert len(query.edits) == 1 and "✅ Nice catch!" in query.edits[0][0] and query.edits[0][1] == {"keyboard": [], "preview": False}  # no buttons: the old ones go
    assert len(out.sent) == 1 and "2 of 5" in out.sent[0][0] and len(out.sent[0][1]["keyboard"][0]) == 3 and out.sent[0][1]["preview"] is False


def test_the_last_tap_sends_the_summary_with_its_two_buttons():
    q = handlers.on_quiz(401)[0]
    for _ in range(4):
        _, out = tap(401, right(401, q))
        q = Reply(out.sent[0][0], [[Button("x", d) for d in out.sent[0][1]["keyboard"][0]]])  # the next question, as the chat received it
    query, out = tap(401, right(401, q))
    assert len(query.edits) == 1 and "Flawless" in out.sent[0][0] and out.sent[0][1]["keyboard"] == [["qn"], ["ch"]]


def test_a_stale_or_foreign_tap_gets_a_polite_new_message():
    q = handlers.on_quiz(402)[0]
    query, out = tap(403, datas(q)[0])  # another chat
    assert query.answers == [None] and query.edits == [] and [t for t, _ in out.sent] == [EXPIRED]


def test_a_malformed_tap_gets_a_pop_up_and_nothing_else():
    handlers.on_quiz(404)
    query, out = tap(404, "q:zzz")
    assert query.answers == ["Sorry, I didn't understand that button."] and query.edits == [] and out.sent == []
    query, out = tap(404, None)
    assert query.answers == ["Sorry, I didn't understand that button."] and out.sent == []


def test_a_double_tap_shows_a_pop_up_and_does_not_repeat_the_message():
    q = handlers.on_quiz(405)[0]
    data = right(405, q)
    tap(405, data)
    query, out = tap(405, data)
    assert query.answers == ["Already answered."] and query.edits == [] and out.sent == []


def test_when_the_message_cannot_be_edited_the_feedback_is_sent_as_a_new_message():
    q = handlers.on_quiz(406)[0]
    query, out = tap(406, right(406, q), fail_edit=True)
    assert query.edits == [] and len(out.sent) == 2 and "✅ Nice catch!" in out.sent[0][0] and "2 of 5" in out.sent[1][0]


def test_an_expired_callback_query_does_not_stop_the_reply():
    q = handlers.on_quiz(407)[0]
    query, out = tap(407, right(407, q), fail_answer=True)
    assert len(query.edits) == 1 and len(out.sent) == 1


def test_a_crash_in_the_handler_is_caught_and_answered(monkeypatch):
    def boom(*a):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(handlers, "on_callback", boom)
    query, out = tap(408, "qn")
    assert query.answers == ["Something went wrong. Please try again."] and out.sent == []


def test_the_new_quiz_and_challenge_buttons_send_new_messages(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", "https://baitproof.example")
    query, out = tap(409, "qn")
    assert query.edits == [] and len(out.sent) == 1 and "1 of 5" in out.sent[0][0]
    query, out = tap(409, "ch")
    assert query.edits == [] and len(out.sent) == 2 and "https://baitproof.example/challenge/" in out.sent[1][0] and out.sent[1][1]["preview"] is True


# ---------------------------------------------------------------- the PTB handler functions
class FakeMessage:
    def __init__(self, text=""):
        self.text, self.replies = text, []

    async def reply_text(self, text, **kw):
        self.replies.append((text, kw))


def update(chat_id, text="", language_code=None, callback_query=None):
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_user=SimpleNamespace(language_code=language_code),
                           message=FakeMessage(text), callback_query=callback_query)


def test_commands_reply_with_the_handlers_text_and_buttons(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", "https://baitproof.example")
    u = update(410, language_code="zh-hans")
    asyncio.run(telegram_bot.quiz_cmd(u, SimpleNamespace(args=[])))
    text, kw = u.message.replies[0]
    assert "快速测验" in text and len(kw["keyboard"][0]) == 3
    u = update(410)
    asyncio.run(telegram_bot.quiz_cmd(u, SimpleNamespace(args=["daily"])))
    assert "Daily Challenge" in u.message.replies[0][0] or "每日挑战" in u.message.replies[0][0]
    u = update(411)
    asyncio.run(telegram_bot.challenge_cmd(u, SimpleNamespace(args=[])))
    assert len(u.message.replies) == 2 and "https://baitproof.example/challenge/" in u.message.replies[1][0] and u.message.replies[1][1]["preview"] is True
    u = update(412, "Buy 4 gift cards and send me the numbers please.")
    asyncio.run(telegram_bot.text(u, SimpleNamespace(args=[])))
    assert u.message.replies[0][0].startswith("🚨") and u.message.replies[0][1]["keyboard"] == [["qn"], ["ch"]]
    u = update(413)
    asyncio.run(telegram_bot.start(u, SimpleNamespace(args=[])))
    assert "/quiz" in u.message.replies[0][0] and "/challenge" in u.message.replies[0][0]


def test_the_button_function_sends_new_messages_through_the_bot():
    q = handlers.on_quiz(414)[0]
    sent = []

    async def send_message(chat_id, text, **kw):
        sent.append((chat_id, text, kw))

    query = FakeQuery(right(414, q))
    u = update(414, callback_query=query)
    asyncio.run(telegram_bot.button(u, SimpleNamespace(bot=SimpleNamespace(send_message=send_message))))
    assert query.answers == [None] and len(query.edits) == 1 and sent[0][0] == 414 and "2 of 5" in sent[0][1]


def test_the_button_function_still_answers_when_there_is_no_chat():
    query = FakeQuery("qn")
    u = SimpleNamespace(callback_query=query, effective_chat=None, effective_user=None)
    asyncio.run(telegram_bot.button(u, SimpleNamespace(bot=None)))
    assert query.answers == [None]
    asyncio.run(telegram_bot.button(SimpleNamespace(callback_query=None, effective_chat=None, effective_user=None), SimpleNamespace(bot=None)))  # and nothing to do without a query


# ---------------------------------------------------------------- with the real telegram package, still offline
def test_render_builds_a_real_inline_keyboard_and_switches_link_previews_off():
    pytest.importorskip("telegram")
    from telegram import InlineKeyboardMarkup

    render = REAL_RENDER

    q = handlers.on_quiz(420)[0]
    kw = render(q)
    assert isinstance(kw["reply_markup"], InlineKeyboardMarkup) and kw["link_preview_options"].is_disabled
    row = kw["reply_markup"].inline_keyboard[0]
    assert [b.text for b in row] == ["🚨 Scam", "✅ Looks fine", "🤔 Check first"] and [b.callback_data for b in row] == datas(q)
    summary = play(420, q)[-1].replies[1]
    assert [[b.callback_data for b in r] for r in render(summary)["reply_markup"].inline_keyboard] == [["qn"], ["ch"]]
    plain = render(Reply("hello"))
    assert "reply_markup" not in plain and plain["link_preview_options"].is_disabled
    assert "link_preview_options" not in render(Reply("see https://example.com", preview=True))


def test_the_bot_handles_updates_concurrently(monkeypatch):
    from telegram.ext import Application

    started = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:dummy-token-for-a-test")
    monkeypatch.setattr(Application, "run_polling", lambda self, *a, **k: started.append(self))
    telegram_bot.main()
    assert started[0].update_processor.max_concurrent_updates == telegram_bot.MAX_CONCURRENT_UPDATES > 1


def test_main_registers_the_new_commands_and_the_button_handler(monkeypatch):
    pytest.importorskip("telegram")
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler

    started = []
    monkeypatch.setattr(Application, "run_polling", lambda self, *a, **k: started.append(self))  # never talk to Telegram
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:NOT-A-REAL-TOKEN")
    telegram_bot.main()
    handlers_ = [h for group in started[0].handlers.values() for h in group]
    commands = {c for h in handlers_ if isinstance(h, CommandHandler) for c in h.commands}
    assert commands >= {"start", "help", "score", "link", "unlink", "history", "lang", "quiz", "play", "challenge"}
    assert sum(isinstance(h, CallbackQueryHandler) for h in handlers_) == 1 and sum(isinstance(h, MessageHandler) for h in handlers_) == 3  # text, pictures, voice


def test_a_forwarded_message_names_who_it_came_from():
    from types import SimpleNamespace as NS
    assert telegram_bot.forwarded_from(NS(forward_origin=None)) == "" and telegram_bot.forwarded_from(NS()) == ""
    assert telegram_bot.forwarded_from(NS(forward_origin=NS(sender_user=NS(first_name="Mei", last_name="Tan")))) == "Mei Tan"
    assert telegram_bot.forwarded_from(NS(forward_origin=NS(sender_user=None, sender_user_name="Hidden Name", chat=None, sender_chat=None))) == "Hidden Name"
    assert telegram_bot.forwarded_from(NS(forward_origin=NS(chat=NS(title="Daily Deals"), sender_user=None))) == "Daily Deals"
    assert telegram_bot.forwarded_from(NS(forward_origin=NS(sender_chat=NS(title="Group X"), sender_user=None, chat=None))) == "Group X"
