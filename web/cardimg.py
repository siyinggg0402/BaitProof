"""Server-rendered share-card image (1200x630). Pillow only, no design project (PLAN §5)."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

BG, FG, ACCENT, MUTED = (16, 20, 27), (242, 245, 250), (108, 156, 255), (180, 189, 204)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1: scalable built-in font
    except TypeError:
        return ImageFont.load_default()


def render(pct: int, right: int, total: int) -> bytes:
    img = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1200, 14], fill=ACCENT)
    d.text((70, 70), "Baitproof", font=_font(56), fill=ACCENT)
    d.text((70, 190), f"{pct}%", font=_font(260), fill=FG)
    d.text((70, 480), f"I spotted {right} of {total} scam messages.", font=_font(48), fill=FG)
    d.text((70, 550), "Can you beat me?", font=_font(40), fill=MUTED)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
