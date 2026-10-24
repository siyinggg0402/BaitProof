"""Turning a voice note into text on the server (optional: a local speech model; the Nebius endpoint has none).

This is an OPTIONAL feature that runs on this machine with faster-whisper (CTranslate2, CPU, int8); install it with `pip install -r requirements-extras.txt`.
Nothing is sent anywhere: the audio is decoded in memory, transcribed locally and thrown away. Nothing is downloaded until the first voice note (or
`warmup()` at server start) asks for the model; `available()` only looks whether the package is installed. When it is off, the website uses the
browser's own speech recognition instead.

Safety: the type is read from the file's first bytes and only the demuxers we expect are opened (ogg, webm, mp4/m4a, wav, aiff, mp3, flac); decoding
stops as soon as the audio is longer than MAX_SECONDS, so a small file of very long audio cannot fill memory."""
from __future__ import annotations

import importlib.util
import io
import os
import re
import threading
import time
from dataclasses import dataclass

from core import obs
from core.lang import i18n
from core.lang import text as L

from .errors import InputError

MAX_BYTES = 3_000_000
MAX_SECONDS = 60
RATE = 16000  # what the speech model wants
MAX_TEXT = 4000

ERR_OFF = "Voice notes are not switched on here. Send the text or a screenshot instead."
ERR_BIG = "That voice note is too big. Send a shorter one."
ERR_LONG = "That voice note is too long. Send one under a minute."
ERR_TYPE = "That is not a voice note I can play. Send an audio recording."
ERR_BAD = "I couldn't play that voice note. Try recording it again."
ERR_EMPTY = "I couldn't hear any words in that voice note. Try again, a bit closer to the microphone."
ERR_MODEL = "The voice reader could not start. Send the text or a screenshot instead."


@dataclass
class Transcript:
    text: str
    language: str = ""  # detected language (en, zh, ms, ...)
    seconds: float = 0.0


def available() -> bool:
    """True when server-side speech to text is installed and enabled. Never downloads anything."""
    return os.getenv("BAITPROOF_STT", "1") != "0" and importlib.util.find_spec("faster_whisper") is not None


# ---------------------------------------------------------------- the model: one instance, loaded once
_lock = threading.Lock()
_model = None
_model_name = ""


def model_name() -> str:
    return os.getenv("BAITPROOF_STT_MODEL", "base").strip() or "base"


