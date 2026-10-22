"""The Telegram side of screenshots and voice notes, driven with plain fakes (no network; the real `telegram` package only to check which messages
the registered handlers pick up)."""
import asyncio
import datetime
import time
from types import SimpleNamespace

import pytest

from bot import handlers, telegram_bot
from core.inputs import audio, image
from core.lang.i18n import to_traditional
from core.obs import logger


@pytest.fixture(autouse=True)
def plain_render(monkeypatch):
    monkeypatch.setattr(telegram_bot, "render", lambda r: {"keyboard": [[b.data for b in row] for row in r.buttons], "preview": r.preview})


class FakeFile:
    def __init__(self, data):
        self.data = data

    async def download_as_bytearray(self):
        return bytearray(self.data)


class FakeMedia:
    """Stands in for a PhotoSize, Document, Voice or Audio: `fetched` counts downloads."""
    def __init__(self, data=b"BYTES", file_size=None, width=0, height=0, mime_type=None, duration=None, fail=None):
        self.data, self.file_size, self.width, self.height = data, len(data) if file_size is None else file_size, width, height
        self.mime_type, self.duration, self.fail, self.fetched = mime_type, duration, fail, 0

    async def get_file(self):
        self.fetched += 1
        if self.fail:
            raise self.fail
        return FakeFile(self.data)


class FakeBot:
    def __init__(self, fail=False):
        self.actions, self.fail = [], fail

    async def send_chat_action(self, chat_id, action):
        self.actions.append((chat_id, action))
        if self.fail:
            raise RuntimeError("flood control")


class FakeMessage:
    def __init__(self, photo=(), document=None, voice=None, audio=None):
        self.photo, self.document, self.voice, self.audio, self.text, self.replies = list(photo), document, voice, audio, None, []

    async def reply_text(self, text, **kw):
        self.replies.append((text, kw))


def send(chat_id, message, language_code="en", bot=None):
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_user=SimpleNamespace(language_code=language_code), message=message)
    return update, SimpleNamespace(bot=bot or FakeBot())


def run_image(chat_id, media, as_photo=True, **kw):
    update, ctx = send(chat_id, FakeMessage(photo=[media]) if as_photo else FakeMessage(document=media), **kw)
    asyncio.run(telegram_bot.image_msg(update, ctx))
    return update.message.replies, ctx.bot.actions


def texts(replies):
    return [t for t, _ in replies]


# ---------------------------------------------------------------- a photo
def test_a_photo_is_downloaded_in_its_largest_size_read_and_checked_with_the_typing_action(images):
    small, big, mid = FakeMedia(b"small", width=90, height=51), FakeMedia(b"BIG-ONE", width=1280, height=720), FakeMedia(b"mid", width=320, height=180)
    update, ctx = send(2001, FakeMessage(photo=[small, big, mid]))  # not even in order: the biggest by pixels is the one
    asyncio.run(telegram_bot.image_msg(update, ctx))
    assert (small.fetched, big.fetched, mid.fetched) == (0, 1, 0) and images.calls[0][0] == b"BIG-ONE"
    assert ctx.bot.actions == [(2001, "typing")]
    (said, _), (checked, kw) = update.message.replies
    assert said.startswith("📷 I read this from your screenshot:") and checked.startswith("🚨") and kw["keyboard"] == [["qn"], ["ch"]] and kw["preview"] is False


def test_the_last_photo_size_wins_a_tie(images):
    a, b = FakeMedia(b"first"), FakeMedia(b"second")
    update, ctx = send(2002, FakeMessage(photo=[a, b]))
    asyncio.run(telegram_bot.image_msg(update, ctx))
    assert (a.fetched, b.fetched) == (0, 1)


def test_a_file_that_is_too_big_is_refused_before_anything_is_downloaded(images, monkeypatch):
    monkeypatch.setattr(image, "MAX_BYTES", 1000)
    media = FakeMedia(b"tiny", file_size=1001)
    replies, actions = run_image(2003, media)
    assert media.fetched == 0 and actions == [] and images.calls == []
    assert texts(replies) == ["That picture is too big (the limit is 0.001 MB). Please send a smaller one, or paste the text."]
    ok = FakeMedia(b"tiny", file_size=1000)
    assert run_image(2003, ok)[0][0][0].startswith("📷") and ok.fetched == 1


def test_when_telegram_does_not_say_how_big_it_is_the_bytes_are_measured_after_the_download(images, monkeypatch):
    monkeypatch.setattr(image, "MAX_BYTES", 10)
    media = FakeMedia(b"x" * 11)
    media.file_size = None
    replies, _ = run_image(2004, media)
    assert media.fetched == 1 and images.calls == [] and texts(replies)[0].startswith("That picture is too big")


def test_when_screenshots_are_off_nothing_is_downloaded_and_the_chat_is_told_in_its_language(images, monkeypatch):
    monkeypatch.setattr(image, "available", lambda: False)
    media = FakeMedia()
    replies, actions = run_image(2005, media, language_code="zh-hans")
    assert media.fetched == 0 and actions == [] and texts(replies) == ["读取截图需要用到AI，这里没有开启。请直接粘贴文字。"]


