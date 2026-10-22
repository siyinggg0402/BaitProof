"""Ways into a check other than typing: a screenshot and a voice note. Both end as plain text that goes through the normal pipeline.

Both the website and the Telegram bot read the input with `image` / `audio`, show the person what was read, and then call check_message."""
from __future__ import annotations

from . import audio, image
from .errors import InputError  # noqa: F401


def capabilities() -> dict:
    """What this server can do, for the website and the bot to show or hide controls."""
    return {"image": image.available(), "audio": audio.available()}
