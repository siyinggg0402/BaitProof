"""The festive calendar of the places our players live (Singapore and Malaysia): which festival, if any, is on today, so the road and the home page can dress for it.

Each festival has a window around its day (a few days before, and as long after as people keep celebrating), and the days come from the governments' published holiday
lists for the years we know. The lunar festivals move about eleven days earlier each year and the Islamic and Hindu dates depend on the moon, so every year after 2027 is an
ESTIMATE: the windows are generous enough that a day or two of error shows the right theme, and the table should be refreshed each year. Dates are read in Singapore time.
Nothing here is personal: it is the date, and it is the same for everyone."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

from core.lang.i18n import tr

try:
    from zoneinfo import ZoneInfo

    _SG = ZoneInfo("Asia/Singapore")
except Exception:  # (no timezone database on this machine: Singapore has no daylight saving, so a fixed +8 is exact)
    _SG = timezone(timedelta(hours=8))

# festival -> (theme id, icon name, days before the day the theme starts, days after it ends)
FESTIVALS: dict[str, tuple[str, str, int, int]] = {
    "cny": ("cny", "fest-cny", 5, 15),               # Chinese New Year runs fifteen days, to Chap Goh Mei
    "raya": ("raya", "fest-raya", 5, 10),             # Hari Raya Aidilfitri (Hari Raya Puasa in Singapore)
    "deepavali": ("deepavali", "fest-deepavali", 5, 4),
    "midautumn": ("midautumn", "fest-midautumn", 5, 2),
    "christmas": ("christmas", "fest-christmas", 10, 2),
    "national": ("national", "fest-national", 8, 1),      # National Day, Singapore, 9 August
    "merdeka": ("merdeka", "fest-merdeka", 6, 16),       # Merdeka (31 August) through Malaysia Day (16 September)
}
# the day of each festival, by year. 2026 and 2027 are the governments' lists; later years are estimates (see the note above).
DAYS: dict[str, dict[int, tuple[int, int]]] = {
    "cny": {2026: (2, 17), 2027: (2, 6), 2028: (1, 26), 2029: (2, 13), 2030: (2, 3), 2031: (1, 23), 2032: (2, 11)},
    "raya": {2026: (3, 21), 2027: (3, 10), 2028: (2, 27), 2029: (2, 15), 2030: (2, 5), 2031: (1, 25), 2032: (1, 14)},
    "deepavali": {2026: (11, 8), 2027: (10, 28), 2028: (10, 17), 2029: (11, 5), 2030: (10, 26), 2031: (11, 14), 2032: (11, 2)},
    "midautumn": {2026: (9, 25), 2027: (9, 15), 2028: (10, 3), 2029: (9, 22), 2030: (9, 12), 2031: (10, 1), 2032: (9, 19)},
}
FIXED = {"christmas": (12, 25), "national": (8, 9), "merdeka": (8, 31)}

NAMES = {"cny": "Chinese New Year", "raya": "Hari Raya", "deepavali": "Deepavali", "midautumn": "Mid-Autumn Festival", "christmas": "Christmas", "national": "National Day", "merdeka": "Merdeka"}
GREETINGS = {"cny": "Happy Chinese New Year! Gong xi fa cai!", "raya": "Selamat Hari Raya! Maaf zahir dan batin.", "deepavali": "Happy Deepavali!", "midautumn": "Happy Mid-Autumn Festival!",
             "christmas": "Merry Christmas!", "national": "Happy National Day!", "merdeka": "Happy Merdeka! Selamat Hari Kebangsaan!"}


def today(now: datetime | None = None) -> date:
    """Today in Singapore. BAITPROOF_TODAY=2026-11-08 pins it (to film a festival's look, or to test one)."""
    pinned = os.getenv("BAITPROOF_TODAY", "")
    if pinned and now is None:
        try:
            return date.fromisoformat(pinned)
        except ValueError:
            pass
    return (now or datetime.now(timezone.utc)).astimezone(_SG).date()


def _day(festival: str, year: int) -> date | None:
    if festival in FIXED:
        m, d = FIXED[festival]
        return date(year, m, d)
    md = DAYS[festival].get(year)
    return date(year, *md) if md else None


def active(on: date) -> list[tuple[int, str, date]]:
    """Festivals whose window covers this date, as (distance in days from the festival's day, festival, its day)."""
    out = []
    for fest, (_, _, before, after) in FESTIVALS.items():
        for year in (on.year - 1, on.year, on.year + 1):   # (a window can reach across New Year)
            day = _day(fest, year)
            if day and day - timedelta(days=before) <= on <= day + timedelta(days=after):
                out.append((abs((on - day).days), fest, day))
    return out


def current(lang: str = "en", on: date | None = None) -> dict | None:
    """The festival on today, if any: {id, name, icon, greeting, day}. Where two windows overlap, the one whose day is nearer wins."""
    on = on or today()
    hits = sorted(active(on))
    if not hits:
        return None
    _, fest, day = hits[0]
    theme, icon, _, _ = FESTIVALS[fest]
    return {"id": theme, "name": tr(NAMES[fest], lang), "icon": icon, "greeting": tr(GREETINGS[fest], lang), "day": day.isoformat(), "days_to": (day - on).days}


def upcoming(on: date | None = None, n: int = 3) -> list[dict]:
    """The next festivals by their day (for a calendar view and for tests): [{id, day}]."""
    on = on or today()
    days = sorted((d, f) for f in FESTIVALS for y in (on.year, on.year + 1) if (d := _day(f, y)) and d >= on)
    return [{"id": f, "day": d.isoformat()} for d, f in days[:n]]