def test_a_picture_sent_as_a_file_is_read_too(images):
    doc = FakeMedia(b"PNG-FILE", mime_type="image/png")
    replies, actions = run_image(2006, doc, as_photo=False)
    assert doc.fetched == 1 and images.calls[0][0] == b"PNG-FILE" and len(replies) == 2 and actions == [(2006, "typing")]


def test_a_chinese_speaking_chat_gets_chinese_replies(images):
    replies, _ = run_image(2007, FakeMedia(), language_code="zh-hans")
    assert replies[0][0].startswith("📷 我从你的截图里读到：") and "骗局" in replies[1][0].splitlines()[0]


def test_the_twenty_first_picture_in_an_hour_is_not_even_downloaded(images):
    media = [FakeMedia() for _ in range(21)]
    out = [run_image(2008, m)[0] for m in media]
    assert all(len(r) == 2 for r in out[:20]) and sum(m.fetched for m in media) == 20 and media[20].fetched == 0
    assert texts(out[20]) == ["You've sent a lot of pictures. Please wait a while, or paste the text instead."]


def test_a_reader_that_says_no_is_a_polite_message(images):
    from core.inputs.errors import InputError

    images.error = InputError("unreadable", "I couldn't open that picture. Please send it again.")
    replies, actions = run_image(2009, FakeMedia())
    assert texts(replies) == ["I couldn't open that picture. Please send it again."] and actions == [(2009, "typing")]


# ---------------------------------------------------------------- things going wrong
def test_a_failed_download_is_a_polite_reply_and_a_log_line_not_a_crash(images):
    media = FakeMedia(fail=ConnectionError("Telegram timed out: token 123:SECRET"))
    replies, _ = run_image(2020, media)
    assert texts(replies) == ["Sorry, I couldn't read that. Please send the text."] and images.calls == []
    events = open(logger.path(), encoding="utf-8").read()
    assert '"where":"bot.image"' in events and '"type":"ConnectionError"' in events and "SECRET" not in events


