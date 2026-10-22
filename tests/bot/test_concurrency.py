"""With concurrent updates, two chats handled at the same moment must never see each other's profile, records or quiz."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from bot import handlers
from core.storage import db, history


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
