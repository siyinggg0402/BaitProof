"""The website's other ways in (a screenshot, a voice note), the links panel and the source chip. The readers themselves are replaced by fakes here
(their own tests live with core/inputs); what is tested is the web layer around them: the endpoints, the size limits, the translated errors, the
privacy promises (nothing stored, nothing logged, no temporary file) and what the page shows."""
import asyncio
import io
import re
import struct
import tempfile
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import core.inputs as core_inputs
from core.ai import llm
from core.domain.schemas import CheckResult, Evidence, LinkInfo, Verdict
from core.inputs import audio, image
from core.inputs.errors import CODES, InputError
from core.inputs.image import ImageReading
from core.lang import i18n
from core.pipelines import check as check_pipeline
from core.storage import history
from web import deps, results, ui, uploads
from web.main import app
from web.routes import inputs as routes

ROOT = Path(__file__).resolve().parents[2]
CJK = re.compile(r"[一-鿿]")
MARK = "ZEBRA-UNICORN-4242"  # a made-up word that must never be stored or logged
SCAM = "Pay with gift cards today or you will be arrested. IRS notice."


def png(extra: bytes = b"") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (12, 12), "white").save(out, "PNG")
    return out.getvalue() + extra


def lang_client(code: str = "en") -> TestClient:
    deps.HITS.clear()
    c = TestClient(app)
    c.cookies.set("lang", code)
    return c


def files(data: bytes, name: str = "shot.png", mime: str = "image/png", **fields) -> dict:
    return {"file": (name, data, mime), **{k: (None, v) for k, v in fields.items()}}


@pytest.fixture
def client():
    return lang_client("en")


@pytest.fixture
def seen(monkeypatch):
    """Replace both readers with fakes that remember what they were given."""
    got: dict = {}

    def fake_image(data, *, lang="en"):
        got["image"] = (data, lang)
        return ImageReading(text="Your parcel is on hold. Pay the $1.99 fee: dhl-fee-pay.xyz/track", sender="DHL", language="en", links=["dhl-fee-pay.xyz/track"],
                            qr_urls=["https://qr.example/pay"], legible=True, note="")

    def fake_audio(data, *, mime="", lang_hint=""):
        got["audio"] = (data, mime, lang_hint)
        return audio.Transcript(text="Hello grandma, it is me. I need gift cards.", language="en", seconds=4.2)

    monkeypatch.setattr(image, "read_image", fake_image)
    monkeypatch.setattr(audio, "transcribe", fake_audio)
    return got


# ------------------------------------------------------------------------------------------------ what this server can do
@pytest.mark.parametrize("image_on, audio_on, ai_on, want", [
    (True, True, True, {"image": True, "audio": True}),
    (True, False, True, {"image": True, "audio": False}),
    (True, True, False, {"image": False, "audio": True}),  # reading a screenshot also needs the AI
    (False, False, True, {"image": False, "audio": False}),
])
def test_capabilities(client, monkeypatch, image_on, audio_on, ai_on, want):
    monkeypatch.setattr(core_inputs, "capabilities", lambda: {"image": image_on, "audio": audio_on})
    monkeypatch.setattr(llm, "available", lambda: ai_on)
    r = client.get("/api/capabilities")
    assert r.status_code == 200 and r.json() == want and r.headers["cache-control"] == "no-store"


def home(client, monkeypatch, image_on, audio_on, ai_on=True):
    monkeypatch.setattr(core_inputs, "capabilities", lambda: {"image": image_on, "audio": audio_on})
    monkeypatch.setattr(llm, "available", lambda: ai_on)
    return client.get("/").text


def test_the_home_page_shows_only_the_controls_the_server_can_run(client, monkeypatch):
    both = home(client, monkeypatch, True, True)
    assert 'id="shot-btn"' in both and "We don&#39;t keep the picture" in both and "is turned into text on our server" in both and 'data-audio="1"' in both
    assert 'accept="image/*"' in both and 'id="speak-btn"' in both and "Baitproof never receives the audio" in both
    none = home(client, monkeypatch, False, False)
    assert 'id="shot-btn"' not in none and "We don&#39;t keep the picture" not in none and "on our server" not in none and 'data-audio="0"' in none
    assert 'id="speak-btn"' in none and "Baitproof never receives the audio" in none  # the browser's own speech service is the script's call
    off = home(client, monkeypatch, True, False, ai_on=False)  # no AI: no screenshot button, whatever the reader says
    assert 'id="shot-btn"' not in off
    # every control starts hidden, so a page without scripts never shows a dead button
    assert re.search(r'id="inputs"[^>]*\bhidden\b', none) and re.search(r'id="speak-btn" hidden', none) and re.search(r'id="priv-browser" hidden', none)


