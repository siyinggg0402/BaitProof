"""The house: a room each person decorates with the XP they earn by playing: the XP already earned (the same number that sets the level) minus what has
been spent here, so spending never lowers a level and nothing new has to be earned anywhere else. Every purchase and every layout is checked on the server:
what you own, what it costs, what fits in the room and where. The 3D room is drawn by the browser (web/static/js/house.js); this module only knows the rules.

The room is a grid of 12 x 10 cells. Floor items cover a rectangle of cells (turned in quarter turns); rugs lie flat, so other things may stand on them; wall items hang
along the back wall or the left wall. Festival items can only be bought while their festival is on (core/domain/seasons.py) but stay yours for good."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from core.domain import seasons
from core.game import state as gs
from core.lang.i18n import tr

ROOM_W, ROOM_D = 12, 10
MAX_PLACED = 80
MAX_FOLLOWERS = 3          # pets that walk behind you at once
WALLS = ("back", "left")
PRICE_SCALE = 3            # the prices below are the first sketch; a house is built over many rounds, not one, so what things cost is three times that (rounded to 5)


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    cat: str                  # plants | furniture | decor | wall | festival | pets
    price: int
    w: int                    # cells along the x axis (floor items) or along the wall (wall items)
    d: int = 1                # cells along the z axis; always 1 for wall items
    kind: str = "floor"       # floor | rug | wall
    festival: str | None = None


def _price(sketch: int) -> int:
    return int(round(sketch * PRICE_SCALE / 5) * 5)


def _i(id, name, cat, price, w, d=1, kind="floor", festival=None) -> tuple[str, Item]:
    return id, Item(id, name, cat, _price(price), w, d, kind, festival)


CATALOG: dict[str, Item] = dict([
    # plants
    _i("succulent", "Succulent", "plants", 20, 1), _i("fern", "Fern", "plants", 35, 1), _i("bamboo", "Lucky bamboo", "plants", 55, 1), _i("monstera", "Monstera", "plants", 60, 1),
    _i("orchid", "Orchid", "plants", 70, 1), _i("palm", "Palm tree", "plants", 90, 1), _i("bonsai", "Bonsai", "plants", 120, 1),
    # furniture
    _i("stool", "Stool", "furniture", 30, 1), _i("beanbag", "Beanbag", "furniture", 60, 1), _i("armchair", "Armchair", "furniture", 110, 2, 2), _i("sofa", "Sofa", "furniture", 180, 4, 2),
    _i("coffee-table", "Coffee table", "furniture", 70, 2), _i("dining-table", "Dining table", "furniture", 150, 3, 2), _i("desk", "Desk", "furniture", 120, 3),
    _i("bookshelf", "Bookshelf", "furniture", 110, 2), _i("cabinet", "Cabinet", "furniture", 90, 2), _i("tv-stand", "TV stand", "furniture", 140, 3), _i("bed", "Bed", "furniture", 220, 3, 4),
    _i("floor-lamp", "Floor lamp", "furniture", 50, 1),
    # decor
    _i("vase", "Flower vase", "decor", 30, 1), _i("globe", "Globe", "decor", 60, 1), _i("teddy", "Teddy bear", "decor", 40, 1), _i("safe", "Family safe", "decor", 100, 1),
    _i("shield-trophy", "Shield trophy", "decor", 150, 1), _i("fish-tank", "Fish tank", "decor", 160, 2), _i("bike", "Bicycle", "decor", 110, 2), _i("piano", "Piano", "decor", 400, 3, 2),
    _i("rug-round", "Round rug", "decor", 80, 3, 3, "rug"), _i("rug-rect", "Big rug", "decor", 110, 4, 3, "rug"),
    # on the wall
    _i("poster-shield", "Baitproof poster", "wall", 40, 1, kind="wall"), _i("calendar", "Calendar", "wall", 40, 1, kind="wall"), _i("clock", "Wall clock", "wall", 45, 1, kind="wall"),
    _i("mirror", "Mirror", "wall", 70, 1, kind="wall"), _i("painting", "Painting", "wall", 50, 2, kind="wall"), _i("photo-frames", "Photo frames", "wall", 50, 2, kind="wall"),
    _i("wall-shelf", "Wall shelf", "wall", 60, 2, kind="wall"), _i("safe-home-sign", "Scam-free home sign", "wall", 90, 2, kind="wall"), _i("bunting", "Bunting", "wall", 55, 3, kind="wall"),
    # festivals
    _i("cny-lanterns", "Red lanterns", "festival", 50, 2, kind="wall", festival="cny"), _i("mandarin-tree", "Mandarin orange tree", "festival", 90, 1, festival="cny"),
    _i("ketupat", "Ketupat", "festival", 40, 1, kind="wall", festival="raya"), _i("pelita", "Pelita lamps", "festival", 60, 1, festival="raya"),
    _i("diya-set", "Diya lamps", "festival", 45, 1, festival="deepavali"), _i("rangoli", "Rangoli", "festival", 70, 2, 2, "rug", festival="deepavali"),
    _i("moon-lanterns", "Moon lanterns", "festival", 60, 3, kind="wall", festival="midautumn"), _i("lantern-stand", "Lantern stand", "festival", 70, 1, festival="midautumn"),
    _i("xmas-tree", "Christmas tree", "festival", 90, 1, festival="christmas"), _i("wreath", "Wreath", "festival", 40, 1, kind="wall", festival="christmas"),
    _i("sg-flag", "Singapore flag", "festival", 50, 2, kind="wall", festival="national"), _i("merlion", "Merlion", "festival", 100, 1, festival="national"),
    _i("my-flag", "Jalur Gemilang", "festival", 50, 2, kind="wall", festival="merdeka"), _i("wau", "Wau kite", "festival", 60, 2, kind="wall", festival="merdeka"),
    # pets (the animals that used to be profile pictures)
    _i("pet-fish", "Finn in a bowl", "pets", 90, 1), _i("pet-fox", "Fox", "pets", 140, 1), _i("pet-panda", "Panda", "pets", 160, 1), _i("pet-tiger", "Tiger cub", "pets", 160, 1),
    _i("pet-frog", "Frog", "pets", 100, 1), _i("pet-owl", "Owl", "pets", 120, 1), _i("pet-octopus", "Octopus", "pets", 130, 1), _i("pet-turtle", "Turtle", "pets", 110, 1),
    _i("pet-unicorn", "Unicorn", "pets", 220, 1), _i("pet-cat", "Cat", "pets", 120, 1), _i("pet-penguin", "Penguin", "pets", 150, 1), _i("pet-lion", "Lion", "pets", 180, 1),
])
CATEGORIES = ("plants", "furniture", "decor", "wall", "festival", "pets")
CATEGORY_NAMES = {"plants": "Plants", "furniture": "Furniture", "decor": "Decor", "wall": "Wall", "festival": "Festival", "pets": "Pets"}
FESTIVAL_NAMES = {"cny": "Chinese New Year", "raya": "Hari Raya", "deepavali": "Deepavali", "midautumn": "Mid-Autumn Festival", "christmas": "Christmas", "national": "National Day", "merdeka": "Merdeka"}

# floors and walls: id -> (name, price, colour). The first of each is free and what a new house starts with.
FLOORS: dict[str, tuple[str, int, str]] = {"wood": ("Wooden floor", 0, "#C9A27A"), "oak": ("Light oak floor", _price(50), "#E4CBA3"), "tile": ("Tiled floor", _price(60), "#E7E3EE"),
                                           "carpet": ("Carpet", _price(80), "#B9A7E8"), "stone": ("Stone floor", _price(70), "#B4B0BC")}
PAINTS: dict[str, tuple[str, int, str]] = {"lilac": ("Lilac walls", 0, "#E3DAF7"), "cream": ("Cream walls", _price(30), "#F6EBD6"), "mint": ("Mint walls", _price(40), "#D6F0E4"),
                                           "sky": ("Sky walls", _price(40), "#D5E8F8"), "blush": ("Blush walls", _price(40), "#F8DCE6"), "charcoal": ("Charcoal walls", _price(60), "#5A5670")}
STYLES = {"floor": FLOORS, "wall": PAINTS}
DEFAULT_HOUSE = {"spent": 0, "owned": {}, "styles": ["wood", "lilac"], "floor": "wood", "wall": "lilac", "layout": []}


class HouseError(ValueError):
    """The message is plain language, shown to the person (and translated by the website)."""


def get() -> dict:
    """This profile's house as stored, with every field present."""
    raw = gs.get()["house"]
    return {**json.loads(json.dumps(DEFAULT_HOUSE)), **{k: raw[k] for k in DEFAULT_HOUSE if k in raw}} if isinstance(raw, dict) else json.loads(json.dumps(DEFAULT_HOUSE))


