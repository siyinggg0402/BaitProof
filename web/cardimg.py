"""Server-rendered share-card image (1200x630). Pillow only, no design project (PLAN §5).

Chinese needs a font with Chinese glyphs, which Pillow does not ship. We look for one that is installed on the machine (macOS, Windows or Linux)
and use it only if it really has every character we are about to draw; with none, the card is drawn in English instead of showing empty boxes."""
from __future__ import annotations

import glob
import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from core.lang.i18n import norm, tr

BG, FG, ACCENT, MUTED = (16, 20, 27), (242, 245, 250), (108, 156, 255), (180, 189, 204)

# Where a Chinese font usually lives. Patterns are globbed, in this order.
CJK_FONT_PATTERNS = (
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc",   # macOS
    "/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msyh.ttf", "C:/Windows/Fonts/msjh.ttf", "C:/Windows/Fonts/simsun.ttc",  # Windows
    "C:/Windows/Fonts/mingliu.ttc",
    "/usr/share/fonts/**/NotoSansCJK*Regular*.ttc", "/usr/share/fonts/**/NotoSansCJK*.ttc", "/usr/share/fonts/**/NotoSansCJK*.otf",   # Linux
    "/usr/share/fonts/**/NotoSansSC*.[ot]t[fc]", "/usr/share/fonts/**/NotoSansTC*.[ot]t[fc]", "/usr/share/fonts/**/wqy-microhei.ttc",
    "/usr/share/fonts/**/wqy-zenhei.ttc", "/usr/share/fonts/**/DroidSansFallback*.ttf", "/usr/share/fonts/**/unifont*.ttf",
    "/usr/local/share/fonts/**/*CJK*.[ot]t[fc]", "~/.fonts/**/*CJK*.[ot]t[fc]", "~/.local/share/fonts/**/*CJK*.[ot]t[fc]",
)
_FACES_PER_FILE = 24
SIMPLIFIED_HINTS = ("SC", "YaHei", "Simplified", "GB", "CN", "SimSun", "WenQuanYi", "Droid Sans Fallback")  # in order of preference
TRADITIONAL_HINTS = ("TC", "JhengHei", "Traditional", "TW", "MingLiU", "PMingLiU", "HK", "MO")
LIGHT_STYLES = ("Light", "Thin", "W1", "W2", "Ultralight", "ExtraLight")
HEAVY_STYLES = ("Bold", "Black", "Heavy", "Semibold", "W6", "W7", "W8", "W9", "ExtraBold")


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1: scalable built-in font
    except TypeError:
        return ImageFont.load_default()


@lru_cache(maxsize=1)
def _font_files() -> tuple[str, ...]:
    import os

    found: list[str] = []
    for pattern in CJK_FONT_PATTERNS:
        for path in sorted(glob.glob(os.path.expanduser(pattern), recursive=True)):
            if path not in found:
                found.append(path)
    return tuple(found)


def _faces(path: str) -> list[tuple[int, str, str]]:
    """(index, family, style) of each face in a font file (a .ttc holds several: Simplified, Traditional, ...)."""
    out = []
    for i in range(_FACES_PER_FILE):
        try:
            family, style = ImageFont.truetype(path, 20, index=i).getname()
        except Exception:  # past the last face, or an unreadable file
            break
        out.append((i, family or "", style or ""))
    return out


def _rank(family: str, style: str, lang: str) -> int:
    """Higher is better: the right script first, then a regular weight."""
    own, other = (TRADITIONAL_HINTS, SIMPLIFIED_HINTS) if lang == "zh-Hant" else (SIMPLIFIED_HINTS, TRADITIONAL_HINTS)
    words = set(family.replace("-", " ").split())

    def named(hints) -> int | None:  # position of the first hint the family name carries
        return next((i for i, h in enumerate(hints) if h in words or (" " in h and h in family)), None)

    mine, theirs = named(own), named(other)
    score = 20 - mine if mine is not None else -10 if theirs is not None else 0
    if family.startswith("."):  # system-internal faces ('.Hiragino Sans GB Interface')
        score -= 30
    if any(w in style for w in LIGHT_STYLES):
        score -= 2
    elif any(w in style for w in HEAVY_STYLES):
        score -= 1
    return score


def _ink(font, ch: str) -> bytes:
    """The pixels of one character as the font draws it."""
    im = Image.new("L", (90, 90), 0)
    ImageDraw.Draw(im).text((10, 10), ch, font=font, fill=255)
    return im.tobytes()


def has_glyphs(font, text: str) -> bool:
    """True if the font draws every character of `text` (a missing one comes out as the font's empty box, or as nothing)."""
    box, blank = _ink(font, "\uffff"), _ink(font, " ")
    for ch in {c for c in text if not c.isspace()}:
        ink = _ink(font, ch)
        if ink == blank or ink == box:
            return False
    return True


@lru_cache(maxsize=64)
def _cjk_choice(lang: str, text: str) -> tuple[str, int] | None:
    """(path, face index) of an installed font that suits `lang` and can draw all of `text`, or None."""
    for path in _font_files():
        ranked = sorted(_faces(path), key=lambda f: -_rank(f[1], f[2], lang))
        for index, _family, _style in ranked[:6]:
            try:
                if has_glyphs(ImageFont.truetype(path, 40, index=index), text):
                    return path, index
            except Exception:
                continue
    return None


def cjk_font(lang: str, size: int, text: str):
    """A Pillow font for Chinese text in `lang`, or None when this machine has no font that can draw it."""
    choice = _cjk_choice(norm(lang), text)
    return ImageFont.truetype(choice[0], size, index=choice[1]) if choice else None


def _fit(draw: ImageDraw.ImageDraw, text: str, make, size: int, width: int):
    """The font at the largest size (down from `size`) at which `text` fits in `width` pixels."""
    while size > 20:
        f = make(size)
        if draw.textlength(text, font=f) <= width:
            return f
        size -= 2
    return make(20)


def render(pct: int, right: int, total: int, lang: str = "en") -> bytes:
    lang = norm(lang)
    line1 = tr("I spotted {right} of {total} scam messages.", lang, right=right, total=total)
    line2 = tr("Can you beat me?", lang)
    if lang != "en" and cjk_font(lang, 48, line1 + line2) is None:
        lang = "en"  # no installed font can draw it: the English card is better than one full of boxes
        line1, line2 = tr("I spotted {right} of {total} scam messages.", lang, right=right, total=total), tr("Can you beat me?", lang)
    make = _font if lang == "en" else (lambda size: cjk_font(lang, size, line1 + line2))
    img = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1200, 14], fill=ACCENT)
    d.text((70, 70), "Baitproof", font=_font(56), fill=ACCENT)
    d.text((70, 190), f"{pct}%", font=_font(260), fill=FG)
    d.text((70, 480), line1, font=_fit(d, line1, make, 48, 1060), fill=FG)
    d.text((70, 550), line2, font=_fit(d, line2, make, 40, 1060), fill=MUTED)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