def test_the_speak_language_choice_is_for_english_pages_only(monkeypatch):
    c = lang_client("en")
    assert 'id="speak-lang"' in home(c, monkeypatch, False, False) and "Bahasa Melayu" in c.get("/").text
    zh = lang_client("zh")
    page = zh.get("/").text
    assert 'id="speak-lang"' not in page and "<option value=\"ms-MY\">" not in page  # (Bahasa Melayu is in the language menu now, but the speech choice stays English-pages-only)


def test_the_form_remembers_how_the_message_arrived(client):
    assert 'name="source" id="source" value="text"' in client.get("/").text
    page = client.post("/check", data={"message": SCAM, "source": "screenshot"}).text
    assert 'name="source" id="source" value="screenshot"' in page and "Read from a screenshot" in page


def test_the_screenshots_app_and_sender_travel_with_the_check_and_come_back_as_a_line_on_the_result(client, monkeypatch):
    from core.pipelines import check as pipeline
    got = {}
    real = pipeline.check_message

    def spy(text, **kw):
        got.update(kw)
        return real(text, **kw)
    monkeypatch.setattr(pipeline, "check_message", spy)
    page = client.post("/check", data={"message": SCAM, "source": "screenshot", "origin_channel": "app", "origin_app": "Tomoro Coffee", "origin_sender": ""}).text
    assert got["origin"].app == "Tomoro Coffee" and got["origin"].channel == "app"
    assert "Where it came from: a screen inside Tomoro Coffee" in page
    got.clear()
    client.post("/check", data={"message": SCAM, "source": "text", "origin_app": "Tomoro Coffee"})
    assert "origin" not in got  # only a screenshot reports where it came from; a typed message cannot claim it
    got.clear()
    client.post("/check", data={"message": SCAM, "source": "screenshot", "origin_channel": "carrier pigeon"})
    assert "origin" not in got  # nothing usable left after cleaning


# ------------------------------------------------------------------------------------------------ reading a screenshot
def test_a_screenshot_is_read_and_returned_for_the_person_to_check(client, seen):
    r = client.post("/api/read/image", files=files(png()))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"text": "Your parcel is on hold. Pay the $1.99 fee: dhl-fee-pay.xyz/track", "sender": "DHL", "channel": "", "app": "", "language": "en", "links": ["dhl-fee-pay.xyz/track"],
                        "qr_urls": ["https://qr.example/pay"], "legible": True, "note": ""}
    data, lang = seen["image"]
    assert data == png() and lang == "en"  # the bytes arrive untouched, with the visitor's language


def test_the_note_is_translated_and_an_unreadable_picture_is_flagged(monkeypatch):
    monkeypatch.setitem(i18n.ZH, "The link was hard to read: please check it.", "链接看不清楚：请核对一下。")
    monkeypatch.setattr(image, "read_image", lambda data, *, lang="en": ImageReading(text="Pay now: dh1.xyz", legible=False, note="The link was hard to read: please check it."))
    en = lang_client("en").post("/api/read/image", files=files(png())).json()
    zh = lang_client("zh").post("/api/read/image", files=files(png())).json()
    hant = lang_client("zh-Hant").post("/api/read/image", files=files(png())).json()
    assert en["legible"] is False and en["note"] == "The link was hard to read: please check it."
    assert zh["note"] == "链接看不清楚：请核对一下。" and hant["note"] == "連結看不清楚：請核對一下。"


@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("lang", ["en", "zh", "zh-Hant"])
def test_every_input_error_becomes_a_translated_message(monkeypatch, code, lang):
    msg = f"Test message for {code}."
    monkeypatch.setitem(i18n.ZH, msg, f"测试：{code}。")

    def boom(data, **kw):
        raise InputError(code, msg)

    monkeypatch.setattr(image, "read_image", boom)
    monkeypatch.setattr(audio, "transcribe", boom)
    for url in ("/api/read/image", "/api/read/audio"):
        r = lang_client(lang).post(url, files=files(b"x" * 30))
        assert r.status_code == routes.STATUS[code], (url, code)
        assert r.json() == {"detail": {"en": msg, "zh": f"测试：{code}。", "zh-Hant": f"測試：{code}。"}[lang], "code": code}
        assert r.headers["cache-control"] == "no-store"


