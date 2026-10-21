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
