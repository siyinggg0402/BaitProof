"""The garage: cars and hats for Finn that are earned by playing, never bought. Each unlocks from something the player has already done (a level, a distance,
a streak, a Daily Road, passing a friend), and the choice is shown to friends on the road next to their ghost."""
from __future__ import annotations

from core.game import state as gs
from core.lang.i18n import tr
from core.storage import runs

# id -> (body colour or "rainbow", what unlocks it). A need is (kind, value); None means from the start.
CARS: dict[str, tuple[str, tuple | None]] = {
    "plum": ("#7A5CD0", None),
    "mint": ("#33B27C", ("level", 2)),
    "sky": ("#3FA7E8", ("best", 400)),
    "sunset": ("#F08A4B", ("streak", 3)),
    "gold": ("#E3B23C", ("best", 1200)),
    "midnight": ("#2D3070", ("daily", 3)),
    "rainbow": ("rainbow", ("badge", "road-ahead")),
}
HATS: dict[str, tuple | None] = {"none": None, "cap": ("level", 3), "shades": ("best", 800), "party": ("daily", 1), "scarf": ("streak", 5), "crown": ("best", 2000)}
CAR_NAMES = {"plum": "Plum", "mint": "Mint", "sky": "Sky", "sunset": "Sunset", "gold": "Gold", "midnight": "Midnight", "rainbow": "Rainbow"}
HAT_NAMES = {"none": "No hat", "cap": "Cap", "shades": "Shades", "party": "Party hat", "scarf": "Scarf", "crown": "Crown"}
DEFAULT = {"car": "plum", "hat": "none"}


class GarageError(ValueError):
    pass


def progress(profile: str) -> dict:
    s = gs.get()
    return {"level": gs.level_for(s["xp"]), "best": runs.best_distance(profile), "streak": s["best_streak"], "daily": s["road_daily_count"], "badges": set(s["badges"])}


def met(need: tuple | None, prog: dict) -> bool:
    if need is None:
        return True
    kind, value = need
    return value in prog["badges"] if kind == "badge" else prog[kind] >= value


def need_text(need: tuple | None, lang: str) -> str:
    if need is None:
        return ""
    kind, value = need
    if kind == "level":
        return tr("Reach level {n}", lang, n=value)
    if kind == "best":
        return tr("Drive {n} m in one go", lang, n=value)
    if kind == "streak":
        return tr("Play {n} days in a row", lang, n=value)
    if kind == "daily":
        return tr("Finish the Daily Road once", lang) if value == 1 else tr("Finish the Daily Road {n} times", lang, n=value)
    return tr("Drive past a friend's best on Scam Road", lang)


def selected(profile: str) -> dict:
    """The car and hat in use: what was chosen, as long as it is still unlocked (otherwise the plain ones)."""
    prog, chosen = progress(profile), gs.get()["garage"]
    car = chosen.get("car") if chosen.get("car") in CARS and met(CARS[chosen.get("car")][1], prog) else DEFAULT["car"]
    hat = chosen.get("hat") if chosen.get("hat") in HATS and met(HATS[chosen.get("hat")], prog) else DEFAULT["hat"]
    return {"car": car, "hat": hat}


def catalog(profile: str, lang: str = "en") -> dict:
    prog = progress(profile)
    return {
        "selected": selected(profile),
        "cars": [{"id": i, "name": tr(CAR_NAMES[i], lang), "color": c, "unlocked": met(n, prog), "need": need_text(n, lang)} for i, (c, n) in CARS.items()],
        "hats": [{"id": i, "name": tr(HAT_NAMES[i], lang), "unlocked": met(n, prog), "need": need_text(n, lang)} for i, n in HATS.items()],
    }


def choose(profile: str, car: str, hat: str) -> dict:
    prog = progress(profile)
    if car not in CARS or hat not in HATS:
        raise GarageError("That isn't in the garage.")
    if not met(CARS[car][1], prog) or not met(HATS[hat], prog):
        raise GarageError("That one is still locked. Keep driving to earn it.")
    s = gs.get()
    s["garage"] = {"car": car, "hat": hat}
    gs.save(s)
    return s["garage"]