def test_the_statuses_are_what_a_browser_and_a_proxy_expect():
    assert routes.STATUS == {"too_big": 413, "bad_type": 415, "unreadable": 422, "no_text": 422, "unavailable": 503, "too_long": 413}
    assert set(routes.STATUS) == set(CODES)


def test_with_the_ai_off_the_real_reader_says_so_in_the_visitors_language():
    """The stub or the real reader, with no AI configured: a clear 503 in the right language, never a crash."""
    for lang, word in (("en", "AI"), ("zh", "AI")):
        r = lang_client(lang).post("/api/read/image", files=files(png()))
        assert r.status_code == 503 and r.json()["code"] == "unavailable" and word in r.json()["detail"]
    assert CJK.search(lang_client("zh").post("/api/read/image", files=files(png())).json()["detail"])


def test_an_unexpected_failure_is_a_clean_message_and_logs_only_the_kind(monkeypatch, tmp_path):
    def boom(data, *, lang="en"):
        raise RuntimeError(f"secret {MARK}")

    monkeypatch.setattr(image, "read_image", boom)
    r = lang_client("en").post("/api/read/image", files=files(png()))
    assert r.status_code == 422 and r.json()["code"] == "unreadable" and MARK not in r.text
    log = "".join(p.read_text() for p in (tmp_path / "logs").glob("*") if p.is_file())
    assert "RuntimeError" in log and MARK not in log


