import json
import os
from types import SimpleNamespace

import pytest

from core import obs
from core.ai import llm
from core.domain.schemas import Verdict as V
from core.obs import logger, metrics
from core.pipelines.check import check_message, pipeline


def _events():
    return [json.loads(line) for line in open(logger.path())]


def test_check_writes_one_structured_event_and_never_the_message_text():
    secret = "zebra-unicorn-4242"
    r = check_message(f"Buy gift cards now and send the codes. Ref {secret} call 0412 345 678")
    raw = open(logger.path()).read()
    assert secret not in raw and "0412" not in raw and "gift cards" not in raw
    (e,) = _events()
    assert e["kind"] == "check" and e["id"] == r.check_id and e["verdict"] == r.verdict.value
    assert len(e["msg"]["fp"]) == 12 and e["msg"]["len"] > 10
    assert {"ingest", "intent", "arbiter", "flywheel"} <= {s["stage"] for s in e["stages"]}
    assert all("ms" in s for s in e["stages"]) and e["latency_ms"] >= 0


def test_internal_error_returns_cautious_answer_and_is_logged(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom with secret text")

    monkeypatch.setattr(pipeline.intent_stage, "diagnose", boom)
    r = check_message("Pay with gift cards today.")
    assert r.verdict == V.UNSURE and r.confidence == "low" and any(s.stage == "guard" for s in r.trace)
    kinds = [e["kind"] for e in _events()]
    assert kinds == ["error", "check"]
    assert "kaboom" not in open(logger.path()).read()  # exception TYPE only, never its message


def test_empty_message_is_a_validation_error_not_a_crash_guard():
    with pytest.raises(ValueError):
        check_message("   ")


def _fake_client(fail=False):
    def create(**kw):
        if fail:
            raise ConnectionError("network down")
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30),
                               choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_llm_calls_are_recorded_with_tokens_and_failures(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setenv("NEBIUS_MODEL", "test-model")
    run = obs.start()
    monkeypatch.setattr(llm, "_client", lambda: _fake_client())
    assert llm.chat_json("s", "u", purpose="analysis") == {"ok": True}
    monkeypatch.setattr(llm, "_client", lambda: _fake_client(fail=True))
    with pytest.raises(llm.LLMUnavailable):
        llm.chat_json("s", "u", purpose="critic", retries=0)
    ok, bad = run.llm
    assert (ok["purpose"], ok["ok"], ok["tokens_in"], ok["tokens_out"], ok["model"]) == ("analysis", True, 120, 30, "test-model")
    assert bad["ok"] is False and bad["purpose"] == "critic" and bad["error"].startswith("ConnectionError")
    assert run.llm_totals() == {"calls": 2, "ok": 1, "tokens_in": 120, "tokens_out": 30}


def test_log_rotation(monkeypatch):
    monkeypatch.setattr(logger, "MAX_BYTES", 300)
    for i in range(30):
        logger.emit({"kind": "system", "i": i, "pad": "x" * 40})
    assert os.path.exists(logger.path() + ".1")
    assert len(metrics.read_events()) > 5  # reads across rotated files


def test_logging_failure_never_breaks_the_app(monkeypatch, tmp_path):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x")
    monkeypatch.setenv("BAITPROOF_LOG_DIR", str(blocker))
    before = logger.DROPPED["count"]
    logger.emit({"kind": "check"})  # must not raise
    assert logger.DROPPED["count"] == before + 1
    assert check_message("Pay with gift cards today.").verdict  # app still works


def _ev(**kw):
    base = {"kind": "check", "verdict": "scam", "confidence": "high", "rounds": 1, "latency_ms": 1000, "ai_configured": True,
            "used_ai": True, "llm_calls": 3, "tokens_in": 1000, "tokens_out": 200, "stages": [], "tools": [], "flywheel": False}
    return {**base, **kw}


def test_summarize_numbers():
    evs = [_ev(), _ev(used_ai=False, latency_ms=9000, stages=[{"stage": "grounding", "status": "flag", "ms": 5}],
                      tools=[{"tool": "domain_check", "ok": True, "ms": 3}, {"tool": "domain_check", "ok": False, "ms": 7}]),
           {"kind": "feedback", "rating": "down"}, {"kind": "error", "where": "check", "type": "KeyError", "ts": 1}]
    s = metrics.summarize(evs)
    assert s["checks"] == 2 and s["llm"]["fallbacks"] == 1 and s["llm"]["fallback_rate"] == 0.5
    assert s["gate_trips"] == {"grounding:flag": 1} and s["tools"]["domain_check"] == {"calls": 2, "ok_rate": 0.5, "avg_ms": 5}
    assert s["feedback"] == {"up": 0, "down": 1} and s["errors"] == 1 and s["llm"]["tokens_in"] == 2000


def test_health_flags_model_fallbacks_and_errors():
    good = [_ev() for _ in range(6)]
    assert metrics.health(good)["status"] == "green"
    degraded = [_ev(used_ai=False) for _ in range(6)]
    h = metrics.health(degraded)
    assert h["status"] == "amber" and "fell back to rules" in h["problems"][0]
    assert metrics.health(good + [{"kind": "error", "where": "check", "type": "X"}])["status"] == "red"


def test_warmup_is_logged_and_only_when_configured(monkeypatch):
    llm.warmup()  # not configured (conftest): no thread, no event
    assert not os.path.exists(logger.path())
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: _fake_client())
    monkeypatch.setenv("NEBIUS_MODEL", "m")
    import threading
    llm.warmup()
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(2)
    evs = _events()
    assert any(e.get("event") == "llm_warmup" and e["ok"] for e in evs)
