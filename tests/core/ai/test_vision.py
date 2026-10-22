"""llm.vision_json: the request it builds and how it fails. No network: the client is faked."""
from types import SimpleNamespace

import pytest

from core import obs
from core.ai import llm


def _client(content='{"text": "hi"}', calls=None, fail=0, status=None):
    def create(**kw):
        if calls is not None:
            calls.append(kw)
        if len(calls or []) <= fail:
            err = ConnectionError("down")
            err.status_code = status
            raise err
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1900, completion_tokens=140), choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.delenv("BAITPROOF_VISION", raising=False)
    monkeypatch.delenv("NEBIUS_MODEL_VISION", raising=False)


def test_vision_is_off_without_the_ai_or_with_the_switch(monkeypatch):
    assert not llm.vision_available()  # the test suite has no key
    monkeypatch.setattr(llm, "available", lambda: True)
    assert llm.vision_available()
    monkeypatch.setenv("BAITPROOF_VISION", "0")
    assert not llm.vision_available()
    with pytest.raises(llm.LLMUnavailable):
        llm.vision_json("s", "u", [("image/png", b"x")])


def test_request_carries_the_image_as_a_data_uri_with_thinking_off(on, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_client", lambda: _client(calls=calls))
    before = dict(llm.USAGE)
    out = llm.vision_json("system", "read it", [("image/png", b"\x89PNGdata")], purpose="vision")
    kw = calls[0]
    assert kw["model"] == "nvidia/Nemotron-3.5-Super-VL" and kw["temperature"] == 0 and kw["max_tokens"] == 900
    assert kw["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    part = kw["messages"][1]["content"]
    assert part[0] == {"type": "text", "text": "read it"}
    assert part[1]["type"] == "image_url" and part[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert out["text"] == "hi" and out["_usage"]["in"] == 1900 and out["_usage"]["out"] == 140
    assert llm.USAGE["calls"] == before["calls"] + 1 and llm.USAGE["prompt_tokens"] == before["prompt_tokens"] + 1900


def test_the_vision_model_can_be_chosen_and_the_call_is_recorded(on, monkeypatch):
    monkeypatch.setenv("NEBIUS_MODEL_VISION", "some/other-vl")
    monkeypatch.setattr(llm, "_client", lambda: _client(calls=[]))
    run = obs.start()
    llm.vision_json("s", "u", [("image/jpeg", b"x")], purpose="vision")
    assert run.llm[0]["model"] == "some/other-vl" and run.llm[0]["tokens_in"] == 1900 and run.llm[0]["ok"] is True
    assert "base64" not in str(run.llm)  # the picture is never part of the record


def test_user_text_is_scrubbed_but_the_call_still_happens(on, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_client", lambda: _client(calls=calls))
    llm.vision_json("s", "mail me at bob@example.com", [("image/png", b"x")])
    assert "bob@example.com" not in str(calls[0]["messages"][1]["content"][0])


def test_a_failed_call_raises_after_one_retry_and_is_recorded(on, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_client", lambda: _client(calls=calls, fail=5))
    run = obs.start()
    with pytest.raises(llm.LLMUnavailable):
        llm.vision_json("s", "u", [("image/png", b"x")])
    assert len(calls) == 2 and [c["ok"] for c in run.llm] == [False, False]


def test_a_bad_key_is_not_retried(on, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_client", lambda: _client(calls=calls, fail=5, status=401))
    with pytest.raises(llm.LLMUnavailable):
        llm.vision_json("s", "u", [("image/png", b"x")])
    assert len(calls) == 1


def test_json_with_a_missing_closing_bracket_is_repaired_for_vision_only(on, monkeypatch):
    cut = '{"links": [{"link": "a.com/x", "spelled": "a . c o m / x"}, {"link": "b.com"}]'  # the final } is missing, as the model once did
    monkeypatch.setattr(llm, "_client", lambda: _client(content=cut, calls=[]))
    assert llm.vision_json("s", "u", [("image/png", b"x")])["links"][1]["link"] == "b.com"
    with pytest.raises(ValueError):
        llm.parse_json(cut)  # the text path is unchanged


def test_an_empty_answer_is_a_failure_not_an_empty_dict(on, monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: _client(content="", calls=[]))
    with pytest.raises(llm.LLMUnavailable):
        llm.vision_json("s", "u", [("image/png", b"x")])


def test_the_vision_client_has_a_short_leash_and_no_sdk_retry(monkeypatch):
    seen = {}

    class C:
        def with_options(self, **kw):
            seen.update(kw)
            return "short-leash-client"
    monkeypatch.setattr(llm, "_client", lambda: C())
    assert llm._vision_client() == "short-leash-client" and seen == {"timeout": 20, "max_retries": 0}
    monkeypatch.setattr(llm, "_client", lambda: "plain-double")
    assert llm._vision_client() == "plain-double"
