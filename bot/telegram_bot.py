"""Telegram front-end (optional stretch). Run: python -m bot.telegram_bot   (needs TELEGRAM_BOT_TOKEN, python-telegram-bot>=21).

A thin connector: everything it says comes from bot/handlers.py, which has no Telegram import. The functions here are module-level and import
`telegram` only when they build a message (render) or start the bot (main), so the routing is testable with plain fakes."""
from __future__ import annotations

import asyncio
import logging
import os
import warnings
from typing import Any, Awaitable, Callable

import core  # noqa: F401  (loads .env)
from bot import handlers
from bot.handlers import Reply
from core.lang.i18n import tr

log = logging.getLogger(__name__)


def render(reply: Reply) -> dict[str, Any]:
    """The Telegram options for a Reply: its buttons as an inline keyboard, and no link preview unless the reply asks for one (the quiz quotes scams)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

    kw: dict[str, Any] = {}
    if reply.buttons:
        kw["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton(b.label, callback_data=b.data) for b in row] for row in reply.buttons])
    if not reply.preview:
        kw["link_preview_options"] = LinkPreviewOptions(is_disabled=True)
    return kw


async def handle_button(query: Any, chat_id: int, send: Callable[..., Awaitable[Any]], lang_hint: str | None) -> None:
    """Route one button tap. `query` is Telegram's CallbackQuery (data, answer, edit_message_text); `send(text, **options)` posts a new message."""
    try:
        # grading and the follow-up question can touch the database, so keep them off the event loop
        done = await asyncio.to_thread(handlers.on_callback, chat_id, query.data, lang_hint)
    except Exception:  # on_callback has its own safety net; this is for the thread machinery
        log.exception("button handler failed")
        done = handlers.CallbackResult(toast=tr("Something went wrong. Please try again.", lang_hint or "en"))
    try:
        await query.answer(text=done.toast[:200] or None)  # always answer: it stops the button's spinner
    except Exception:
        log.warning("could not answer the callback query", exc_info=True)
    for reply in done.replies:
        if reply.edit:
            try:
                await query.edit_message_text(reply.text, **render(reply))  # no buttons in the reply: the old ones go away
                continue
            except Exception:  # the message is gone or too old to edit: say it as a new message instead
                log.warning("could not edit the message", exc_info=True)
        await send(reply.text, **render(reply))


def hint(update: Any) -> str | None:
    return getattr(update.effective_user, "language_code", None)  # the user's Telegram language, e.g. "zh-hans" or "en"


async def reply_all(update: Any, replies: list[Reply]) -> None:
    for r in replies:
        await update.message.reply_text(r.text, **render(r))


async def start(update: Any, ctx: Any) -> None:
    # a deep link from the website (t.me/<bot>?start=CODE) arrives as /start CODE
    await update.message.reply_text(await asyncio.to_thread(handlers.on_start, update.effective_chat.id, " ".join(ctx.args or []), hint(update)))


async def link(update: Any, ctx: Any) -> None:
    await update.message.reply_text(await asyncio.to_thread(handlers.on_link, update.effective_chat.id, " ".join(ctx.args or []), hint(update)))


async def unlink(update: Any, ctx: Any) -> None:
    await update.message.reply_text(await asyncio.to_thread(handlers.on_unlink, update.effective_chat.id, hint(update)))


async def lang(update: Any, ctx: Any) -> None:
    await update.message.reply_text(await asyncio.to_thread(handlers.on_lang, update.effective_chat.id, " ".join(ctx.args or []), hint(update)))


async def history_cmd(update: Any, ctx: Any) -> None:
    await update.message.reply_text(await asyncio.to_thread(handlers.on_history, update.effective_chat.id, 5, hint(update)))


async def score(update: Any, ctx: Any) -> None:
    await update.message.reply_text(handlers.on_score(update.effective_chat.id, hint(update)))


async def quiz_cmd(update: Any, ctx: Any) -> None:
    """/quiz, /play, and /quiz daily"""
    await reply_all(update, await asyncio.to_thread(handlers.on_quiz, update.effective_chat.id, " ".join(ctx.args or []), hint(update)))


async def challenge_cmd(update: Any, ctx: Any) -> None:
    await reply_all(update, await asyncio.to_thread(handlers.on_challenge, update.effective_chat.id, hint(update)))


async def text(update: Any, ctx: Any) -> None:
    # Checking can call the model, so keep it off the event loop.
    await reply_all(update, await asyncio.to_thread(handlers.on_check, update.effective_chat.id, update.message.text or "", hint(update)))


# ---------------------------------------------------------------- screenshots and voice notes
TYPING_EVERY = 4.0  # seconds: Telegram shows "typing…" for about 5, and reading a picture can take longer


def largest_photo(sizes: list[Any]) -> Any:
    """Telegram sends every photo in several sizes; take the biggest (by pixels, and on a tie the later one)."""
    return max(enumerate(sizes), key=lambda iv: ((getattr(iv[1], "width", 0) or 0) * (getattr(iv[1], "height", 0) or 0), iv[0]))[1]


