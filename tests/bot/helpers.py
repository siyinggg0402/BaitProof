"""Shared by the quiz tests: read a question's buttons and play a round the way a person tapping them would."""
import re

from bot import handlers
from core.game import engine
from core.storage import links

CODE = {"scam": "s", "safe": "f", "unsure": "u"}


def fake_render(reply) -> dict:
    """Stands in for the Telegram message builder (which needs the `telegram` package): the buttons' data and the preview flag."""
    return {"keyboard": [[b.data for b in row] for row in reply.buttons], "preview": reply.preview}


def datas(reply) -> list[str]:
    return [b.data for row in reply.buttons for b in row]


def labels(reply) -> list[str]:
    return [b.label for row in reply.buttons for b in row]


def round_of(chat_id: int, data: str):
    """The engine's round behind a question's buttons (for the test to know the truth; the chat never sees it)."""
    handlers.bind_chat(chat_id)
    m = re.fullmatch(r"q:([0-9a-f]{12}):([0-9]+):([sfu])", data)
    return engine.get(m.group(1), links.current_profile()), int(m.group(2))


def tap(question, choice: str) -> str:
    """The button of `question` for 'scam' | 'safe' | 'unsure'."""
    return next(d for d in datas(question) if d.endswith(":" + CODE[choice]))


def right(chat_id: int, question) -> str:
    r, i = round_of(chat_id, datas(question)[0])
    return tap(question, r.items[i].truth)


def wrong(chat_id: int, question) -> str:
    """An answer that is wrong: 'looks fine' for a scam, 'scam' for anything else."""
    r, i = round_of(chat_id, datas(question)[0])
    return tap(question, "safe" if r.items[i].truth == "scam" else "scam")


def play(chat_id: int, question, choose=right, lang_hint=None):
    """Answer every question of the round that `question` starts. Returns the list of tap results; the last one carries the summary."""
    results = []
    while True:
        res = handlers.on_callback(chat_id, choose(chat_id, question), lang_hint)
        results.append(res)
        if len(res.replies) < 2 or not res.replies[1].buttons or res.replies[1].buttons[0][0].data in (handlers.QUIZ_NEW,):
            return results
        question = res.replies[1]
