"""When the model service keeps failing, checks fall back to the rules at once instead of every stage waiting and retrying on its own."""
import time
from types import SimpleNamespace

import pytest

from core.ai import llm


class Service:
    """A stand-in for the OpenAI client: counts the calls that reach it and answers (or fails) as told."""

    def __init__(self, monkeypatch, answer='{"ok": true}'):
        self.calls, self.fail, self.answer = 0, False, answer
        monkeypatch.setattr(llm, "available", lambda: True)
        monkeypatch.setenv("NEBIUS_MODEL", "test-model")
        monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))))

    def create(self, **_kw):
        self.calls += 1
        if self.fail:
            raise ConnectionError("down")
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))])


def test_three_failures_in_a_row_pause_the_model_then_a_trial_call_recovers(monkeypatch):
    s, clock = Service(monkeypatch), [1000.0]
    monkeypatch.setattr(llm, "time", SimpleNamespace(monotonic=lambda: clock[0], perf_counter=time.perf_counter))  # only this module sees the fake clock
    s.fail = True
    for _ in range(3):
        with pytest.raises(llm.LLMUnavailable):
            llm.chat_json("s", "u", retries=0)
    assert s.calls == 3
    with pytest.raises(llm.LLMUnavailable, match="paused"):
        llm.chat_json("s", "u")
    assert s.calls == 3  # the paused call never reached the service
    clock[0] += llm.BREAKER_PAUSE + 1
    s.fail = False
    assert llm.chat_json("s", "u") == {"ok": True} and s.calls == 4  # one trial after the pause, and one answer clears the count
    s.fail = True
    with pytest.raises(llm.LLMUnavailable):
        llm.chat_json("s", "u", retries=0)
    assert llm._breaker["fails"] == 1  # not 4: the earlier failures are forgotten


def test_a_failed_trial_pauses_again_straight_away(monkeypatch):
    s, clock = Service(monkeypatch), [1000.0]
    monkeypatch.setattr(llm, "time", SimpleNamespace(monotonic=lambda: clock[0], perf_counter=time.perf_counter))  # only this module sees the fake clock
    s.fail = True
    for _ in range(3):
        with pytest.raises(llm.LLMUnavailable):
            llm.chat_json("s", "u", retries=0)
    clock[0] += llm.BREAKER_PAUSE + 1
    with pytest.raises(llm.LLMUnavailable):
        llm.chat_json("s", "u", retries=0)  # the trial fails ...
    with pytest.raises(llm.LLMUnavailable, match="paused"):
        llm.chat_json("s", "u")  # ... so the model is skipped again without another wait
    assert s.calls == 4


def test_one_call_with_retries_stops_trying_once_the_model_is_paused(monkeypatch):
    s = Service(monkeypatch)
    s.fail = True
    with pytest.raises(llm.LLMUnavailable):
        llm.chat_json("s", "u", retries=5)
    assert s.calls == 3  # not 6


def test_an_unreadable_reply_is_the_models_fault_and_never_pauses_it(monkeypatch):
    s = Service(monkeypatch, answer="I cannot help with that")
    for _ in range(6):
        with pytest.raises(llm.LLMUnavailable):
            llm.chat_json("s", "u", retries=0)
    assert s.calls == 6 and llm._breaker["until"] == 0.0


def test_a_pause_of_zero_turns_it_off(monkeypatch):
    s = Service(monkeypatch)
    monkeypatch.setattr(llm, "BREAKER_PAUSE", 0.0)
    s.fail = True
    for _ in range(5):
        with pytest.raises(llm.LLMUnavailable):
            llm.chat_json("s", "u", retries=0)
    assert s.calls == 5