def _load():
    """The cached model (the caller holds the lock). Downloads it on the first use, then reads it from the local cache."""
    global _model, _model_name
    name = model_name()
    if _model is None or _model_name != name:
        from faster_whisper import WhisperModel

        try:  # already on this machine: no network check, loads in well under a second
            _model = WhisperModel(name, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:  # not downloaded yet (or not a model name): fetch it, once
            _model = WhisperModel(name, device="cpu", compute_type="int8")
        _model_name = name
    return _model


def warmup() -> None:
    """Load the model in the background at server start, so the first voice note does not wait for it (and, the first time ever, for the download)."""
    if not available():
        return

    def go() -> None:
        t0 = time.perf_counter()
        ok = True
        try:
            with _lock:
                _load()
        except Exception:
            ok = False
        obs.emit({"kind": "system", "event": "stt_warmup", "model": model_name(), "ok": ok, "ms": int((time.perf_counter() - t0) * 1000)})

    threading.Thread(target=go, daemon=True).start()


# ---------------------------------------------------------------- decoding
def sniff(data: bytes) -> str | None:
    """The container (PyAV format name) from the first bytes, or None for anything we do not expect."""
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska,webm"
    if data[4:8] == b"ftyp":
        return "mov,mp4,m4a,3gp,3g2,mj2"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"FORM" and data[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def decode(data: bytes, fmt: str):
    """Mono float32 audio at 16 kHz and its length in seconds. Raises InputError (unreadable, too_long)."""
    import av
    import numpy as np

    limit = int((MAX_SECONDS + 0.5) * RATE)
    parts, n = [], 0
    try:
        with av.open(io.BytesIO(data), mode="r", format=fmt) as box:
            if not box.streams.audio:
                raise InputError("bad_type", ERR_TYPE)
            resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
            frames = box.decode(box.streams.audio[0])
            done = False
            while not done:
                try:
                    frame = next(frames)
                    out = resampler.resample(frame)
                except StopIteration:
                    out, done = resampler.resample(None), True  # flush what the resampler still holds
                for f in out:
                    a = f.to_ndarray().reshape(-1)
                    n += a.size
                    if n > limit:
                        raise InputError("too_long", ERR_LONG)  # stop at once: we never decode an hour of audio
                    parts.append(a)
    except InputError:
        raise
    except Exception:  # corrupt, truncated, or not audio after all
        raise InputError("unreadable", ERR_BAD) from None
    if not parts or n < RATE // 10:
        raise InputError("no_text", ERR_EMPTY)
    return np.concatenate(parts).astype(np.float32) / 32768.0, n / RATE


# ---------------------------------------------------------------- the words
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff]")
_PROMPTS = {"zh": "以下是普通话的句子。", "zh-Hant": "以下是普通話的句子。"}  # nudges the model towards the script the user reads


def _hint(lang_hint: str) -> tuple[str | None, str]:
    """(the language to tell the model, the script to return): only English, Chinese, Malay and Tamil are hinted; anything else is left to detection."""
    h = (lang_hint or "").strip().lower().replace("_", "-")
    if h.startswith("zh") or h in ("cn", "chinese"):
        return "zh", i18n.norm(h)
    if h in ("en", "ms", "ta") or h.startswith(("en-", "ms-", "ta-")):
        return h[:2], ""
    return None, ""


def to_script(text: str, script: str) -> str:
    """Chinese text in one script: "zh" (Simplified) or "zh-Hant" (Traditional). Whichever the model wrote, Traditional is made from Simplified."""
    simplified = L.to_simplified(text)
    return i18n.to_traditional(simplified) if script == "zh-Hant" else simplified


def transcribe(data: bytes, *, mime: str = "", lang_hint: str = "") -> Transcript:
    """bytes of ogg/opus, webm, m4a, mp3 or wav -> the words. Raises InputError (too_big, bad_type, too_long, unreadable, no_text, unavailable).
    `lang_hint` (en, zh, zh-Hant, ms) is the language the user expects; for Chinese the answer is written in that script."""
    t0 = time.perf_counter()
    data = bytes(data or b"")
    stats = {"kind": "input", "input": "audio", "bytes": len(data), "ok": False}
    try:
        if not available():
            raise InputError("unavailable", ERR_OFF)
        out = _transcribe(data, mime, lang_hint, stats)
        stats["ok"] = True
        return out
    except InputError as e:
        stats["code"] = e.code
        raise
    finally:  # one small event: sizes and timing only, never the audio or the words
        stats["ms"] = int((time.perf_counter() - t0) * 1000)
        obs.emit(stats)


def _transcribe(data: bytes, mime: str, lang_hint: str, stats: dict) -> Transcript:
    from core.pipelines.check.links import from_speech

    if len(data) > MAX_BYTES:
        raise InputError("too_big", ERR_BIG)
    major = (mime or "").split("/")[0].strip().lower()
    if major and major not in ("audio", "video", "application"):  # a browser says video/webm for a recording with no picture
        raise InputError("bad_type", ERR_TYPE)
    fmt = sniff(data)
    if fmt is None:
        raise InputError("bad_type", ERR_TYPE)
    audio, seconds = decode(data, fmt)
    stats["seconds"] = round(seconds, 1)
    lang, script = _hint(lang_hint)
    try:
        with _lock:  # one at a time: a CPU model, and the machine is small
            model = _load()
            segments, info = model.transcribe(audio, language=lang, beam_size=5, vad_filter=True, condition_on_previous_text=False,
                                              initial_prompt=_PROMPTS.get(script) if lang == "zh" else None)
            heard = [s.text.strip() for s in segments if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0)]  # silence the model "hears" words in
    except InputError:
        raise
    except Exception:  # no model on disk and no way to fetch it, out of memory, ...
        raise InputError("unavailable", ERR_MODEL) from None
    text = _CONTROL.sub("", " ".join(h for h in heard if h)).strip()
    detected = (getattr(info, "language", "") or "").lower()
    if text and script in ("zh", "zh-Hant") and L.CJK.search(text):
        text = to_script(text, script)  # the script the user reads, whichever one the model chose
    text = from_speech(text)[:MAX_TEXT]
    if not text:
        raise InputError("no_text", ERR_EMPTY)
    stats["language"] = detected
    return Transcript(text=text, language=detected, seconds=round(seconds, 1))