def _save(h: dict) -> None:
    s = gs.get()
    s["house"] = h
    gs.save(s)


def balance(h: dict | None = None) -> int:
    """XP to spend: the XP earned so far minus what has been spent in the house."""
    return max(0, gs.get()["xp"] - (h or get())["spent"])


def open_festivals(on: date | None = None) -> set[str]:
    return {fest for _, fest, _ in seasons.active(on or seasons.today())}


def buy(item_id: str, on: date | None = None) -> dict:
    item = CATALOG.get(item_id)
    if item is None:
        raise HouseError("That isn't in the shop.")
    if item.festival and item.festival not in open_festivals(on):
        raise HouseError("That one is only in the shop during its festival.")
    h = get()
    if balance(h) < item.price:
        raise HouseError("You don't have enough XP yet. Keep playing to earn more.")
    if sum(h["owned"].values()) >= MAX_PLACED * 2:
        raise HouseError("Your house has all the things it can hold.")
    h["spent"] += item.price
    h["owned"][item_id] = h["owned"].get(item_id, 0) + 1
    _save(h)
    return h


def buy_style(part: str, style_id: str) -> dict:
    table = STYLES.get(part)
    if table is None or style_id not in table:
        raise HouseError("That isn't in the shop.")
    h = get()
    if style_id not in h["styles"]:
        price = table[style_id][1]
        if balance(h) < price:
            raise HouseError("You don't have enough XP yet. Keep playing to earn more.")
        h["spent"] += price
        h["styles"].append(style_id)
    h[part] = style_id
    _save(h)
    return h


