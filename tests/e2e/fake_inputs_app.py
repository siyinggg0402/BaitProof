"""The website with its two readers replaced by canned ones, so the browser test (and anyone who wants to look at the screens) can walk the whole
screenshot and voice flows without the AI or a speech model. The checks themselves still run the offline rules.
Run:  NEBIUS_API_KEY= python -m uvicorn tests.e2e.fake_inputs_app:app --port 8772        (never with a real key: nothing here stops a live call)

Which canned answer a screenshot gets depends on its width in pixels, so a test chooses by how it draws the picture:
  200 the DHL parcel scam with a link        201 the same with a QR code        202 too blurry to trust        203 no message found        204 cannot be opened
  205 the parcel scam, but slowly (a few seconds, to see the 'reading' state)
Anything else is the plain parcel scam. A voice note is heard as one canned sentence per language hint (en, ms, zh)."""
from __future__ import annotations

import io
import time
from types import SimpleNamespace

from PIL import Image

from core.domain.schemas import LinkInfo
from core.inputs import audio, image
from core.inputs.errors import InputError
from core.lang import i18n
from core.pipelines import check as check_pipeline
from web.routes import inputs as input_routes

PARCEL = "DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours or it will be returned. Pay now: dhl-fee-pay.xyz/track"
VOICE = {"en": "Hi grandma, it's me. I'm in trouble and need four gift cards today. Please don't tell Mom.",
         "ms": "Helo nenek, ini saya. Saya dalam masalah dan perlukan kad hadiah hari ini. Jangan beritahu ibu.",
         "zh": "奶奶，是我。我出事了，今天急需四张礼品卡，请不要告诉妈妈。"}
NOTES = {  # English key -> Simplified Chinese (the real notes live in core/lang/i18n_inputs.py; these only exist for this fake)
    "There is a QR code in this picture. Do not scan it.": "图里有一个二维码，请不要扫它。",
    "The link was hard to read. Please check it before you trust it.": "链接看不清楚，请先核对一下再相信它。",
    "I couldn't find a message in that picture. Try a clearer screenshot, or paste the text instead.": "我在这张图里没找到消息。请换一张更清楚的截图，或者直接粘贴文字。",
    "I couldn't open that picture. Please try another screenshot.": "我打不开这张图片。请换一张截图试试。",
}
i18n.ZH.update(NOTES)
LINK_TEXT = {  # (label, notes) per language for the demo links panel
    "en": {"dhl.com": ("This is DHL's real website", ["Online for 27 years"]), "dhl-fee-pay.xyz": ("Looks like DHL but isn't", ["Registered 3 days ago", "Not a DHL address"]),
           "bit.ly": ("A short link hides where it really goes", [])},
    "zh": {"dhl.com": ("这是 DHL 的官方网站", ["已存在 27 年"]), "dhl-fee-pay.xyz": ("看起来像 DHL，其实不是", ["3 天前才注册", "不是 DHL 的网址"]), "bit.ly": ("短链接会藏起真正的去处", [])},
}


def read_image(data: bytes, *, lang: str = "en") -> image.ImageReading:
    width = Image.open(io.BytesIO(data)).size[0]
    if width == 205:
        time.sleep(2.5)
    if width == 203:
        raise InputError("no_text", "I couldn't find a message in that picture. Try a clearer screenshot, or paste the text instead.")
    if width == 204:
        raise InputError("unreadable", "I couldn't open that picture. Please try another screenshot.")
    if width == 202:
        return image.ImageReading(text="DHL: Your parcel is on hold. Pay the fee: dh1-fee-pay.x?z", legible=False, note="The link was hard to read. Please check it before you trust it.")
    if width == 201:
        return image.ImageReading(text=PARCEL, sender="DHL", language="en", links=["dhl-fee-pay.xyz/track"], qr_urls=["https://dhl-fee-pay.xyz/qr"],
                                  note="There is a QR code in this picture. Do not scan it.")
    return image.ImageReading(text=PARCEL, sender="DHL", language="en", links=["dhl-fee-pay.xyz/track"])


def transcribe(data: bytes, *, mime: str = "", lang_hint: str = "") -> audio.Transcript:
    return audio.Transcript(text=VOICE.get(lang_hint, VOICE["en"]), language=lang_hint or "en", seconds=5.0)


image.read_image, audio.transcribe = read_image, transcribe
image.available = audio.available = lambda: True
audio.warmup = lambda: None  # the real one would load a speech model in the background
input_routes.llm = SimpleNamespace(available=lambda: True)  # only the capabilities answer: the checks keep using the real (offline) setting

_real_check = check_pipeline.check_message


def check_with_links(*args, **kw):
    """The offline rules do not look links up yet in every setup, so show a result that has three (an official one, a lookalike and a short one)."""
    r = _real_check(*args, **kw)
    if not r.links and "dhl-fee-pay" in (args[0] if args else kw.get("text", "")):
        text = LINK_TEXT["zh" if r.lang.startswith("zh") else "en"]
        r.links = [LinkInfo(host="dhl.com", status="official", label=text["dhl.com"][0], notes=text["dhl.com"][1], age_days=9900),
                   LinkInfo(host="dhl-fee-pay.xyz", status="lookalike", label=text["dhl-fee-pay.xyz"][0], notes=text["dhl-fee-pay.xyz"][1], age_days=3),
                   LinkInfo(host="bit.ly", status="shortener", label=text["bit.ly"][0], notes=text["bit.ly"][1], expanded_to="parcel-claim.top")]
    return r


check_pipeline.check_message = check_with_links

from web.main import app  # noqa: E402,F401  (imported last, after the fakes are in place)