def test_a_crash_in_the_handler_is_a_polite_reply_in_the_chats_language(images, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(handlers, "on_image", boom)
    replies, _ = run_image(2021, FakeMedia(), language_code="zh")
    assert texts(replies) == ["抱歉，我没能读懂这个。请把文字发给我。"]
    monkeypatch.setattr(handlers, "image_precheck", boom)  # even the first step
    assert texts(run_image(2022, FakeMedia())[0]) == ["Sorry, I couldn't read that. Please send the text."]
    assert open(logger.path(), encoding="utf-8").read().count('"kind":"error"') == 2


def test_the_sorry_reply_still_works_if_the_database_is_what_broke(images, monkeypatch):
    monkeypatch.setattr(handlers, "image_precheck", lambda *a: (_ for _ in ()).throw(RuntimeError("db gone")))
    monkeypatch.setattr(handlers, "bind_chat", lambda *a: (_ for _ in ()).throw(RuntimeError("db gone")))
    assert texts(run_image(2023, FakeMedia(), language_code="zh-hant")[0]) == [to_traditional("抱歉，我没能读懂这个。请把文字发给我。")]


def test_the_typing_action_is_repeated_while_the_work_takes_long_and_a_failing_action_does_not_stop_it(images, monkeypatch):
    monkeypatch.setattr(telegram_bot, "TYPING_EVERY", 0.01)
    real = images.run
    images.run = lambda data, **kw: (time.sleep(0.12), real(data, **kw))[1]
    update, ctx = send(2024, FakeMessage(photo=[FakeMedia()]), bot=FakeBot(fail=True))
    asyncio.run(telegram_bot.image_msg(update, ctx))
    assert len(ctx.bot.actions) >= 3 and all(a == (2024, "typing") for a in ctx.bot.actions)
    assert len(update.message.replies) == 2  # the actions all raised, the answer still came


def test_an_update_without_a_message_is_ignored(images):
    for fn in (telegram_bot.image_msg, telegram_bot.voice_msg):
        update, ctx = send(2025, None)
        asyncio.run(fn(update, ctx))
        assert ctx.bot.actions == []


# ---------------------------------------------------------------- a voice note
def run_voice(chat_id, message, **kw):
    update, ctx = send(chat_id, message, **kw)
    asyncio.run(telegram_bot.voice_msg(update, ctx))
    return update.message.replies, ctx.bot.actions


def test_a_voice_note_is_downloaded_transcribed_and_checked(voices):
    voice = FakeMedia(b"OggS", mime_type="audio/ogg", duration=12)
    replies, actions = run_voice(2030, FakeMessage(voice=voice))
    assert voice.fetched == 1 and voices.calls == [(b"OggS", {"mime": "audio/ogg", "lang_hint": ""})] and actions == [(2030, "typing")]
    assert texts(replies)[0].startswith("🎙️ I heard:") and texts(replies)[1].startswith("🚨") and replies[1][1]["keyboard"] == [["qn"], ["ch"]]


def test_an_audio_file_is_read_like_a_voice_note_and_a_timedelta_duration_is_understood(voices):
    song = FakeMedia(b"ID3", mime_type="audio/mpeg", duration=datetime.timedelta(seconds=30))
    replies, _ = run_voice(2031, FakeMessage(audio=song))
    assert song.fetched == 1 and voices.calls[0][1]["mime"] == "audio/mpeg" and len(replies) == 2
    long = FakeMedia(b"ID3", mime_type="audio/mpeg", duration=datetime.timedelta(seconds=audio.MAX_SECONDS + 1))
    replies, actions = run_voice(2031, FakeMessage(audio=long))
    assert long.fetched == 0 and actions == [] and texts(replies)[0].startswith("That voice note is too long")


def test_a_voice_note_that_is_too_long_or_too_big_is_refused_before_it_is_downloaded(voices):
    long = FakeMedia(b"x", duration=audio.MAX_SECONDS + 1)
    replies, actions = run_voice(2032, FakeMessage(voice=long), language_code="zh")
    assert long.fetched == 0 and actions == [] and texts(replies) == [f"这条语音太长了（上限 {audio.MAX_SECONDS} 秒）。请发一条短一点的，或者直接发文字。"]
    big = FakeMedia(b"x", file_size=audio.MAX_BYTES + 1, duration=5)
    replies, _ = run_voice(2032, FakeMessage(voice=big))
    assert big.fetched == 0 and texts(replies)[0].startswith("That voice note is too big") and voices.calls == []
    edge = FakeMedia(b"x", file_size=audio.MAX_BYTES, duration=audio.MAX_SECONDS)
    assert len(run_voice(2032, FakeMessage(voice=edge))[0]) == 2 and edge.fetched == 1


def test_voice_notes_that_are_off_are_explained_without_downloading(voices, monkeypatch):
    monkeypatch.setattr(audio, "available", lambda: False)
    voice = FakeMedia(duration=3, mime_type="audio/ogg")
    replies, actions = run_voice(2033, FakeMessage(voice=voice))
    assert voice.fetched == 0 and actions == [] and texts(replies) == ["Voice notes are not switched on here. Send the text or a screenshot instead."]


def test_a_failed_voice_download_is_a_polite_reply(voices):
    replies, _ = run_voice(2034, FakeMessage(voice=FakeMedia(duration=3, fail=TimeoutError("slow"))))
    assert texts(replies) == ["Sorry, I couldn't read that. Please send the text."] and '"where":"bot.voice"' in open(logger.path(), encoding="utf-8").read()


# ---------------------------------------------------------------- the real python-telegram-bot, still offline
def message_update(**fields):
    from telegram import Update

    msg = {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}, **fields}
    return Update.de_json({"update_id": 1, "message": msg}, None)


def test_the_registered_handlers_pick_up_the_right_messages(monkeypatch):
    pytest.importorskip("telegram")
    from telegram.ext import Application, MessageHandler

    monkeypatch.setattr(Application, "run_polling", lambda self, *a, **k: started.append(self))
    started = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:NOT-A-REAL-TOKEN")
    telegram_bot.main()
    by_callback = {h.callback: h for group in started[0].handlers.values() for h in group if isinstance(h, MessageHandler)}
    assert set(by_callback) == {telegram_bot.text, telegram_bot.image_msg, telegram_bot.voice_msg}

    def picked(**fields):
        update = message_update(**fields)
        return sorted(cb.__name__ for cb, h in by_callback.items() if h.check_update(update))

    file = {"file_id": "a", "file_unique_id": "b"}
    assert picked(photo=[{**file, "width": 90, "height": 90}]) == ["image_msg"]
    assert picked(document={**file, "mime_type": "image/png"}) == ["image_msg"]
    assert picked(document={**file, "mime_type": "image/jpeg"}) == ["image_msg"]
    assert picked(document={**file, "mime_type": "application/pdf"}) == []
    assert picked(voice={**file, "duration": 3}) == ["voice_msg"]
    assert picked(audio={**file, "duration": 3}) == ["voice_msg"]
    assert picked(text="hello") == ["text"]
    assert picked(text="/start", entities=[{"type": "bot_command", "offset": 0, "length": 6}]) == []


def test_a_real_photo_size_and_voice_duration_work_with_the_connector_helpers():
    pytest.importorskip("telegram")
    msg = message_update(photo=[{"file_id": "a", "file_unique_id": "a", "width": 90, "height": 60}, {"file_id": "b", "file_unique_id": "b", "width": 1280, "height": 853}],
                         voice={"file_id": "c", "file_unique_id": "c", "duration": 12, "mime_type": "audio/ogg", "file_size": 999}).message
    assert telegram_bot.largest_photo(msg.photo).file_id == "b"
    assert telegram_bot.seconds_of(msg.voice) == 12 and telegram_bot.seconds_of(SimpleNamespace()) is None
