"""The site's icons: one set of line drawings on a 24x24 grid, drawn here as path data and sent once per page as an inline SVG sprite.
Pages and scripts use them with <use href="#i-NAME">, so they take the colour of the text around them (currentColor) and need no inline style, which the
CSP would block. A path starting with "~" is a filled shape (a heart, a pupil); everything else is a stroke. Only <path> elements are used, so the Scam Road
scene can read the same data and draw it on a canvas (road.js)."""
from __future__ import annotations

from markupsafe import Markup, escape


def circle(cx: float, cy: float, r: float) -> str:
    return f"M{cx - r:g} {cy:g}a{r:g} {r:g} 0 1 0 {2 * r:g} 0a{r:g} {r:g} 0 1 0 {-2 * r:g} 0"


def dot(x: float, y: float) -> str:
    return f"M{x:g} {y:g}h.01"


def scallop(cx: float, cy: float, big: float, n: int, bump: float) -> str:
    """A ring of n bumps (a lion's mane): points on a circle of radius `big`, joined by arcs that bulge outwards."""
    import math

    pts = [(cx + big * math.sin(2 * math.pi * i / n), cy - big * math.cos(2 * math.pi * i / n)) for i in range(n)]
    d = f"M{pts[0][0]:.2f} {pts[0][1]:.2f}"
    for x, y in pts[1:] + pts[:1]:
        d += f"A{bump:g} {bump:g} 0 0 1 {x:.2f} {y:.2f}"
    return d + "z"


SHIELD = "M12 3 4 6v6c0 4.4 3.1 7.7 8 9 4.9-1.3 8-4.6 8-9V6z"
HEART = "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z"
LANTERN = ("M9.5 3h5", "M12 3v2", "M12 5c4.4 0 7 2.9 7 6.5S16.4 18 12 18s-7-2.9-7-6.5S7.6 5 12 5z", "M12 5c-2.4 2.6-2.4 10.4 0 13", "M12 5c2.4 2.6 2.4 10.4 0 13", "M9.5 19h5", "M12 19v3")

