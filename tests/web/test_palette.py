"""The colours: each part of the site has its own accent (Check purple, Train teal, Friends rose, Records blue, the House amber), every accent keeps its text readable in
the light and the dark look, and the soft light behind the page mixes different hues instead of three shades of one."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web import deps
from web.main import app

CSS = Path(__file__).resolve().parents[2] / "web" / "static" / "css"
ACCENTS = ("violet", "teal", "rose", "blue", "sun")


def lum(h: str) -> float:
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def tokens(block: str) -> dict[str, str]:
    out = {}
    for name, value in re.findall(r"--([\w-]+):(#[0-9A-Fa-f]{3,6})\b", block):
        out[name] = "#" + "".join(c * 2 for c in value[1:]) if len(value) == 4 else value
    return out


def blocks():
    """{(accent, 'light'|'dark'): tokens} read from palette.css."""
    css = (CSS / "palette.css").read_text()
    dark_start = css.index("@media (prefers-color-scheme:dark){\n  :root{")
    dark_end = css.index("\n}\n", dark_start)
    light, dark = css[:dark_start], css[dark_start:dark_end]
    out = {}
    for name in ACCENTS:
        sel = rf":root\[data-accent={name}\]\{{([^}}]*)\}}"
        out[(name, "light")] = tokens(re.search(sel, light).group(1)) if name != "violet" else tokens(re.search(r":root,:root\[data-accent=violet\]\{([^}]*)\}", light).group(1))
        out[(name, "dark")] = tokens(re.search(sel, dark).group(1)) if name != "violet" else tokens(re.search(r":root,:root\[data-accent=violet\]\{([^}]*)\}", dark).group(1))
    return out


BASE = {"light": tokens(re.search(r"\n:root\{([^}]*)\}", (CSS / "palette.css").read_text()).group(1)), "dark": None}
BLOCKS = blocks()


@pytest.mark.parametrize("accent", ACCENTS)
@pytest.mark.parametrize("look", ["light", "dark"])
def test_every_accent_keeps_its_text_readable(accent, look):
    t = BLOCKS[(accent, look)]
    bg = BASE["light"]["bg"] if look == "light" else "#100E16"
    soft_text = contrast(t["brand-deep"], t["brand-soft"])
    assert contrast(t["brand-ink"], t["brand"]) >= 4.5, "the words on a button"
    assert contrast(t["brand-ink"], t["brand-hover"]) >= 4.5, "the words on a hovered button"
    assert soft_text >= 4.5, "a chip's words on its soft fill"
    assert contrast(t["brand"], bg) >= 4.5, "a link on the page"


def test_the_background_light_uses_different_hues_not_three_shades_of_one():
    for accent in ACCENTS:
        t = BLOCKS[(accent, "light")]
        hues = {}
        for name in ("brand", "violet", "cyan"):
            h = t[name].lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
            mx, mn = max(r, g, b), min(r, g, b)
            d = mx - mn
            hue = 0 if d == 0 else (60 * (((g - b) / d) % 6) if mx == r else 60 * ((b - r) / d + 2) if mx == g else 60 * ((r - g) / d + 4))
            hues[name] = hue
        pairs = [abs(a - b) for a, b in (("brand", "violet"), ("brand", "cyan"), ("violet", "cyan")) for a, b in [(hues[a], hues[b])]]
        assert min(min(d, 360 - d) for d in pairs) > 25, (accent, hues)       # (every pair is a different colour, not a lighter or darker one)


def test_the_page_base_is_a_calm_neutral_not_a_tinted_purple():
    base = BASE["light"]
    assert base["bg"].lower() == "#fbfaf8" and base["surface"].lower() == "#ffffff"
    r, g, b = (int(base["bg"][i:i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) - min(r, g, b) < 12 and contrast(base["ink"], base["bg"]) > 14 and contrast(base["muted"], base["bg"]) >= 4.5


SECTIONS = {"/": "violet", "/train": "teal", "/game": "teal", "/road": "teal", "/link": "teal", "/duel": "teal", "/friends": "rose", "/me": "rose",
            "/signin": "rose", "/family": "rose", "/records": "blue", "/house": "sun"}


@pytest.mark.parametrize("path, accent", list(SECTIONS.items()))
def test_each_part_of_the_site_wears_its_own_accent(path, accent):
    deps.HITS.clear()
    html = TestClient(app).get(path).text
    assert re.search(rf'<html lang="[^"]+" data-accent="{accent}">', html), path
    assert "/static/css/palette.css" in html and html.index("/static/css/palette.css") > html.index("/static/css/polish.css")      # (the palette has the last word on the colours)


def test_the_logo_and_the_mascot_stay_purple_whatever_the_accent():
    css = (CSS / "palette.css").read_text()
    assert ".brand svg rect{fill:#7A5CD0}" in css and "#B7A0F3" in (CSS / "mascot.css").read_text()


def test_the_games_each_have_their_own_colour_on_the_train_page():
    html = TestClient(app).get("/train").text
    games = html[html.index('id="games"'):html.index('id="practice"')]
    accents = re.findall(r'class="gm [^"]* acc-(\w+)"', games)
    assert len(accents) == 6 and len(set(accents)) >= 4 and set(accents) <= set(ACCENTS)
    assert 'acc-sun' in html[:html.index('id="games"')]   # and the house above them wears its own


def test_the_ripples_are_gentler_than_they_were():
    js = (CSS.parent / "js" / "ripple.js").read_text()
    assert "CALM = 0.5" in js and "MAX = 8" in js and "LIFE = 3.0" in js and "amp * CALM" in js
    assert "d > 150 && dt > 240" in js and "setTimeout(ambient, 7000" in js
    fx = (CSS.parent / "js" / "fx.js").read_text()
    assert "* 5).toFixed" in fx and ", 0.8);" in fx and "rgba(255,255,255,.26)" in (CSS / "polish.css").read_text()
