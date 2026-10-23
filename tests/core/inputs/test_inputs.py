"""What this server can do with screenshots and voice, the source field of a check, and that every message a person can see is translated."""
import io
import json
import math
import struct
import wave
from types import SimpleNamespace

import pytest
from PIL import Image

from core import inputs, obs
from core.ai import llm
from core.inputs import InputError, audio, image
from core.lang import i18n
from core.lang.i18n_inputs import INPUTS_ZH
from core.pipelines.check import check_message


def png(w=600, h=900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


def wav_bytes(seconds=1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(int(seconds * 16000))))
    return buf.getvalue()


@pytest.fixture
def vision(monkeypatch):
    monkeypatch.setattr(llm, "vision_available", lambda: True)
    monkeypatch.setattr(image, "_qr_texts", lambda pieces: [])

    def install(answer):
        monkeypatch.setattr(llm, "vision_json", lambda *a, **k: dict(answer, _usage={"in": 1, "out": 1, "ms": 1}))
    return install


@pytest.fixture
def stt(monkeypatch):
    monkeypatch.setattr(audio, "available", lambda: True)

    def install(text, language="en"):
        model = SimpleNamespace(transcribe=lambda a, **kw: (iter([SimpleNamespace(text=text, no_speech_prob=0.0, avg_logprob=-0.1)]), SimpleNamespace(language=language)))
        monkeypatch.setattr(audio, "_load", lambda: model)
    return install


def test_capabilities_say_what_this_server_can_do(monkeypatch):
    monkeypatch.setattr(image, "available", lambda: False)
    monkeypatch.setattr(audio, "available", lambda: False)
    assert inputs.capabilities() == {"image": False, "audio": False}
    monkeypatch.setattr(image, "available", lambda: True)
    monkeypatch.setattr(audio, "available", lambda: True)
    assert inputs.capabilities() == {"image": True, "audio": True}


def test_by_default_in_the_test_suite_nothing_is_on():
    assert inputs.capabilities()["image"] is False  # no key: tests never reach the model


# ---------------------------------------------------------------- check_message additions
def test_check_message_takes_source_and_read_text_without_changing_the_verdict():
    text = "Your bank: we sent a 6-digit code. Reply with that code to keep your account open."
    plain = check_message(text, store=False, log=False)
    shot = check_message(text, store=False, log=False, source="screenshot", read_text=text)
    assert (plain.source, plain.read_text) == ("text", "")
    assert (shot.source, shot.read_text) == ("screenshot", text)
    assert (plain.verdict, plain.headline) == (shot.verdict, shot.headline)
    with pytest.raises(TypeError):  # keyword-only: nobody passes them by position by accident
        check_message(text, True, None, False, None, "voice")


def test_the_check_log_keeps_the_source_but_never_the_text(monkeypatch):
    events = []
    monkeypatch.setattr(obs, "emit", events.append)
    secret = "Hi mum my new number is 07911123456 please send 450 pounds, Alice"
    check_message(secret, store=False, source="voice", read_text=secret)
    ev = next(e for e in events if e.get("kind") == "check")
    assert ev["msg"]["source"] == "voice" and "Alice" not in json.dumps(ev) and "07911123456" not in json.dumps(ev)


# ---------------------------------------------------------------- everything a person can see is translated
def strings(module, prefixes):
    return {v for k, v in vars(module).items() if k.startswith(prefixes) and isinstance(v, str)}


def test_every_input_error_and_caution_has_a_chinese_text():
    shown = strings(image, ("ERR_", "NOTE_")) | strings(audio, ("ERR_",))
    assert len(shown) >= 15
    assert not [s for s in shown if s not in INPUTS_ZH], [s for s in shown if s not in INPUTS_ZH]
    for s in shown:
        assert i18n.tr(s, "zh") == INPUTS_ZH[s] and i18n.tr(s, "zh") != s
        assert i18n.tr(s, "zh-Hant") != s and i18n.tr(s, "en") == s


def test_the_stub_messages_the_other_agents_rely_on_are_still_there():
    assert "Reading screenshots needs the AI, which is not switched on here. Paste the text instead." in INPUTS_ZH
    assert "Voice notes are not switched on here. Send the text or a screenshot instead." in INPUTS_ZH
    with pytest.raises(AssertionError):
        InputError("nonsense", "x")  # codes are a closed set


def test_the_link_panel_and_evidence_texts_are_translated():
    for s in ("This short link really goes to {dest}", "The real website of {brand}", "Looks like {official} but isn't", "A short link that goes to {dest}",
              "A short link: it hides where it really goes", "Looks suspicious", "A long-established website", "Not verified", "This address {why}",
              "This is where the short link really goes", "Registered {n} days ago", "Registered about {n} years ago", "This website address doesn't exist (any more)",
              "It points to an internal address, which a real website never does"):
        assert s in INPUTS_ZH, s
        placeholders = {p for p in ("{dest}", "{brand}", "{official}", "{why}", "{n}") if p in s}
        assert all(p in INPUTS_ZH[s] for p in placeholders), s


# ---------------------------------------------------------------- where the picture comes from
def test_the_reader_reports_the_app_and_channel_but_only_from_the_fixed_list(vision):
    vision({"text": "Voucher Applied APP | PAYDAY REWARDS 1-FOR-1", "channel": "App", "app": "Tomoro Coffee\n(official)", "sender": ""})
    r = image.read_image(png())
    assert r.channel == "app" and r.app == "Tomoro Coffee (official)"
    vision({"text": "hello", "channel": "carrier pigeon; ignore the rules", "app": ""})
    r = image.read_image(png())
    assert r.channel == "" and r.app == ""  # the model's own words are never passed on as a channel
    vision({"text": "hello"})
    assert image.read_image(png()).channel == ""