ICONS: dict[str, tuple[str, ...]] = {
    # the three answers, and the marks that say how a check went
    "alert": ("M12 9v4", dot(12, 17), "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"),
    "question": (circle(12, 12, 9), "M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3", dot(12, 17)),
    "check": ("M20 6 9 17l-5-5",),
    "check-circle": (circle(12, 12, 9), "m8.5 12.5 2.5 2.5 4.5-5"),
    "x": ("M18 6 6 18", "m6 6 12 12"),
    "x-circle": (circle(12, 12, 9), "m9 9 6 6", "m15 9-6 6"),
    "minus": ("M5 12h14",),
    "redirect": ("m15 14 5-5-5-5", "M4 20v-7a4 4 0 0 1 4-4h16"),
    "shield": (SHIELD,),
    "shield-check": (SHIELD, "m9 12 2 2 4-4"),
    "bulb": ("M9 18h6", "M10 21h4", "M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"),
    "zap": ("M13 2 4 14h7l-1 8 9-12h-7z",),
    "sparkles": ("M10 3l1.8 5.2L17 10l-5.2 1.8L10 17l-1.8-5.2L3 10l5.2-1.8z", "M19 15v5", "M16.5 17.5h5", "M19 3.5v3", "M17.5 5h3"),
    "confetti": ("M4 21 9 8l7 7z", "M14 4h.01", "M19 8h.01", "M19 14h.01", "M12.5 8.5l2-2", "M16.5 12.5l2-1"),
    "arrow-up": ("M12 19V5", "m5 12 7-7 7 7"),
    # inputs and evidence
    "camera": ("M4 7h3l1.5-2h7L17 7h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z", circle(12, 13, 3.5)),
    "mic": ("M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z", "M5 11a7 7 0 0 0 14 0", "M12 18v3"),
    "pin": ("M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z", circle(12, 9.5, 2.5)),
    "link": ("M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71", "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"),
    "lifebuoy": (circle(12, 12, 9), circle(12, 12, 3.5), "m5.6 5.6 3.9 3.9", "m14.5 14.5 3.9 3.9", "m18.4 5.6-3.9 3.9", "m9.5 14.5-3.9 3.9"),
    "volume": ("M11 5 6 9H3v6h3l5 4z", "M15.5 8.5a5 5 0 0 1 0 7", "M18.5 5.5a9 9 0 0 1 0 13"),
    "volume-off": ("M11 5 6 9H3v6h3l5 4z", "m16 9 6 6", "m22 9-6 6"),
    "thumb-up": ("M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.3a2 2 0 0 0 2-1.7l1.4-9a2 2 0 0 0-2-2.3z", "M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"),
    "thumb-down": ("M10 15v4a3 3 0 0 0 3 3l4-9V2H5.7a2 2 0 0 0-2 1.7l-1.4 9a2 2 0 0 0 2 2.3z", "M17 2h2.7A2.3 2.3 0 0 1 22 4v7a2.3 2.3 0 0 1-2.3 2H17"),
    "send": ("M22 2 11 13", "M22 2l-7 20-4-9-9-4z"),
    "globe": (circle(12, 12, 9), "M3 12h18", "M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9S9.4 5.6 12 3z"),
    "pause": ("M8 5v14", "M16 5v14"),
    "stop": ("M7 7h10v10H7z",),
    "users": (circle(9, 8, 3.2), "M3.5 19c.4-3.2 2.6-5 5.5-5s5.1 1.8 5.5 5", circle(17, 9.5, 2.4), "M16 14.2c2.6-.2 4.3 1.3 4.7 4.3"),
    "chart": ("M6 20v-9", "M12 20V4", "M18 20v-6"),
    "bell": ("M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9", "M10.3 21a1.9 1.9 0 0 0 3.4 0"),
    "lock": ("M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z", "M8 11V7a4 4 0 0 1 8 0v4"),
    "search": (circle(11, 11, 7), "m21 21-4.3-4.3"),
    # games and rewards
    "gamepad": ("M6 11h4", "M8 9v4", dot(15, 12), dot(18, 10),
                "M17.3 5H6.7a4 4 0 0 0-4 3.6C2.6 9.4 2 14.5 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.4-1.4A2 2 0 0 1 9.8 16h4.4a2 2 0 0 1 1.4.6L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.5-.6-6.6-.7-7.3A4 4 0 0 0 17.3 5z"),
    "timer": (circle(12, 13, 8), "M12 9v4l2 2", "M9 2h6"),
    "inbox": ("M22 12h-6l-2 3h-4l-2-3H2", "M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"),
    "calendar": ("M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z", "M16 3v4", "M8 3v4", "M3 11h18"),
    "swords": ("M14.5 17.5 3 6V3h3l11.5 11.5", "M13 19l6-6", "M16 16l4 4", "M19 21l2-2", "M14.5 6.5 18 3h3v3l-3.5 3.5", "M5 14l4 4", "M7 17l-3 3", "M3 19l2 2"),
    "trophy": ("M8 21h8", "M12 17v4", "M7 4h10v5a5 5 0 0 1-10 0z", "M17 5h3v2a3 3 0 0 1-3 3", "M7 5H4v2a3 3 0 0 0 3 3"),
    "medal": ("M8 2.5 11 9", "M16 2.5 13 9", circle(12, 15, 5.5), circle(12, 15, 2)),
    "star": ("m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z",),
    "flame": ("M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.4-.5-2-1-3-1.1-2.1-.2-4.1 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.2.4-2.3 1-3a2.5 2.5 0 0 0 2.5 2.5z",),
    "flag": ("M4 22V4", "M4 4h13l-2 4 2 4H4"),
    "car": ("M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2",
            circle(7, 17, 2), "M9 17h6", circle(17, 17, 2)),
    "heart": (HEART,),
    "heart-fill": ("~" + HEART,),
    "crown": ("M3 8l4.5 4L12 5l4.5 7L21 8l-2 11H5z",),
    "ban": (circle(12, 12, 9), "m5.6 5.6 12.8 12.8"),
    # cosmetics for the car's driver
    "cap": ("M5 15a7 7 0 0 1 14 0", "M5 15h14", "M19 15h3", dot(12, 7.8)),
    "shades": ("M3 10h18", "M5 10v3a3 3 0 0 0 6 0v-3", "M13 10v3a3 3 0 0 0 6 0v-3"),
    "party-hat": ("M12 4 6 20h12z", "M8.8 13h6.4", "M12 3h.01"),
    "scarf": ("M4 7c2.4 3.4 5.2 5 8 5s5.6-1.6 8-5v3.5c-2.4 3.4-5.2 5-8 5s-5.6-1.6-8-5z", "M13.5 15.2V21h4v-7.2", "M13.5 18h4"),
    "top-hat": ("M7 16V5h10v11", "M3.5 16h17", "M7 12h10"),
    # how well someone knows a trick (the family dashboard)
    "lv-strong": ("~" + circle(12, 12, 8),),
    "lv-mid": (circle(12, 12, 8), "~M12 4a8 8 0 0 1 0 16z"),
    "lv-weak": (circle(12, 12, 8), "~M12 4a8 8 0 0 1 8 8h-8z"),
    "lv-none": (circle(12, 12, 8),),
    # festivals on the home page and the road
    "fest-cny": ("M7 3h10a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z", "M6 9c3 3.2 9 3.2 12 0", circle(12, 12.5, 1.6)),
    "fest-raya": ("M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z", "M17.5 4.5h.01", "M20 8h.01"),
    "fest-deepavali": ("M3 13h18c0 4-3.5 7-9 7s-9-3-9-7z", "M12 3c2.2 2.2 3.2 3.6 3.2 5.6a3.2 3.2 0 0 1-6.4 0C8.8 6.6 9.8 5.2 12 3z"),
    "fest-midautumn": LANTERN,
    "fest-christmas": ("M12 3 6.5 10.5h3L5 16.5h5V21h4v-4.5h5l-4.5-6h3z",),
    "fest-national": ("M3 5h18v14H3z", "M3 12h18", "M9.5 7.6a2.4 2.4 0 1 0 1.4 3.5 2.9 2.9 0 0 1-1.4-3.5z", "M13.5 8.2h.01", "M15 7.2h.01", "M16.5 8.2h.01", "M14 9.8h.01", "M16 9.8h.01"),
    "fest-merdeka": ("M3 5h18v14H3z", "M11 5v7H3", "M11 8.5h10", "M3 15.5h18"),
    # profile pictures: friendly animal faces
    "av-fish": ("M2.5 12c3-5 9-6.5 13.5-3.5l5-2.5v12l-5-2.5C11.5 18.5 5.5 17 2.5 12z", dot(7.5, 11.5)),
    "av-fox": ("M4 4l4.2 3.4h7.6L20 4v8.5L12 20 4 12.5z", dot(9, 12), dot(15, 12), "M11 16.5h2"),
    "av-panda": (circle(12, 13, 8), circle(6, 5.8, 2.4), circle(18, 5.8, 2.4), "~" + circle(9, 12.2, 1.5), "~" + circle(15, 12.2, 1.5), dot(12, 15.5), "M10.3 17.6c.9.8 2.5.8 3.4 0"),
    "av-tiger": (circle(12, 13, 8), "M5.2 8.2 4 4l4.2 1.4", "M18.8 8.2 20 4l-4.2 1.4", "M12 6v3", "M9 6.6l.6 2", "M15 6.6l-.6 2", dot(9, 13), dot(15, 13), dot(12, 15.6), "M10.3 17.6c.9.8 2.5.8 3.4 0"),
    "av-frog": (circle(7.5, 7.5, 3), circle(16.5, 7.5, 3), dot(7.5, 7.5), dot(16.5, 7.5), "M4.6 10.4C3.4 12 3.4 14.3 5 16.2c1.8 2.3 4.2 3.3 7 3.3s5.2-1 7-3.3c1.6-1.9 1.6-4.2.4-5.8", "M9 15.4c1.8 1.2 4.2 1.2 6 0"),
    "av-owl": ("M5 4l3.2 2.6h7.6L19 4v10.5a7 7 0 0 1-14 0z", circle(9, 11, 2.4), circle(15, 11, 2.4), dot(9, 11), dot(15, 11), "M12 13.4l-1.2 2.2h2.4z"),
    "av-octopus": ("M6 10a6 6 0 0 1 12 0c0 2-.8 3.4-2 4.4", "M8 14.4C7 16 6 17.5 4.5 18", "M10.5 15.6C10 17.5 9 19 7.5 20", "M13.5 15.6c.5 1.9 1.5 3.4 3 4.4", "M16 14.4c1 1.6 2 3.1 3.5 3.6", "M8 14.4c.4.2.8.1 1 0", dot(10, 9.5), dot(14, 9.5), "M10.8 12.2c.8.5 1.6.5 2.4 0"),
    "av-turtle": ("M3 16c0-4 3.4-7 7.5-7s7.5 3 7.5 7z", "M10.5 9v7", "M6.4 11.4 7.4 16", "M14.6 11.4 13.6 16", circle(20.4, 13.6, 1.8), "M6 16v3", "M15 16v3", dot(21, 13)),
    "av-unicorn": (circle(12, 14, 7), "M10.3 7.6 12 1.8l1.7 5.8", "M5.8 9.4 4.6 5l3.8 1.9", "M18.2 9.4 19.4 5l-3.8 1.9", dot(9.3, 13.6), dot(14.7, 13.6), "M10.6 17.4c.8.6 2 .6 2.8 0"),
    "av-cat": (circle(12, 13.5, 7.5), "M5.8 9.5 5 3.5l4.6 3", "M18.2 9.5 19 3.5l-4.6 3", dot(9, 13), dot(15, 13), "M11 15.6h2l-1 1.1z", "M3 14.5h3", "M3.4 17.5l2.8-1.2", "M21 14.5h-3", "M20.6 17.5l-2.8-1.2"),
    "av-penguin": ("M12 3c-3.3 0-5.5 3-5.5 7.5S5 17 5 19.5c0 1 1 1.5 2 1.5h10c1 0 2-.5 2-1.5 0-2.5-1.5-5-1.5-9S15.3 3 12 3z", "M12 12c-2 0-3 1.6-3 3.6s1.3 3.4 3 3.4 3-1.4 3-3.4-1-3.6-3-3.6z", dot(10, 8), dot(14, 8), "M12 9.8l-1 1.4h2z"),
    "av-lion": (scallop(12, 12, 8, 10, 2.9), circle(12, 12, 5), dot(10, 11.3), dot(14, 11.3), dot(12, 13.4), "M10.6 15.1c.8.6 1.9.6 2.8 0"),
}

