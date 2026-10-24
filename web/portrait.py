"""The flat portrait of a character (the little round picture beside a name), drawn in layers from the look code (core/domain/characters.py). Each layer is a group
in the page's sprite and a portrait is the layers stacked as <use> elements, each filled with its colour: skin, hair, outfit. A path may carry its own colours (the face,
glasses); the rest take the layer's. Only <path> elements are used, so Scam Road can read the same data and draw a portrait on a canvas (look.js)."""
from __future__ import annotations

from markupsafe import Markup

from core.domain import characters as ch

DARK = "#2B1B55"


def _p(d: str, **attrs) -> dict:
    return {"d": d, **attrs}


def _ellipse(cx: float, cy: float, rx: float, ry: float) -> str:
    return f"M{cx - rx:g} {cy:g}a{rx:g} {ry:g} 0 1 0 {2 * rx:g} 0a{rx:g} {ry:g} 0 1 0 {-2 * rx:g} 0"


SHORT = "M20.3 25.5C19.5 16 25 11 32 11s12.5 5 11.7 14.5c-1.4-3.6-3.6-5.6-6-6.6-3.4 2.4-9.2 2.4-12.2.4-2.2 1.4-4.1 3.4-5.2 6.2z"
BOB_FRONT = "M20.5 24.8C20.6 16.5 25.5 11.5 32 11.5s11.4 5 11.5 13.3c-3.8-1.2-8-5.2-11.5-7-3.5 2.6-7.3 5.8-11.5 6z"
CURLY_FRINGE = "M21.4 23.6c1.2-5 5.4-8 10.6-8s9.4 3 10.6 8c-3-1.8-6.2-3.4-10.6-3.4s-7.6 1.6-10.6 3.4z"
BUZZ = "M20.9 24.5c-.2-7.5 4.2-12.4 11.1-12.4s11.3 4.9 11.1 12.4c-2.8-3.4-6.6-5.6-11.1-5.6s-8.3 2.2-11.1 5.6z"
SIDEPART = "M20.3 25.5C19.3 15.8 25 10.6 32.4 10.6s12.2 5.2 11.3 14.9c-1.2-3.4-3-5.4-5.2-6.6-1.6 2.6-5.2 4.4-9.6 4.4-2.8 0-5-.6-6.9-1.8-1.6 1.2-2.8 3.4-3.7 5z"
SPIKY = "M20.4 25.2c-1.3-5.6.2-9.4 2.4-11.4l-1.3-5.2 4.3 2.7 2.1-5.6 3.5 4.5 3.6-4.7 2 5.5 4.4-2.8-.9 5.4c2.3 2 3.8 5.7 2.5 11.6-1.6-3.6-3.8-5.6-6.4-6.6-3.2 2-8.8 2-12 0-2.6 1-4.8 3-7 6.6z"
TUDUNG = ("M10 64c0-13 2.6-22.5 7.5-29.5-2.6-3.6-4-7.8-4-12C13.5 12.3 21 5.5 32 5.5s18.5 6.8 18.5 17c0 4.2-1.4 8.4-4 12C51.4 41.5 54 51 54 64z" + _ellipse(32, 27.5, 10.2, 12))

