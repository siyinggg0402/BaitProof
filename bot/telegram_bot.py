"""Telegram front-end (optional stretch). Run: python -m bot.telegram_bot   (needs TELEGRAM_BOT_TOKEN, python-telegram-bot>=21).

A thin connector: everything it says comes from bot/handlers.py, which has no Telegram import. The functions here are module-level and import
`telegram` only when they build a message (render) or start the bot (main), so the routing is testable with plain fakes."""
from __future__ import annotations

import asyncio
import logging
import os
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


def main() -> None:
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
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
    app.run_polling()


if __name__ == "__main__":
    main()
