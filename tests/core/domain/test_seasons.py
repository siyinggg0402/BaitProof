"""The festive calendar: which festival is on, the windows around each day, the nearest wins, and the pinned date used to try a look."""
from datetime import date, datetime, timezone

import pytest

from core.domain import seasons

D = date.fromisoformat


def on(day: str, lang="en"):
    return seasons.current(lang, D(day))


@pytest.mark.parametrize("day,festival", [
    ("2026-11-03", "deepavali"), ("2026-11-08", "deepavali"), ("2026-11-12", "deepavali"),          # five days before to four days after
    ("2026-12-15", "christmas"), ("2026-12-25", "christmas"), ("2026-12-27", "christmas"),
    ("2027-02-01", "cny"), ("2027-02-06", "cny"), ("2027-02-21", "cny"),                           # fifteen days after the first day: Chap Goh Mei
    ("2027-03-05", "raya"), ("2027-03-10", "raya"), ("2027-03-20", "raya"),
    ("2027-08-01", "national"), ("2027-08-09", "national"), ("2027-08-10", "national"),
    ("2027-08-25", "merdeka"), ("2027-08-31", "merdeka"), ("2027-09-09", "merdeka"),
    ("2027-09-10", "midautumn"), ("2027-09-15", "midautumn"), ("2027-09-17", "midautumn"),
    ("2028-01-26", "cny"), ("2029-02-13", "cny"), ("2030-02-05", "raya"),
])
def test_the_festival_is_on_during_its_window(day, festival):
    assert on(day)["id"] == festival, day


@pytest.mark.parametrize("day", ["2026-10-24", "2026-11-02", "2026-11-13", "2026-12-14", "2026-12-28", "2027-01-30", "2027-02-22", "2027-03-04", "2027-03-21", "2027-06-15", "2027-11-03"])
def test_most_days_have_no_festival(day):
    assert on(day) is None, day


def test_the_nearest_festival_wins_when_two_windows_overlap():
    assert on("2027-09-14")["id"] == "midautumn"      # Merdeka's window (to Malaysia Day on the 16th) still covers it, but Mid-Autumn is a day away
    assert on("2027-09-16")["id"] == "midautumn" and on("2027-09-09")["id"] == "merdeka"   # (before Mid-Autumn's window opens, Merdeka has it to itself)
    assert on("2027-09-10")["id"] == "midautumn"


def test_a_window_can_reach_across_new_year():
    assert on("2028-01-22")["id"] == "cny" and on("2031-01-18")["id"] == "cny" and on("2031-01-22")["days_to"] == 1


def test_what_the_page_gets():
    s = on("2026-11-05")
    assert s == {"id": "deepavali", "name": "Deepavali", "icon": "fest-deepavali", "greeting": "Happy Deepavali!", "day": "2026-11-08", "days_to": 3}
    assert on("2026-11-10")["days_to"] == -2


def test_the_names_and_greetings_are_translated():
    assert on("2027-02-06", "ms")["name"] == "Tahun Baharu Cina" and "Gong xi fa cai" in on("2027-02-06", "ms")["greeting"]
    assert on("2027-02-06", "zh")["name"] == "农历新年" and on("2027-02-06", "zh")["greeting"] == "新年快乐！恭喜发财！"
    for day in ("2026-11-08", "2026-12-25", "2027-03-10", "2027-08-09", "2027-08-31", "2027-09-15"):
        zh, ms, en = on(day, "zh"), on(day, "ms"), on(day, "en")
        assert zh["greeting"] != en["greeting"] and zh["name"] != en["name"], day
        assert ms["greeting"] != en["greeting"] or en["id"] == "raya", day     # (Hari Raya's greeting is already Malay)


def test_every_festival_has_a_day_for_the_years_we_serve():
    for fest in seasons.FESTIVALS:
        for year in range(2026, 2031):
            assert seasons._day(fest, year) is not None, (fest, year)
    for fest, years in seasons.DAYS.items():
        days = [date(y, *md) for y, md in sorted(years.items())]
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        assert all(300 < g < 400 for g in gaps), (fest, gaps)   # (lunar festivals shift by about eleven days, or nineteen with a leap month: never more than a year or fewer than 10 months)


def test_upcoming_lists_the_next_days_in_order():
    got = seasons.upcoming(D("2026-10-24"), 4)
    assert [g["id"] for g in got] == ["deepavali", "christmas", "cny", "raya"] and [g["day"] for g in got] == ["2026-11-08", "2026-12-25", "2027-02-06", "2027-03-10"]


def test_today_is_read_in_singapore_time_and_can_be_pinned(monkeypatch):
    late = datetime(2026, 11, 7, 17, 30, tzinfo=timezone.utc)        # already the 8th in Singapore
    assert seasons.today(late) == D("2026-11-08")
    monkeypatch.setenv("BAITPROOF_TODAY", "2027-02-06")
    assert seasons.today() == D("2027-02-06") and seasons.current("en")["id"] == "cny"
    monkeypatch.setenv("BAITPROOF_TODAY", "not-a-date")
    assert isinstance(seasons.today(), date)