# symbol id -> the paths it draws
LAYERS: dict[str, list[dict]] = {
    "pt-body": [_p("M7 64c0-9.5 6.5-15.8 15.5-17.6C25 49.5 28.3 51 32 51s7-1.5 9.5-4.6C50.5 48.2 57 54.5 57 64z")],
    "pt-neck": [_p("M28 36h8v9a4 4 0 0 1-8 0z")],
    "pt-head": [_p(_ellipse(32, 27, 11.5, 12.5)), _p(_ellipse(20.6, 28.5, 2.4, 2.4)), _p(_ellipse(43.4, 28.5, 2.4, 2.4))],
    "pt-face": [_p("M27.2 28h.01M36.8 28h.01", fill="none", stroke=DARK, **{"stroke-width": 3}),
                _p("M29 33.2c1.6 1.7 4.4 1.7 6 0", fill="none", stroke=DARK, **{"stroke-width": 1.4})],
    "pt-blush": [_p(_ellipse(24.7, 32.4, 2.1, 1.3) + _ellipse(39.3, 32.4, 2.1, 1.3), fill="#F29BB5", **{"fill-opacity": .5})],
    "pt-brows": [_p("M23.2 25.6c1.6-2 4.3-2.7 6.4-1.7l-.3 1.7c-1.9-.8-3.9-.2-5.5 1.2zM40.8 25.6c-1.6-2-4.3-2.7-6.4-1.7l.3 1.7c1.9-.8 3.9-.2 5.5 1.2z")],
    # facial hair, over the face, in the hair colour (a fantasy hair colour gets a natural brown, see layers_for)
    "pt-fh-stubble": [_p("M21.6 29.5c.4 5.8 4.6 10.3 10.4 10.3s10-4.5 10.4-10.3c-2.6 2.4-6.3 3.6-10.4 3.6s-7.8-1.2-10.4-3.6z", **{"fill-opacity": .38})],
    "pt-fh-moustache": [_p("M26.4 31.8c1.5-1.4 3.4-1.7 5.6-.8 2.2-.9 4.1-.6 5.6.8-1.2 1.6-3.4 2-5.6 1-2.2 1-4.4.6-5.6-1z")],
    "pt-fh-goatee": [_p("M26.4 31.8c1.5-1.4 3.4-1.7 5.6-.8 2.2-.9 4.1-.6 5.6.8-1.2 1.6-3.4 2-5.6 1-2.2 1-4.4.6-5.6-1zM28.4 36c1 .9 2.2 1.3 3.6 1.3s2.6-.4 3.6-1.3c.6 2.2-1.4 4.6-3.6 4.6s-4.2-2.4-3.6-4.6z")],
    "pt-fh-beard": [_p("M20.8 29.5c.1 6.6 4.5 11.4 11.2 11.4s11.1-4.8 11.2-11.4c-1.6 2.3-3.4 3.4-5.2 3.8-1.6-1.2-3.4-1.8-6-1.8s-4.4.6-6 1.8c-1.8-.4-3.6-1.5-5.2-3.8z"
                      "M26.2 33.6c1.8 2.9 3.8 4 5.8 4s4-1.1 5.8-4c-1.7-.9-3.6-1.4-5.8-1.4s-4.1.5-5.8 1.4z", **{"fill-rule": "evenodd"})],
    # outfit details, drawn over the body
    "pt-det-tee": [_p("M25 47.5c2 3.8 4.4 5.5 7 5.5s5-1.7 7-5.5", fill="none", stroke="#000", **{"stroke-opacity": .2, "stroke-width": 1.6})],
    "pt-det-hoodie": [_p("M21.5 46.8c1.2 6.8 5.6 10.2 10.5 10.2s9.3-3.4 10.5-10.2", fill="none", stroke="#000", **{"stroke-opacity": .2, "stroke-width": 2.2}),
                      _p("M29 54v6M35 54v6", fill="none", stroke="#fff", **{"stroke-opacity": .85, "stroke-width": 1.3})],
    "pt-det-shirt": [_p("M23.5 46.4 32 56l-5-.2-6.5-8zM40.5 46.4 32 56l5-.2 6.5-8z", fill="#fff", **{"fill-opacity": .92}),
                     _p("M32 59h.01M32 62.5h.01", fill="none", stroke="#000", **{"stroke-opacity": .25, "stroke-width": 1.6})],
    "pt-det-polo": [_p("M23 46.6 29.6 52l2.4-4.6zM41 46.6 34.4 52 32 47.4z", fill="#fff", **{"fill-opacity": .9}), _p("M32 49v8", fill="none", stroke="#000", **{"stroke-opacity": .25, "stroke-width": 1.4}),
                    _p("M32 52h.01M32 55.5h.01", fill="none", stroke="#fff", **{"stroke-opacity": .8, "stroke-width": 1.6})],
    "pt-det-kurta": [_p("M26.4 46.4c1.4 1.6 3.4 2.4 5.6 2.4s4.2-.8 5.6-2.4l.4 2.2c-1.6 2-3.8 3-6 3s-4.4-1-6-3z", fill="#fff", **{"fill-opacity": .85}),
                     _p("M32 51v13", fill="none", stroke="#fff", **{"stroke-opacity": .6, "stroke-width": 1.2}), _p("M32 53h.01M32 57h.01M32 61h.01", fill="none", stroke="#F2C94C", **{"stroke-width": 1.7})],
    "pt-det-kurung": [_p("M29 47.5c.8 3 1.8 4.5 3 4.5s2.2-1.5 3-4.5", fill="none", stroke="#000", **{"stroke-opacity": .2, "stroke-width": 1.6}),
                      _p("M7 60h50", fill="none", stroke="#fff", **{"stroke-opacity": .55, "stroke-width": 1.4}), _p("M32 55h.01", fill="none", stroke="#F2C94C", **{"stroke-width": 3})],
    "pt-det-jacket": [_p("M24.5 47c2.6 3 5.2 4.5 7.5 4.5s4.9-1.5 7.5-4.5", fill="none", stroke="#000", **{"stroke-opacity": .25, "stroke-width": 2.2}),
                      _p("M32 51v13", fill="none", stroke="#fff", **{"stroke-opacity": .7, "stroke-width": 1.4})],
    # hair behind the head, and in front of it
    "pt-hairb-bob": [_p("M18.3 27c-.3-10.2 5-17 13.7-17s14 6.8 13.7 17c-.1 5-.6 9.5-2.2 12.2-.5.8-1.4 1.3-2.4 1.3H22.9c-1 0-1.9-.5-2.4-1.3-1.6-2.7-2.1-7.2-2.2-12.2z")],
    "pt-hairb-long": [_p("M17.8 28C17.4 16.5 23.5 9.5 32 9.5s14.6 7 14.2 18.5c-.1 8 1 15 2.8 21H15c1.8-6 2.9-13 2.8-21z")],
    "pt-hairb-ponytail": [_p("M41 14c6.5-.5 10.5 4 10 11.5-.4 6.4-3.4 10.5-5.4 14.5-1-4.5-1.8-7.5-4-10.5z")],
    "pt-hairb-bun": [_p(_ellipse(32, 9.2, 5, 5))],
    "pt-hairb-curly": [_p(_ellipse(32, 13.5, 8, 8) + _ellipse(23.5, 17.5, 6, 6) + _ellipse(40.5, 17.5, 6, 6) + _ellipse(20, 25, 4.6, 4.6) + _ellipse(44, 25, 4.6, 4.6))],
    "pt-hairf-short": [_p(SHORT)], "pt-hairf-bob": [_p(BOB_FRONT)], "pt-hairf-long": [_p(BOB_FRONT)], "pt-hairf-ponytail": [_p(SHORT)], "pt-hairf-bun": [_p(SHORT)],
    "pt-hairf-curly": [_p(CURLY_FRINGE)], "pt-hairf-buzz": [_p(BUZZ)], "pt-hairf-sidepart": [_p(SIDEPART), _p("M27.4 11.4c-.7 3.2-.3 5.6 1.1 7.6", fill="none", stroke="#fff", **{"stroke-opacity": .35, "stroke-width": 1})],
    "pt-hairf-spiky": [_p(SPIKY)], "pt-hairf-tudung": [_p(TUDUNG, **{"fill-rule": "evenodd"})],
    # accessories (their own colours)
    "pt-acc-glasses": [_p("M21.6 25.8h8.2v5.4h-8.2zM34.2 25.8h8.2v5.4h-8.2zM29.8 28h4.4", fill="#fff", **{"fill-opacity": .3}, stroke=DARK, **{"stroke-width": 1.4})],
    "pt-acc-round": [_p(_ellipse(27.2, 28.2, 3.4, 3.4) + _ellipse(36.8, 28.2, 3.4, 3.4) + "M30.6 28h2.8", fill="#fff", **{"fill-opacity": .3}, stroke=DARK, **{"stroke-width": 1.4})],
    "pt-acc-songkok": [_p("M21.3 18.5v-5.2c0-1.4 1-2.5 2.4-2.7 5.4-.8 11.2-.8 16.6 0 1.4.2 2.4 1.3 2.4 2.7v5.2z", fill="#1F1A1A"), _p("M21.3 16.3h21.4", fill="none", stroke="#E3B23C", **{"stroke-width": 1})],
    "pt-acc-cap": [_p("M20 21c0-7.5 4.6-11.8 12-11.8S44 13.5 44 21z", fill="#E5546B", stroke="#B73A4E", **{"stroke-width": 1}), _p("M31 21h18c0 2.2-3.5 3.6-9 3.6h-9z", fill="#C93A52"),
                   _p("M32 9.6h.01", fill="none", stroke="#fff", **{"stroke-width": 2})],
    "pt-acc-flower": [_p(_ellipse(42, 12.8, 1.9, 1.9) + _ellipse(44.2, 14.4, 1.9, 1.9) + _ellipse(43.4, 17, 1.9, 1.9) + _ellipse(40.6, 17, 1.9, 1.9) + _ellipse(39.8, 14.4, 1.9, 1.9), fill="#F29BB5"),
                       _p(_ellipse(42, 15, 1.3, 1.3), fill="#F2C94C")],
}
VIEWBOX = "4 5 56 56"