def bomb() -> bytes:
    """A 41-byte-header PNG that claims to be 100000 x 100000 pixels: what a decompression bomb looks like before anything is decoded."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 100_000, 100_000, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00" * 64)) + chunk(b"IEND", b"")


def test_a_decompression_bomb_gets_an_error_not_a_crash(monkeypatch, tmp_path):
    def naive_reader(data, *, lang="en"):  # what any reader built on Pillow does first
        Image.open(io.BytesIO(data)).load()
        return ImageReading(text="never reached")

    assert len(bomb()) < 200
    monkeypatch.setattr(image, "read_image", naive_reader)
    r = lang_client("en").post("/api/read/image", files=files(bomb()))
    assert r.status_code == 422 and r.json()["code"] == "unreadable" and "never reached" not in r.text
    assert "DecompressionBombError" in "".join(p.read_text() for p in (tmp_path / "logs").glob("*") if p.is_file())


def test_a_file_that_is_not_a_picture_is_the_readers_call(client, monkeypatch):
    seen_bytes = []

    def strict(data, *, lang="en"):
        seen_bytes.append(data)
        raise InputError("bad_type", "That doesn't look like a picture.")

    monkeypatch.setattr(image, "read_image", strict)
    r = client.post("/api/read/image", files=files(b"%PDF-1.7 not a picture", "doc.pdf", "application/pdf"))
    assert r.status_code == 415 and r.json()["code"] == "bad_type" and seen_bytes == [b"%PDF-1.7 not a picture"]


# ------------------------------------------------------------------------------------------------ a voice note
def test_a_voice_note_is_turned_into_text(client, seen):
    r = client.post("/api/read/audio", files=files(b"OggS-pretend", "voice.webm", "audio/webm;codecs=opus", lang="ms"))
    assert r.status_code == 200 and r.json() == {"text": "Hello grandma, it is me. I need gift cards.", "language": "en", "seconds": 4.2}
    assert seen["audio"] == (b"OggS-pretend", "audio/webm", "ms")  # the type (without its parameters) and the language hint reach the transcriber


@pytest.mark.parametrize("hint, want", [("en", "en"), ("zh-TW", "zh-TW"), ("", ""), ("x; DROP TABLE", ""), ("a" * 40, ""), ("e", "")])
def test_the_language_hint_is_checked(client, seen, hint, want):
    client.post("/api/read/audio", files=files(b"abc", "v.webm", "audio/webm", lang=hint))
    assert seen["audio"][2] == want


def test_voice_notes_are_off_unless_the_server_can_transcribe(client, monkeypatch):
    def off(data, **kw):
        raise InputError("unavailable", "Voice notes are not switched on here. Send the text or a screenshot instead.")

    monkeypatch.setattr(audio, "transcribe", off)
    r = client.post("/api/read/audio", files=files(b"abc", "v.webm", "audio/webm"))
    assert r.status_code == 503 and r.json()["code"] == "unavailable"
    zh = lang_client("zh").post("/api/read/audio", files=files(b"abc", "v.webm", "audio/webm"))
    assert zh.status_code == 503 and CJK.search(zh.json()["detail"])


# ------------------------------------------------------------------------------------------------ size limits and odd uploads
def test_an_oversize_upload_is_refused_and_never_reaches_the_reader(client, seen, monkeypatch):
    monkeypatch.setattr(image, "MAX_BYTES", 2000)
    ok = client.post("/api/read/image", files=files(b"a" * 2000))
    assert ok.status_code == 200
    seen.clear()
    r = client.post("/api/read/image", files=files(b"a" * 2001))
    assert r.status_code == 413 and r.json()["code"] == "too_big" and "too big" in r.json()["detail"] and "image" not in seen
    zh = lang_client("zh").post("/api/read/image", files=files(b"a" * 5000))
    assert zh.status_code == 413 and CJK.search(zh.json()["detail"])


def test_the_real_limits_hold_for_a_screenshot_and_a_voice_note(client, seen):
    assert client.post("/api/read/image", files=files(b"a" * (image.MAX_BYTES + 1))).status_code == 413
    assert client.post("/api/read/audio", files=files(b"a" * (audio.MAX_BYTES + 1), "v.webm", "audio/webm")).status_code == 413
    assert "image" not in seen and "audio" not in seen
    msg = client.post("/api/read/audio", files=files(b"a" * (audio.MAX_BYTES + 1), "v.webm", "audio/webm")).json()["detail"]
    assert "voice note" in msg


def multipart(body: bytes) -> tuple[bytes, dict]:
    b = "----testboundary"
    head = f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="s.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
    return head + body + f"\r\n--{b}--\r\n".encode(), {"content-type": f"multipart/form-data; boundary={b}"}


def test_an_upload_that_lies_about_its_size_is_still_stopped(client, seen, monkeypatch):
    monkeypatch.setattr(image, "MAX_BYTES", 5000)
    body, headers = multipart(b"a" * 400_000)
    lying = client.post("/api/read/image", content=body, headers={**headers, "content-length": "300"})  # says 300 bytes, sends 400 000
    assert lying.status_code == 413 and "image" not in seen
    chunked = client.post("/api/read/image", content=(body[i:i + 8192] for i in range(0, len(body), 8192)), headers=headers)  # no Content-Length at all
    assert chunked.status_code == 413 and "image" not in seen
    honest = client.post("/api/read/image", content=body, headers=headers)  # Content-Length says so up front
    assert honest.status_code == 413 and "image" not in seen


def fake_request(chunks, content_type, length=None):
    pulled = []

    async def stream():
        for c in chunks:
            pulled.append(len(c))
            yield c

    headers = {"content-type": content_type, **({"content-length": str(length)} if length is not None else {})}
    return SimpleNamespace(headers=headers, stream=stream), pulled


def test_the_body_is_cut_off_the_moment_the_file_passes_the_limit():
    """Memory stays bounded and the rest of the upload is never read: a gigabyte of chunks is abandoned after the first few."""
    body, headers = multipart(b"a" * 50_000_000)
    chunks = (body[i:i + 65536] for i in range(0, len(body), 65536))
    req, pulled = fake_request(chunks, headers["content-type"])
    with pytest.raises(uploads.UploadError) as e:
        asyncio.run(uploads.read_upload(req, 100_000))
    assert e.value.reason == "too_big" and sum(pulled) <= 100_000 + 2 * 65536


def test_a_small_upload_parses_with_its_fields_and_the_first_file_only():
    b = "xx"
    body = (f'--{b}\r\nContent-Disposition: form-data; name="lang"\r\n\r\nms\r\n--{b}\r\nContent-Disposition: form-data; name="other"; filename="o.bin"\r\n\r\nIGNORED\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="v.webm"\r\nContent-Type: Audio/WebM; codecs=opus\r\n\r\nDATA\r\n--{b}--\r\n').encode()
    req, _ = fake_request([body[:30], body[30:90], body[90:]], f"multipart/form-data; boundary={b}")
    up = asyncio.run(uploads.read_upload(req, 1000))
    assert up.data == b"DATA" and up.mime == "audio/webm" and up.fields == {"lang": "ms"}


@pytest.mark.parametrize("kind", ["not_multipart", "no_file", "empty_file", "cut_off"])
def test_a_request_without_a_usable_file_is_a_clear_error(client, seen, kind):
    if kind == "not_multipart":
        r = client.post("/api/read/image", json={"file": "nope"})
    elif kind == "no_file":
        r = client.post("/api/read/image", files={"note": (None, "hello")})
    elif kind == "empty_file":
        r = client.post("/api/read/image", files=files(b""))
    else:
        body, headers = multipart(png())
        r = client.post("/api/read/image", content=body[:-30], headers=headers)  # the closing boundary never came
    assert r.status_code == 422 and r.json()["code"] == "unreadable" and "image" not in seen


# ------------------------------------------------------------------------------------------------ rate limit
def test_reading_is_rate_limited_like_checking(seen, monkeypatch):
    monkeypatch.setattr(deps, "RATE", 3)
    c = lang_client("en")
    codes = [c.post("/api/read/image", files=files(png())).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429] and "image" in seen
    assert lang_client("zh").post("/api/read/audio", files=files(b"abc", "v.webm", "audio/webm")).status_code == 200
    deps.HITS.clear()
    monkeypatch.setattr(deps, "RATE", 1)
    c = lang_client("zh")
    c.post("/api/read/audio", files=files(b"abc", "v.webm", "audio/webm"))
    limited = c.post("/api/read/audio", files=files(b"abc", "v.webm", "audio/webm"))
    assert limited.status_code == 429 and CJK.search(limited.json()["detail"])


# ------------------------------------------------------------------------------------------------ privacy
def everything_on_disk(tmp_path) -> bytes:
    return b"".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())


def test_nothing_is_stored_or_logged_and_no_temporary_file_is_made(client, monkeypatch, tmp_path):
    secret_text = f"Pay now to {MARK}.example/pay"
    monkeypatch.setattr(image, "read_image", lambda data, *, lang="en": ImageReading(text=secret_text, sender=MARK, links=[f"{MARK}.example/pay"]))
    monkeypatch.setattr(audio, "transcribe", lambda data, *, mime="", lang_hint="": audio.Transcript(text=secret_text))

    def no_temp_file(*a, **k):
        raise AssertionError("an upload must stay in memory")

    for name in ("SpooledTemporaryFile", "TemporaryFile", "NamedTemporaryFile", "mkstemp"):
        monkeypatch.setattr(tempfile, name, no_temp_file)
    import starlette.formparsers as fp

    monkeypatch.setattr(fp, "SpooledTemporaryFile", no_temp_file)
    kept = dict(results._store)
    assert client.post("/api/read/image", files=files(png(MARK.encode()))).status_code == 200
    assert client.post("/api/read/audio", files=files(MARK.encode(), "v.webm", "audio/webm")).status_code == 200
    assert client.post("/api/read/image", files=files(b"a" * (image.MAX_BYTES + 5))).status_code == 413
    assert history.list_checks() == [] and results._store == kept  # no record, no kept result
    disk = everything_on_disk(tmp_path)
    assert MARK.encode() not in disk and MARK.lower().encode() not in disk


def test_the_check_after_a_screenshot_stores_what_a_typed_check_would(client, tmp_path):
    """The record is the same shape as for typed text, and the picture's words are only ever kept as the usual redacted preview."""
    client.post("/check", data={"message": SCAM})
    client.post("/check", data={"message": SCAM, "source": "screenshot"})
    typed, shot = history.list_checks()[1], history.list_checks()[0]
    assert set(typed) == set(shot) and "source" not in shot and typed["verdict"] == shot["verdict"]


