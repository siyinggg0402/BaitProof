"""Voice notes to text with a FAKE speech model: nothing is downloaded and nothing is transcribed for real. The decoding (PyAV) is real."""
import io
import json
import math
import struct
import wave
from types import SimpleNamespace

import pytest

from core import obs
from core.inputs import InputError
from core.inputs import audio as A

av = pytest.importorskip("av")


def wav_bytes(seconds=1.0, rate=16000, tone=True) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 8)) if tone else 0) for i in range(n)))
    return buf.getvalue()


def seg(text, no_speech=0.01, logprob=-0.2):
    return SimpleNamespace(text=text, no_speech_prob=no_speech, avg_logprob=logprob)


class FakeModel:
    def __init__(self, segments, language="en"):
        self.segments, self.language, self.calls = segments, language, []

    def transcribe(self, audio, **kw):
        self.calls.append(dict(kw, samples=len(audio)))
        return iter(self.segments), SimpleNamespace(language=self.language, language_probability=0.99)


@pytest.fixture
def stt(monkeypatch):
    monkeypatch.setattr(A, "available", lambda: True)

    def install(*segments, language="en"):
        m = FakeModel(list(segments), language)
        monkeypatch.setattr(A, "_load", lambda: m)
        return m
    return install


# ---------------------------------------------------------------- switches
def test_available_needs_the_package_and_is_never_a_download(monkeypatch):
    monkeypatch.delenv("BAITPROOF_STT", raising=False)
    monkeypatch.setattr(A.importlib.util, "find_spec", lambda name: object())
    assert A.available()
    monkeypatch.setattr(A.importlib.util, "find_spec", lambda name: None)
    assert not A.available()
    monkeypatch.setattr(A.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setenv("BAITPROOF_STT", "0")
    assert not A.available()


def test_unavailable_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("BAITPROOF_STT", "0")
    with pytest.raises(InputError) as e:
        A.transcribe(wav_bytes())
    assert e.value.code == "unavailable" and "Voice notes are not switched on" in e.value.message


def test_warmup_does_nothing_when_off_and_loads_in_the_background_when_on(monkeypatch):
    loaded = []
    monkeypatch.setattr(A, "_load", lambda: loaded.append(1))
    monkeypatch.setattr(A, "available", lambda: False)
    A.warmup()
    assert not loaded
    monkeypatch.setattr(A, "available", lambda: True)
    events = []
    monkeypatch.setattr(obs, "emit", events.append)
    A.warmup()
    for _ in range(100):
        if events:
            break
        import time
        time.sleep(0.02)
    assert loaded and events[0]["event"] == "stt_warmup" and events[0]["ok"] is True


# ---------------------------------------------------------------- validation
def test_too_big_and_wrong_type_and_empty(stt):
    stt(seg("x"))
    with pytest.raises(InputError) as e:
        A.transcribe(wav_bytes() + b"\0" * A.MAX_BYTES)
    assert e.value.code == "too_big"
    for data in (b"", b"just some text", b"\x89PNG\r\n\x1a\n" + b"x" * 50, b"MZ" + b"x" * 100):
        with pytest.raises(InputError) as e:
            A.transcribe(data)
        assert e.value.code == "bad_type"
    with pytest.raises(InputError) as e:  # a browser that says it is an image
        A.transcribe(wav_bytes(), mime="image/png")
    assert e.value.code == "bad_type"


def test_a_corrupt_recording_is_unreadable_not_a_crash(stt):
    stt(seg("x"))
    for data in (b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\xff" * 40, b"OggS" + b"\x00" * 60, b"ID3" + b"\x00" * 30, b"\x1a\x45\xdf\xa3" + b"\x7f" * 80):
        with pytest.raises(InputError) as e:
            A.transcribe(data)
        assert e.value.code in ("unreadable", "no_text")


def test_a_recording_over_the_limit_is_refused_while_decoding(stt):
    m = stt(seg("x"))
    long = wav_bytes(seconds=A.MAX_SECONDS + 5, rate=8000, tone=False)  # small on disk, too long in time
    assert len(long) < A.MAX_BYTES
    with pytest.raises(InputError) as e:
        A.transcribe(long)
    assert e.value.code == "too_long" and not m.calls


def test_a_minute_is_fine_two_seconds_over_is_not(stt):
    stt(seg("hello"))
    assert A.transcribe(wav_bytes(seconds=A.MAX_SECONDS, rate=8000)).text == "hello"
    with pytest.raises(InputError):
        A.transcribe(wav_bytes(seconds=A.MAX_SECONDS + 2, rate=8000))


def test_a_clip_with_no_words_is_no_text(stt):
    stt()  # the model found no speech
    with pytest.raises(InputError) as e:
        A.transcribe(wav_bytes(tone=False))
    assert e.value.code == "no_text"
    stt(seg("Thank you.", no_speech=0.9, logprob=-1.5))  # a made-up phrase on silence
    with pytest.raises(InputError) as e:
        A.transcribe(wav_bytes(tone=False))
    assert e.value.code == "no_text"


def test_a_clip_that_is_too_short_to_hold_a_word(stt):
    stt(seg("x"))
    with pytest.raises(InputError) as e:
        A.transcribe(wav_bytes(seconds=0.02))
    assert e.value.code == "no_text"


def test_a_model_that_cannot_start_is_unavailable(monkeypatch):
    monkeypatch.setattr(A, "available", lambda: True)

    def boom():
        raise OSError("no model on disk and no network")
    monkeypatch.setattr(A, "_load", boom)
    with pytest.raises(InputError) as e:
        A.transcribe(wav_bytes())
    assert e.value.code == "unavailable"


# ---------------------------------------------------------------- the formats
def encode(fmt, codec, seconds=1.0, rate=48000):
    buf = io.BytesIO()
    with av.open(buf, "w", format=fmt) as out:
        st = out.add_stream(codec, rate=rate)
        st.layout = "mono"
        res = av.AudioResampler(format=st.codec_context.format.name, layout="mono", rate=rate)
        src = av.open(io.BytesIO(wav_bytes(seconds)))
        for fr in src.decode(audio=0):
            for r in res.resample(fr):
                for p in st.encode(r):
                    out.mux(p)
        for p in st.encode(None):
            out.mux(p)
    return buf.getvalue()


@pytest.mark.parametrize("fmt,codec,container", [("ogg", "libopus", "ogg"), ("webm", "libopus", "matroska,webm"), ("ipod", "aac", "mov,mp4,m4a,3gp,3g2,mj2"), ("mp3", "libmp3lame", "mp3"), ("wav", "pcm_s16le", "wav")])
def test_every_container_we_promise_decodes(stt, fmt, codec, container):
    try:
        data = encode(fmt, codec)
    except Exception:
        pytest.skip(f"this PyAV build cannot encode {codec} to make a test file")
    assert A.sniff(data) == container
    m = stt(seg("hello"))
    r = A.transcribe(data)
    assert r.text == "hello" and abs(r.seconds - 1.0) < 0.2 and m.calls[0]["samples"] > 14000


# ---------------------------------------------------------------- the words
def test_text_language_seconds_and_the_call_made_to_the_model(stt):
    m = stt(seg(" Hello, this is DHL. "), seg("Your parcel is on hold."), language="en")
    r = A.transcribe(wav_bytes(2.0), mime="audio/webm", lang_hint="en")
    assert (r.text, r.language, r.seconds) == ("Hello, this is DHL. Your parcel is on hold.", "en", 2.0)
    kw = m.calls[0]
    assert kw["language"] == "en" and kw["vad_filter"] is True and kw["condition_on_previous_text"] is False


def test_only_en_zh_ms_are_passed_as_a_language_everything_else_is_detected(stt):
    m = stt(seg("ok"))
    for hint, want in (("en", "en"), ("EN-GB", "en"), ("ms", "ms"), ("zh", "zh"), ("zh-Hant", "zh"), ("zh_TW", "zh"), ("fr", None), ("", None), ("klingon", None)):
        A.transcribe(wav_bytes(), lang_hint=hint)
        assert m.calls[-1]["language"] == want, hint


def test_chinese_is_written_in_the_script_of_the_hint(stt):
    stt(seg("您好，这里是中國信託銀行，請點擊連結"), language="zh")
    assert A.transcribe(wav_bytes(), lang_hint="zh").text == "您好，这里是中国信托银行，请点击连结"  # Simplified
    assert A.transcribe(wav_bytes(), lang_hint="zh-Hant").text == "您好，這裡是中國信託銀行，請點擊連結"  # Traditional, made from Simplified
    assert A.transcribe(wav_bytes()).text == "您好，这里是中國信託銀行，請點擊連結"  # no hint: left as heard


def test_a_spoken_link_becomes_a_link(stt):
    stt(seg("Pay the fee at dhl dash fee dash pay dot x y z slash track within twenty four hours."))
    r = A.transcribe(wav_bytes(), lang_hint="en")
    assert "dhl-fee-pay.xyz/track" in r.text


def test_control_characters_are_stripped_and_text_is_capped(stt):
    stt(seg("hello\x00‮ there " + "word " * 2000))
    r = A.transcribe(wav_bytes())
    assert "\x00" not in r.text and "‮" not in r.text and len(r.text) <= 4000


def test_the_log_gets_sizes_and_timing_never_the_audio_or_the_words(stt, monkeypatch):
    events = []
    monkeypatch.setattr(obs, "emit", events.append)
    stt(seg("My secret account number is 12345678"), language="en")
    data = wav_bytes()
    A.transcribe(data)
    ev = events[-1]
    assert ev["kind"] == "input" and ev["input"] == "audio" and ev["ok"] is True and ev["bytes"] == len(data) and ev["seconds"] == 1.0
    assert "secret" not in json.dumps(ev) and "12345678" not in json.dumps(ev)
    with pytest.raises(InputError):
        A.transcribe(b"nope")
    assert events[-1]["ok"] is False and events[-1]["code"] == "bad_type"


def test_to_script():
    assert A.to_script("中國信託銀行", "zh") == "中国信托银行"
    assert A.to_script("中国银行", "zh-Hant") == "中國銀行"
