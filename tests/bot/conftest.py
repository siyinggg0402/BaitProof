import pytest

from bot import handlers
from core.game import engine


@pytest.fixture(autouse=True)
def fresh_bot_state(monkeypatch):
    """The bot keeps a little state in memory (active quizzes, rate limits, the engine's rounds): every test starts with none of it."""
    for table in (handlers.ATTEMPTS, handlers.RATE, handlers._ACTIVE, engine._rounds):
        table.clear()
    monkeypatch.delenv("BAITPROOF_URL", raising=False)  # a test that needs the web address sets it
    monkeypatch.delenv("BAITPROOF_MULTIUSER", raising=False)


class Reader:
    """Stands in for the vision model and the speech model (the real ones cost money and need the network). Set `reading` / `heard`, or `error`
    to make the call raise; `calls` lists what each call was given."""
    def __init__(self, ok):
        self.ok, self.error, self.calls = ok, None, []

    def run(self, data, **kw):
        self.calls.append((bytes(data), kw))
        if self.error is not None:
            raise self.error
        return self.ok


@pytest.fixture
def images(monkeypatch):
    """Screenshots are switched on and read by a fake that returns `images.ok` (an ImageReading)."""
    from core.inputs import image

    box = Reader(image.ImageReading(text="Buy 4 gift cards and send me the numbers please."))
    monkeypatch.setattr(image, "available", lambda: True)
    monkeypatch.setattr(image, "read_image", lambda data, *, lang="en": box.run(data, lang=lang))
    return box


@pytest.fixture
def voices(monkeypatch):
    """Voice notes are switched on and transcribed by a fake that returns `voices.ok` (a Transcript)."""
    from core.inputs import audio

    box = Reader(audio.Transcript(text="Buy 4 gift cards and send me the numbers please.", language="en", seconds=5.0))
    monkeypatch.setattr(audio, "available", lambda: True)
    monkeypatch.setattr(audio, "transcribe", lambda data, *, mime="", lang_hint="": box.run(data, mime=mime, lang_hint=lang_hint))
    return box