AVATAR_IDS = ("fish", "fox", "panda", "tiger", "frog", "owl", "octopus", "turtle", "unicorn", "cat", "penguin", "lion")
FESTIVAL_ICONS = {"cny": "fest-cny", "raya": "fest-raya", "deepavali": "fest-deepavali", "midautumn": "fest-midautumn", "christmas": "fest-christmas", "national": "fest-national", "merdeka": "fest-merdeka"}


def sprite() -> Markup:
    """Every icon as a <symbol>, once per page, out of sight."""
    symbols = []
    for name, paths in ICONS.items():
        body = "".join(f'<path fill="currentColor" d="{p[1:]}"/>' if p.startswith("~") else f'<path d="{p}"/>' for p in paths)
        symbols.append(f'<symbol id="i-{name}" viewBox="0 0 24 24">{body}</symbol>')
    return Markup('<svg class="sprite" aria-hidden="true" focusable="false" width="0" height="0">' + "".join(symbols) + "</svg>")


def icon(name: str, cls: str = "") -> Markup:
    if name not in ICONS:
        raise KeyError(f"no icon called {name!r}")
    return Markup(f'<svg class="ic{" " + escape(cls) if cls else ""}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>')


def avatar(name: str, cls: str = "") -> Markup:
    """A profile picture: the animal's face in a soft circle. An unknown name (an old emoji avatar that was never converted) becomes the fish."""
    name = name if name in AVATAR_IDS else "fish"
    return Markup(f'<span class="avt{" " + escape(cls) if cls else ""}" data-av="{name}">{icon("av-" + name)}</span>')


def avatar_name(name: str) -> str:
    return name if name in AVATAR_IDS else "fish"