def layers_for(code: str) -> list[tuple[str, str | None]]:
    """The symbols that draw this look, bottom first, each with the colour it is filled with (None: it brings its own)."""
    look = ch.parse(code)
    if look is None:
        return []
    hair, outfit, acc, face = ch.HAIR_STYLES[look["hair"]], ch.OUTFIT_STYLES[look["outfit"]], ch.ACCESSORIES[look["accessory"]], ch.FACES[look["face"]]
    skin, hair_color, outfit_color = ch.SKINS[look["skin"]], ch.HAIR_COLORS[look["hair_color"]], ch.OUTFIT_COLORS[look["outfit_color"]]
    out: list[tuple[str, str | None]] = []
    if f"pt-hairb-{hair}" in LAYERS:
        out.append((f"pt-hairb-{hair}", hair_color))
    out += [("pt-body", outfit_color), (f"pt-det-{outfit}", None), ("pt-neck", skin), ("pt-head", skin), ("pt-face", None)]
    natural = ch.HAIR_COLORS[look["hair_color"]] if look["hair_color"] < ch.NATURAL_HAIR else ch.HAIR_COLORS[1]   # (a purple beard is a step too far)
    if face == "soft":
        out.append(("pt-blush", None))
    else:
        out.append(("pt-brows", natural))
        if face != "plain":
            out.append((f"pt-fh-{face}", natural))
    if f"pt-hairf-{hair}" in LAYERS:
        out.append((f"pt-hairf-{hair}", hair_color))
    if acc != "none" and not (hair == "tudung" and acc in ("songkok", "cap")):
        out.append((f"pt-acc-{acc}", None))
    return out


def symbols() -> str:
    """Every layer as a <g> in a <defs> (put in the page's sprite). Groups, not symbols: a symbol would clip and rescale what it draws."""
    def attrs(p: dict) -> str:
        return "".join(f' {k}="{v}"' for k, v in p.items() if k != "d")

    return "<defs>" + "".join(f'<g id="{sid}">' + "".join(f'<path d="{p["d"]}"{attrs(p)}/>' for p in paths) + "</g>" for sid, paths in LAYERS.items()) + "</defs>"


def portrait(code: str) -> Markup:
    uses = "".join(f'<use href="#{sid}"' + (f' fill="{color}"' if color else "") + "/>" for sid, color in layers_for(code))
    return Markup(f'<svg class="pt" viewBox="{VIEWBOX}" aria-hidden="true" focusable="false">{uses}</svg>')
