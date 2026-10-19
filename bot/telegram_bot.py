"""Telegram front-end (optional stretch). Run: python -m bot.telegram_bot   (needs TELEGRAM_BOT_TOKEN, python-telegram-bot>=21)."""
from __future__ import annotations

import asyncio
import os

import core  # noqa: F401  (loads .env)
from bot import handlers


def main() -> None:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(handlers.WELCOME)

    async def score(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(handlers.on_score(update.effective_chat.id))

    async def text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        # Checking can call the model, so keep it off the event loop.
        reply = await asyncio.to_thread(handlers.on_text, update.effective_chat.id, update.message.text or "")
        await update.message.reply_text(reply)

    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    app.run_polling()


if __name__ == "__main__":
    main()