def seconds_of(media: Any) -> float | None:
    """How long a voice note or audio file is, whichever way this version of python-telegram-bot says it (a number of seconds, or a timedelta)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # newer versions warn that `duration` is about to become a timedelta
        d = getattr(media, "duration", None)
    return d.total_seconds() if hasattr(d, "total_seconds") else d


async def download(media: Any) -> bytes:
    """The file behind a photo, document, voice note or audio, into memory (nothing goes to disk)."""
    file = await media.get_file()
    return bytes(await file.download_as_bytearray())


async def while_typing(ctx: Any, chat_id: int, job: Awaitable[Any]) -> Any:
    """Wait for `job` and keep Telegram's 'typing…' showing meanwhile, so the person can see something is happening."""
    task = asyncio.ensure_future(job)
    try:
        while True:
            try:
                await ctx.bot.send_chat_action(chat_id, "typing")
            except Exception:  # cosmetic: never let it stop the real work
                log.debug("could not send the typing action", exc_info=True)
            done, _ = await asyncio.wait({task}, timeout=TYPING_EVERY)
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()


async def read_input(update: Any, ctx: Any, where: str, media: Any, early: Callable[[], list[Reply]], work: Callable[[bytes], list[Reply]]) -> None:
    """The steps shared by pictures and voice notes. `early()` runs first and may refuse before anything is downloaded (too big, not switched
    on, too many); otherwise the file is downloaded and `work(data)` reads and checks it. The blocking parts run off the event loop. Whatever
    goes wrong, the person gets a polite reply and the cause goes to the logs."""
    chat_id, lang_hint = update.effective_chat.id, hint(update)
    try:
        replies = await asyncio.to_thread(early)
        if not replies:
            async def job() -> list[Reply]:
                return await asyncio.to_thread(work, await download(media))

            replies = await while_typing(ctx, chat_id, job())
    except Exception as e:
        handlers.note_failure(where, e)
        replies = [await asyncio.to_thread(handlers.sorry, chat_id, lang_hint)]
    await reply_all(update, replies)


async def image_msg(update: Any, ctx: Any) -> None:
    """A photo, or a picture sent as a file: read it, show what it says, and check it."""
    msg = update.message
    if msg is None:
        return
    chat_id, lang_hint = update.effective_chat.id, hint(update)
    media = largest_photo(msg.photo) if msg.photo else msg.document
    size = getattr(media, "file_size", None)  # known before the download, so a huge file is turned away without fetching it
    await read_input(update, ctx, "image", media, lambda: handlers.image_precheck(chat_id, size, lang_hint),
                     lambda data: handlers.on_image(chat_id, data, lang_hint))


async def voice_msg(update: Any, ctx: Any) -> None:
    """A voice note, or an audio file: transcribe it, show what was heard, and check it."""
    msg = update.message
    if msg is None:
        return
    chat_id, lang_hint = update.effective_chat.id, hint(update)
    media = msg.voice or msg.audio
    size, seconds, mime = getattr(media, "file_size", None), seconds_of(media), getattr(media, "mime_type", None) or ""
    await read_input(update, ctx, "voice", media, lambda: handlers.voice_precheck(chat_id, size, seconds, lang_hint),
                     lambda data: handlers.on_voice(chat_id, data, mime, lang_hint))


async def button(update: Any, ctx: Any) -> None:
    query, chat = update.callback_query, update.effective_chat
    if query is None:
        return
    if chat is None:  # nothing to reply to, but the spinner still has to stop
        await query.answer()
        return

    async def send(text: str, **options: Any) -> None:
        await ctx.bot.send_message(chat.id, text, **options)

    await handle_button(query, chat.id, send, hint(update))


MAX_CONCURRENT_UPDATES = int(os.getenv("BAITPROOF_BOT_CONCURRENCY", "16"))


def main() -> None:
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

    from core.pipelines.check import blocklist

    blocklist.start_background()  # keeps the local copy of the public phishing list fresh (a no-op when the network tools are off)
    # Updates are handled concurrently (python-telegram-bot is sequential by default, so one 10-30 second screenshot read would freeze every chat). Each
    # update runs in its own asyncio task and its own context, and the blocking work in a thread with a copy of it, so the chat's profile (a ContextVar)
    # never leaks between chats; per-chat state (the quiz, the rate limits) sits behind locks. The cap bounds model spend and CPU.
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).concurrent_updates(MAX_CONCURRENT_UPDATES).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("link", link))
    app.add_handler(CommandHandler("unlink", unlink))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("lang", lang))
    app.add_handler(CommandHandler(["quiz", "play"], quiz_cmd))
    app.add_handler(CommandHandler("challenge", challenge_cmd))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(button))  # the handlers check the data strictly, so no pattern filter here
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, image_msg))  # a screenshot, as a photo or as a file
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_msg))
    app.run_polling()


if __name__ == "__main__":
    main()