def _int(v, lo: int, hi: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise HouseError("That doesn't fit there.")
    return v


def clean_layout(layout, owned: dict[str, int]) -> list[dict]:
    """The layout if it is a legal one, else a HouseError: only things you own (as many as you own), inside the room, nothing standing on anything else.
    Floor items are {item, x, z, r} (r = quarter turns; a pet may also have follow: true, to walk behind its owner, at most three at a time); wall items are {item, wall, x}
    (x = the first cell along the wall)."""
    if not isinstance(layout, list) or len(layout) > MAX_PLACED:
        raise HouseError("That doesn't fit there.")
    out, used, followers = [], {}, 0
    solid, rugs = set(), set()
    wall_used = {w: set() for w in WALLS}
    for p in layout:
        if not isinstance(p, dict) or p.get("item") not in CATALOG:
            raise HouseError("That doesn't fit there.")
        item = CATALOG[p["item"]]
        used[item.id] = used.get(item.id, 0) + 1
        if used[item.id] > owned.get(item.id, 0):
            raise HouseError("You don't own that many.")
        if item.kind == "wall":
            wall = p.get("wall")
            if wall not in WALLS:
                raise HouseError("That doesn't fit there.")
            length = ROOM_W if wall == "back" else ROOM_D
            x = _int(p.get("x"), 0, length - item.w)
            cells = {(wall, x + k) for k in range(item.w)}
            if cells & {(wall, c) for c in wall_used[wall]}:
                raise HouseError("Something is already hanging there.")
            wall_used[wall] |= {x + k for k in range(item.w)}
            out.append({"item": item.id, "wall": wall, "x": x})
            continue
        r = _int(p.get("r", 0), 0, 3)
        follows = item.cat == "pets" and p.get("follow") is True
        if follows:
            followers += 1
            if followers > MAX_FOLLOWERS:
                raise HouseError("Only three pets can follow you at once.")
        w, d = (item.w, item.d) if r % 2 == 0 else (item.d, item.w)
        x, z = _int(p.get("x"), 0, ROOM_W - w), _int(p.get("z"), 0, ROOM_D - d)
        cells = {(x + i, z + j) for i in range(w) for j in range(d)}
        taken = rugs if item.kind == "rug" else solid
        if cells & taken:
            raise HouseError("Something is already standing there.")
        taken |= cells
        out.append({"item": item.id, "x": x, "z": z, "r": r, **({"follow": True} if follows else {})})
    return out


def save_layout(layout) -> dict:
    h = get()
    h["layout"] = clean_layout(layout, h["owned"])
    _save(h)
    return h


def _item_json(item: Item, h: dict, open_now: set[str], lang: str) -> dict:
    return {"id": item.id, "name": tr(item.name, lang), "cat": item.cat, "price": item.price, "w": item.w, "d": item.d, "kind": item.kind, "festival": item.festival or "",
            "festival_name": tr(FESTIVAL_NAMES[item.festival], lang) if item.festival else "", "open": not item.festival or item.festival in open_now,
            "owned": h["owned"].get(item.id, 0)}


def styles_json(h: dict, lang: str) -> dict:
    return {part: [{"id": i, "name": tr(n, lang), "price": p, "color": c, "owned": i in h["styles"]} for i, (n, p, c) in table.items()] for part, table in STYLES.items()}


def view(lang: str = "en", on: date | None = None) -> dict:
    """Everything the page needs to draw and edit your own house."""
    h, open_now = get(), open_festivals(on)
    return {"balance": balance(h), "room": {"w": ROOM_W, "d": ROOM_D}, "floor": h["floor"], "wall": h["wall"], "layout": h["layout"], "styles": styles_json(h, lang),
            "items": [_item_json(i, h, open_now, lang) for i in CATALOG.values()],
            "categories": [{"id": c, "name": tr(CATEGORY_NAMES[c], lang)} for c in CATEGORIES], "max_placed": MAX_PLACED, "max_followers": MAX_FOLLOWERS}


def public_view(lang: str = "en") -> dict:
    """What a friend who visits sees: the layout and the room's look, and nothing about points or what is owned."""
    h = get()
    looks = {part: [{"id": i, "name": tr(n, lang), "color": c} for i, (n, _, c) in table.items() if i == h[part]] for part, table in STYLES.items()}   # (just the ones in use)
    return {"room": {"w": ROOM_W, "d": ROOM_D}, "floor": h["floor"], "wall": h["wall"], "layout": h["layout"], "styles": looks,
            "items": [{"id": i.id, "name": tr(i.name, lang), "w": i.w, "d": i.d, "kind": i.kind, "cat": i.cat} for i in CATALOG.values() if any(p["item"] == i.id for p in h["layout"])]}