# ------------------------------------------------------------------------------------------------ source of the message
def stream_done(c, message, **extra):
    import json

    ids = []
    with c.stream("POST", "/api/check/stream", json={"message": message, **extra}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev["type"] == "done":
                    ids.append(ev["data"])
    return ids[0]


@pytest.mark.parametrize("source, chip", [("screenshot", "Read from a screenshot"), ("voice", "Heard from a voice note"), ("text", None)])
def test_the_result_says_where_the_message_came_from(client, source, chip):
    cid = stream_done(client, SCAM, source=source)
    part = client.get(f"/result/{cid}").text
    text = re.sub(r"<[^>]+>", "", part)
    labels = ("Read from a screenshot", "Heard from a voice note")
    assert (chip in text) if chip else not any(x in text for x in labels)
    assert sum(x in text for x in labels) == (1 if chip else 0)
    assert "SCAM" in text  # the verdict itself does not depend on the source


def test_a_stream_without_a_source_is_a_typed_check(client):
    part = client.get(f"/result/{stream_done(client, SCAM)}").text
    assert 'class="src"' not in part


def test_the_chip_is_translated():
    zh = lang_client("zh")
    assert "从截图中读出的消息" in zh.get(f"/result/{stream_done(zh, SCAM, source='screenshot')}").text
    assert "从语音中听出的消息" in zh.post("/check", data={"message": SCAM, "source": "voice"}).text
    hant = lang_client("zh-Hant")
    assert "從截圖中讀出的訊息" in hant.get(f"/result/{stream_done(hant, SCAM, source='screenshot')}").text


@pytest.mark.parametrize("bad", ["email", "SCREENSHOT2", "../x", "screenshot; drop", "<b>", "a" * 500, "none"])
def test_an_unknown_source_is_refused(client, bad):
    assert client.post("/api/check/stream", json={"message": SCAM, "source": bad}).status_code == 422
    assert client.post("/check", data={"message": SCAM, "source": bad}).status_code == 422
    assert history.list_checks() == []
    zh = lang_client("zh").post("/api/check/stream", json={"message": SCAM, "source": bad}).json()["detail"]
    assert CJK.search(zh)


def test_the_source_is_case_and_space_tolerant_but_still_from_the_allow_list(client):
    assert client.post("/check", data={"message": SCAM, "source": " Screenshot "}).status_code == 200
    assert client.post("/api/check/stream", json={"message": "  ", "source": "voice"}).status_code == 400


def test_the_core_is_told_the_source_when_it_can_take_it(client, monkeypatch):
    calls = []

    def new_core(text, store=True, on_event=None, log=True, lang=None, source="text", read_text=""):
        calls.append((text, source, read_text))
        return CheckResult(verdict=Verdict.UNSURE, headline="❓ Not sure. Treat it with care.", check_id="aabbccddeeff", lang="en", source=source, read_text=read_text)

    monkeypatch.setattr(check_pipeline, "check_message", new_core)
    client.post("/check", data={"message": "hello there", "source": "voice"})
    client.post("/check", data={"message": "hello there"})
    assert calls == [("hello there", "voice", "hello there"), ("hello there", "text", "")]


def test_an_older_core_still_gets_the_chip(client, monkeypatch):
    def old_core(text, store=True, on_event=None, log=True, lang=None):
        return CheckResult(verdict=Verdict.UNSURE, headline="❓ Not sure. Treat it with care.", check_id="aabbccddeeff", lang="en")

    monkeypatch.setattr(check_pipeline, "check_message", old_core)
    page = client.post("/check", data={"message": "hello there", "source": "screenshot"}).text
    assert "Read from a screenshot" in page
    assert "Read from a screenshot" not in client.post("/check", data={"message": "hello there"}).text


# ------------------------------------------------------------------------------------------------ the links panel
def link(host, status, label="", notes=(), expanded_to="", age_days=None):
    return LinkInfo(host=host, status=status, label=label, notes=list(notes), expanded_to=expanded_to, age_days=age_days)


LINKS = [
    link("dhl.com", "official", "This is DHL's real website", ["Registered 25 years ago"], age_days=9000),
    link("dhl-fee-pay.xyz", "lookalike", "Looks like DHL but isn't", ["Registered 3 days ago", "Not a DHL address"], age_days=3),
    link("bit.ly", "shortener", "A short link hides where it goes", expanded_to="parcel-claim.top"),
    link("free-gift.top", "suspicious", "A site that asks for card details"),
    link("example-shop.net", "unverified", "I could not check this one"),
    link("wikipedia.org", "established", "A long-established site", ["Online for 24 years"]),
]


def result_with(links, lang="en", **kw):
    r = CheckResult(verdict=Verdict.SCAM, headline="🚨 SCAM. Don't pay, don't tap the link.", tell="It rushes you.", action="Do not pay.", lang=lang, check_id="0123456789ab", links=links,
                    evidence=[Evidence(kind="rule", source="pattern", supports="scam", strength="strong", claim="It rushes you")], **kw)
    results.put(r)
    return r.check_id


def panel_of(html: str) -> str:
    return re.search(r'<section class="panel links".*?</section>', html, flags=re.S).group(0)


def test_the_links_panel_lists_every_link_with_its_status(client):
    html = client.get(f"/result/{result_with(LINKS)}").text
    panel = panel_of(html)
    assert "Links in this message" in panel and panel.count("<li class=\"lk-") == 6
    for host in ("dhl.com", "dhl-fee-pay.xyz", "bit.ly", "free-gift.top", "example-shop.net", "wikipedia.org"):
        assert f'<code class="lk-host">{host}</code>' in panel
    for chip in ("Official site", "Fake lookalike", "Short link", "Suspicious", "Not verified", "Long-established site"):
        assert chip in panel
    for cls in ("official", "lookalike", "shortener", "suspicious", "unverified", "established"):
        assert f'class="lk-{cls}"' in panel
    assert "Looks like DHL but isn&#39;t" in panel and "Registered 3 days ago" in panel and "Not a DHL address" in panel and "A short link hides where it goes" in panel
    assert 'Really goes to <code class="lk-host">parcel-claim.top</code>' in panel
    assert panel.index("dhl.com") < panel.index("dhl-fee-pay.xyz") < panel.index("bit.ly")  # in the order the message gave them
    assert html.index("The evidence") < html.index("Links in this message") < html.index("How I decided")  # after the evidence, before the trace


def test_a_link_on_the_public_phishing_list_has_its_own_red_chip(client):
    html = client.get(f"/result/{result_with([link('pay-now-parcel.top', 'known_phishing', 'Known phishing website', ['It is on a public list of known phishing websites'])])}").text
    panel = panel_of(html)
    assert 'class="lk-known_phishing"' in panel and "Known phishing site" in panel and "Known phishing website" in panel and "#i-x" in panel
    assert ".lk-known_phishing .lk-chip" in client.get("/static/css/style.css").text  # red, like a lookalike


def test_the_phishing_list_chip_is_translated():
    html = lang_client("zh").get(f"/result/{result_with([link('pay-now-parcel.top', 'known_phishing', '已知的钓鱼网站')], lang='zh')}").text
    assert "已知钓鱼网站" in panel_of(html) and "Known phishing" not in panel_of(html)


def test_links_are_never_clickable(client):
    html = client.get(f"/result/{result_with(LINKS)}").text
    panel = panel_of(html)
    assert "<a " not in panel and not re.search(r'href="(?!#i-)', panel) and "onclick" not in panel   # (the only href is an icon inside the page)
    for host in ("dhl-fee-pay.xyz", "bit.ly", "parcel-claim.top", "free-gift.top"):
        assert not re.search(rf"<a\b[^>]*>[^<]*{re.escape(host)}", html), host
        assert f'href="{host}' not in html and f"//{host}" not in html
    assert "Shown as plain text on purpose" in panel


def test_nothing_is_shown_without_links(client):
    html = client.get(f"/result/{result_with([])}").text
    assert "Links in this message" not in html and 'class="panel links"' not in html


def test_a_hostile_host_or_note_cannot_inject_markup(client):
    evil = link('<img src=x onerror=alert(1)>.com', "weird", '<script>alert(1)</script>', ['"><b>x</b>'], expanded_to="<i>y</i>")
    panel = panel_of(client.get(f"/result/{result_with([evil])}").text)
    assert "<img" not in panel and "<script" not in panel and "<b>x" not in panel and "<i>y" not in panel and "&lt;img" in panel
    assert 'class="lk-unverified"' in panel and "Not verified" in panel  # an unknown status is shown as unverified, and cannot become a class name


def test_the_panel_is_in_chinese_and_traditional():
    zh = panel_of(lang_client("zh").get(f"/result/{result_with(LINKS, lang='zh')}").text)
    for word in ("这条消息里的链接", "官方网站", "假冒网址", "短链接", "可疑", "无法核实", "老牌网站", "实际指向", "不能点"):
        assert word in zh, word
    assert "Links in this message" not in zh and "Official site" not in zh and "Really goes" not in zh
    hant = panel_of(lang_client("zh-Hant").get(f"/result/{result_with(LINKS, lang='zh-Hant')}").text)
    assert "這條訊息裡的連結" in hant and "假冒網址" in hant and "无法" not in hant
    assert "Links in this message" in panel_of(lang_client("en").get(f"/result/{result_with(LINKS)}").text)


def test_a_real_check_shows_links_from_the_pipeline(client, monkeypatch):
    """When the core fills `links`, the page that a check returns shows the panel (the form post and the live view use the same partial)."""
    def with_links(text, store=True, on_event=None, log=True, lang=None, **kw):
        return CheckResult(verdict=Verdict.SCAM, headline="🚨 SCAM. Don't pay, don't tap the link.", tell="t", action="a", check_id="aabbccddee11", lang="en", links=LINKS[:2])

    monkeypatch.setattr(check_pipeline, "check_message", with_links)
    page = client.post("/check", data={"message": "pay at dhl-fee-pay.xyz"}).text
    assert "Links in this message" in page and "Fake lookalike" in page


# ------------------------------------------------------------------------------------------------ headers and strictness
def test_the_microphone_is_ours_alone_and_the_camera_stays_blocked(client):
    h = client.get("/").headers
    policy = {p.split("=")[0].strip(): p.split("=", 1)[1].strip() for p in h["permissions-policy"].split(",")}
    assert policy["microphone"] == "(self)" and policy["camera"] == "()" and policy["geolocation"] == "()"
    for url in ("/", "/train", "/records", "/api/capabilities", "/static/js/inputs.js"):
        assert client.get(url).headers.get("permissions-policy") == h["permissions-policy"], url
    assert "*" not in h["permissions-policy"]


def test_the_csp_allows_only_what_the_page_uses(client):
    csp = {d.split()[0]: d.split()[1:] for d in client.get("/").headers["content-security-policy"].split(";") if d.strip()}
    assert csp["default-src"] == ["'self'"] and csp["script-src"] == ["'self'"] and csp["style-src"] == ["'self'"]
    assert csp["img-src"] == ["'self'", "blob:"] and csp["frame-ancestors"] == ["'none'"]
    assert not {"media-src", "connect-src", "object-src", "worker-src"} & set(csp)  # a recording is uploaded, never played back, so no blob: media
    assert "'unsafe-inline'" not in str(csp) and "'unsafe-eval'" not in str(csp) and "*" not in str(csp)


def test_the_new_page_parts_have_no_inline_script_or_style():
    for name in ("index.html", "_result.html"):
        src = (ROOT / "web/templates" / name).read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)", src) and not re.search(r"\sstyle\s*=", src) and not re.search(r"\son[a-z]+\s*=", src), name
    js = (ROOT / "web/static/js/inputs.js").read_text()
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|setAttribute\(\s*[\"']style", js)  # what the model read is only ever text


def test_the_screenshot_and_voice_script_loads_on_the_home_page_only(client):
    assert "/static/js/inputs.js" in client.get("/").text and "/static/js/inputs.js" not in client.get("/train").text
    assert client.get("/static/js/inputs.js").status_code == 200


# ------------------------------------------------------------------------------------------------ words
def test_every_new_message_has_a_chinese_version():
    for key in (routes.IMAGE_TOO_BIG, routes.AUDIO_TOO_BIG, routes.NO_FILE, routes.FAILED):
        assert key in i18n.ZH, key
    assert ui.tr(routes.IMAGE_TOO_BIG, "zh-Hant") != routes.IMAGE_TOO_BIG
    for text in ("I read this from your screenshot. Check it matches, fix anything wrong, then check it again.", "Reading your screenshot…", "Listening… tap Stop when you are done."):
        assert text in ui.js_keys() and i18n.tr(text, "zh") != text
    assert "正在读取你的截图" in ui.i18n_json("zh") and "正在讀取你的截圖" in ui.i18n_json("zh-Hant")


def test_the_privacy_lines_say_what_happens_to_the_data():
    zh = lang_client("zh")
    page = zh.get("/").text
    assert "Baitproof 收不到你的录音" in page and "AI 会读取你的截图" not in page  # no screenshot line when the AI is off
    lines = {
        "The AI reads your screenshot to get the text. We don't keep the picture.": "我们不会保存这张图片",
        "Your voice note is turned into text on our server and is not kept.": "转完就不留",
        "Your browser's speech service turns your voice into text. Baitproof never receives the audio.": "Baitproof 收不到你的录音",
    }
    for en, zh_part in lines.items():
        assert zh_part in i18n.tr(en, "zh")
