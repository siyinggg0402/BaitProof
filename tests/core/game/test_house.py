"""The house: what the shop sells, how the XP you earn is spent, and which layouts are legal. The server is the only judge: a layout that does not fit is refused whole."""
from datetime import date

import pytest

from core.domain import seasons
from core.game import house
from core.game import state as gs
from core.storage import accounts

DIWALI, ORDINARY = date(2026, 11, 8), date(2026, 6, 10)   # (a day with no festival near it)


def give(xp):
    s = gs.get()
    s["xp"] = xp
    gs.save(s)


def own(**counts):
    """Own these items without paying (the rules for buying are tested on their own)."""
    h = house.get()
    h["owned"] = counts
    house._save(h)


def put(*entries):
    return house.save_layout(list(entries))["layout"]


def rejects(*entries, match=None):
    with pytest.raises(house.HouseError, match=match):
        house.save_layout(list(entries))


# ---------------------------------------------------------------- the shop
def test_the_catalogue_is_sound():
    items = list(house.CATALOG.values())
    assert len({i.id for i in items}) == len(items) >= 60 and all(i.price > 0 and i.name and i.cat in house.CATEGORIES for i in items)
    for i in items:
        if i.kind == "wall":
            assert i.d == 1 and 1 <= i.w <= 3, i.id
        else:
            assert 1 <= i.w and 1 <= i.d and max(i.w, i.d) <= min(house.ROOM_W, house.ROOM_D), i.id   # (it fits the room either way round)
        assert i.kind in ("floor", "rug", "wall") and (i.festival is None) == (i.cat != "festival"), i.id
        assert i.festival is None or i.festival in seasons.FESTIVALS, i.id
    assert {i.festival for i in items if i.festival} == set(seasons.FESTIVALS) and all(sum(1 for i in items if i.festival == f) >= 2 for f in seasons.FESTIVALS)
    assert sorted(i.id for i in items if i.cat == "pets") == sorted("pet-" + a for a in accounts.AVATARS)   # the animals that used to be profile pictures
    assert all(house.FLOORS[k][1] == 0 for k in ("wood",)) and house.PAINTS["lilac"][1] == 0
    assert set(house.CATEGORY_NAMES) == set(house.CATEGORIES) and set(house.FESTIVAL_NAMES) == set(seasons.FESTIVALS)


def test_your_points_are_the_xp_you_earned_minus_what_you_spent():
    fern = house.CATALOG["fern"].price
    give(200)
    assert house.balance() == 200
    house.buy("fern")
    assert house.balance() == 200 - fern and house.get()["owned"] == {"fern": 1}
    assert gs.get()["xp"] == 200          # (spending never lowers your level)
    give(500)
    assert house.balance() == 500 - fern


def test_things_cost_enough_that_a_house_takes_many_rounds():
    """Prices are three times the first sketch: a round of the games earns about 100 XP, so a plant is a round's work and a sofa several, and the whole shop a long game."""
    prices = {i.id: i.price for i in house.CATALOG.values()}
    assert prices["succulent"] == 60 and prices["fern"] == 105 and prices["sofa"] == 540 and prices["piano"] == 1200 and prices["pet-fox"] == 420
    assert all(p % 5 == 0 and p >= 60 for p in prices.values()) and min(prices.values()) == 60
    assert sum(prices.values()) > 15000                       # the whole shop is well over a hundred rounds of play
    assert house.FLOORS["carpet"][1] == 240 and house.PAINTS["charcoal"][1] == 180 and house.FLOORS["wood"][1] == 0 and house.PAINTS["lilac"][1] == 0
    assert all(i.price >= 3 * 20 for i in house.CATALOG.values()) and house.PRICE_SCALE == 3


def test_you_cannot_spend_what_you_do_not_have_and_the_server_says_so():
    give(10)
    with pytest.raises(house.HouseError, match="enough XP"):
        house.buy("fern")
    assert house.balance() == 10 and house.get()["owned"] == {}
    with pytest.raises(house.HouseError, match="isn't in the shop"):
        house.buy("not-a-thing")


def test_you_can_buy_the_same_thing_again_and_the_house_has_a_limit():
    give(1000)
    house.buy("succulent")
    house.buy("succulent")
    assert house.get()["owned"] == {"succulent": 2}
    h = house.get()
    h["owned"] = {"succulent": house.MAX_PLACED * 2}
    house._save(h)
    with pytest.raises(house.HouseError, match="can hold"):
        house.buy("succulent")


def test_festival_things_are_only_sold_during_their_festival_but_stay_yours():
    give(1000)
    with pytest.raises(house.HouseError, match="during its festival"):
        house.buy("diya-set", on=ORDINARY)
    house.buy("diya-set", on=DIWALI)
    assert house.get()["owned"] == {"diya-set": 1}
    put({"item": "diya-set", "x": 2, "z": 2, "r": 0})                       # (placing it needs no festival)
    shown = {i["id"]: i for i in house.view(on=ORDINARY)["items"]}
    assert shown["diya-set"]["open"] is False and shown["diya-set"]["owned"] == 1 and shown["succulent"]["open"] is True and shown["diya-set"]["festival"] == "deepavali"
    assert {i["id"]: i for i in house.view(on=DIWALI)["items"]}["diya-set"]["open"] is True


def test_floors_and_walls_are_bought_once_and_used_free_after():
    give(300)
    assert house.get()["floor"] == "wood" and house.get()["wall"] == "lilac" and house.get()["styles"] == ["wood", "lilac"]
    house.buy_style("floor", "carpet")
    assert house.get()["floor"] == "carpet" and house.balance() == 300 - house.FLOORS["carpet"][1]
    house.buy_style("floor", "wood")                  # back to the free one: no charge
    house.buy_style("floor", "carpet")                # and to the carpet again: already paid for
    assert house.get()["floor"] == "carpet" and house.balance() == 300 - house.FLOORS["carpet"][1]
    give(0)
    house.get()
    with pytest.raises(house.HouseError, match="enough XP"):
        house.buy_style("wall", "charcoal")
    for part, style in (("roof", "wood"), ("floor", "marble"), ("wall", "wood")):
        with pytest.raises(house.HouseError, match="isn't in the shop"):
            house.buy_style(part, style)


# ---------------------------------------------------------------- what fits where
def test_a_legal_layout_is_kept_and_cleaned():
    own(sofa=1, fern=2, **{"rug-round": 1}, painting=1)
    layout = put({"item": "sofa", "x": 4, "z": 6, "r": 0, "junk": "ignored"}, {"item": "fern", "x": 0, "z": 0}, {"item": "fern", "x": 11, "z": 9, "r": 3},
                 {"item": "rug-round", "x": 4, "z": 5}, {"item": "painting", "wall": "back", "x": 3})
    assert layout[0] == {"item": "sofa", "x": 4, "z": 6, "r": 0} and layout[1] == {"item": "fern", "x": 0, "z": 0, "r": 0} and layout[4] == {"item": "painting", "wall": "back", "x": 3}
    assert house.get()["layout"] == layout and house.view()["layout"] == layout


@pytest.mark.parametrize("entry, why", [
    ({"item": "sofa", "x": 9, "z": 0, "r": 0}, "sticks out of the right side (4 wide from 9)"),
    ({"item": "sofa", "x": 0, "z": 9, "r": 0}, "sticks out of the front (2 deep from 9)"),
    ({"item": "sofa", "x": 0, "z": 0, "r": 1}, None),                    # turned: 2 wide and 4 deep, fits
    ({"item": "sofa", "x": 11, "z": 0, "r": 1}, "turned, 2 wide from 11"),
    ({"item": "sofa", "x": -1, "z": 0, "r": 0}, "left of the room"), ({"item": "sofa", "x": 0, "z": -1, "r": 0}, "behind the wall"),
    ({"item": "sofa", "x": 0, "z": 0, "r": 4}, "no such turn"), ({"item": "sofa", "x": 0.5, "z": 0, "r": 0}, "between cells"), ({"item": "sofa", "x": True, "z": 0, "r": 0}, "a boolean is no number"),
    ({"item": "sofa", "x": "1", "z": 0, "r": 0}, "a string is no number"), ({"item": "sofa", "z": 0}, "no x"), ({"item": "nope", "x": 0, "z": 0}, "unknown item"), ({"x": 0, "z": 0}, "no item"),
    ({"item": "painting", "wall": "front", "x": 0}, "no such wall"), ({"item": "painting", "wall": "back", "x": 11}, "2 wide from 11"), ({"item": "painting", "wall": "left", "x": 9}, "2 wide from 9 (the left wall is 10 long)"),
    ({"item": "painting", "wall": "back", "x": -1}, "before the wall"), ({"item": "painting", "x": 1}, "no wall named"),
])
def test_what_does_not_fit_is_refused(entry, why):
    own(sofa=1, painting=1)
    if why is None:
        assert put(entry)
    else:
        rejects(entry, match="fit|hanging|standing")


def test_you_can_only_place_what_you_own_and_only_as_many_as_you_own():
    own(fern=1)
    rejects({"item": "fern", "x": 0, "z": 0}, {"item": "fern", "x": 2, "z": 0}, match="own that many")
    rejects({"item": "sofa", "x": 0, "z": 0}, match="own that many")
    assert put({"item": "fern", "x": 0, "z": 0})


def test_two_things_never_stand_in_the_same_cell_but_rugs_can_be_stood_on():
    own(sofa=1, armchair=1, fern=1, **{"rug-rect": 1, "rug-round": 1}, painting=2, clock=1, ketupat=1)
    rejects({"item": "sofa", "x": 0, "z": 0}, {"item": "armchair", "x": 3, "z": 1}, match="standing")          # sofa covers x 0..3, z 0..1; the armchair starts at x 3
    assert put({"item": "sofa", "x": 0, "z": 0}, {"item": "armchair", "x": 4, "z": 0})                           # next to it is fine
    assert put({"item": "rug-rect", "x": 0, "z": 0}, {"item": "sofa", "x": 0, "z": 0}, {"item": "fern", "x": 1, "z": 2})   # on a rug is fine
    rejects({"item": "rug-rect", "x": 0, "z": 0}, {"item": "rug-round", "x": 3, "z": 2}, match="standing")       # a rug on a rug is not
    rejects({"item": "painting", "wall": "back", "x": 0}, {"item": "clock", "wall": "back", "x": 1}, match="hanging")   # painting covers 0..1
    assert put({"item": "painting", "wall": "back", "x": 0}, {"item": "clock", "wall": "back", "x": 2}, {"item": "painting", "wall": "left", "x": 0}, {"item": "ketupat", "wall": "left", "x": 5})
    assert put({"item": "painting", "wall": "back", "x": 0}, {"item": "fern", "x": 0, "z": 0})                    # something may stand in front of a painting


def test_turning_a_thing_swaps_its_sides():
    own(sofa=2)
    put({"item": "sofa", "x": 0, "z": 0, "r": 1})                          # now 2 wide and 4 deep: z 0..3
    rejects({"item": "sofa", "x": 0, "z": 0, "r": 1}, {"item": "sofa", "x": 1, "z": 3, "r": 0}, match="standing")   # (the other sofa, 4 wide, starts at z 3 and x 1: x 1 is inside the turned one)
    assert put({"item": "sofa", "x": 0, "z": 0, "r": 1}, {"item": "sofa", "x": 0, "z": 4, "r": 0})


def test_a_layout_is_refused_whole_and_the_old_one_stays():
    own(fern=2)
    put({"item": "fern", "x": 1, "z": 1})
    rejects({"item": "fern", "x": 5, "z": 5}, {"item": "fern", "x": 99, "z": 5})
    assert house.get()["layout"] == [{"item": "fern", "x": 1, "z": 1, "r": 0}]
    for bad in ("sofa", {"item": "fern"}, None, 5):
        with pytest.raises(house.HouseError):
            house.save_layout(bad)
    with pytest.raises(house.HouseError):
        house.save_layout([{"item": "fern", "x": 0, "z": 0}] * (house.MAX_PLACED + 1))


def test_a_house_can_be_full_of_things():
    own(succulent=house.MAX_PLACED)
    cells = [{"item": "succulent", "x": x, "z": z, "r": 0} for z in range(house.ROOM_D) for x in range(house.ROOM_W)][:house.MAX_PLACED]
    assert len(put(*cells)) == house.MAX_PLACED


# ---------------------------------------------------------------- what a visitor sees
def test_a_visitor_sees_the_room_but_not_the_points_or_the_cupboard():
    give(1500)
    house.buy("fern")
    house.buy("sofa")
    put({"item": "fern", "x": 1, "z": 1})
    shown = house.public_view("en")
    assert shown["layout"] == [{"item": "fern", "x": 1, "z": 1, "r": 0}] and [i["id"] for i in shown["items"]] == ["fern"]
    assert "balance" not in shown and "owned" not in str(shown) and "sofa" not in str(shown) and shown["floor"] == "wood"
    mine = house.view("en")
    assert mine["balance"] == 1500 - house.CATALOG["fern"].price - house.CATALOG["sofa"].price and {i["id"]: i["owned"] for i in mine["items"]}["sofa"] == 1


def test_the_shop_speaks_the_visitors_language():
    zh = {i["id"]: i["name"] for i in house.view("zh")["items"]}
    ms = {i["id"]: i["name"] for i in house.view("ms")["items"]}
    assert zh["sofa"] == "沙发" and ms["sofa"] == "Sofa" and zh["fern"] != "Fern" and ms["fern"] == "Pakis"
    assert house.view("zh")["categories"][0]["name"] == "植物" and [c["id"] for c in house.view("en")["categories"]] == list(house.CATEGORIES)
    names = {s["id"]: s["name"] for s in house.view("zh")["styles"]["floor"]}
    assert names["wood"] == "木地板"


# ---------------------------------------------------------------- pets that follow you
def test_a_pet_may_follow_its_owner_and_only_a_pet_and_only_three_at_once():
    own(**{"pet-fox": 1, "pet-cat": 1, "pet-owl": 1, "pet-frog": 1}, fern=1, sofa=1)
    layout = put({"item": "pet-fox", "x": 1, "z": 1, "follow": True}, {"item": "pet-cat", "x": 3, "z": 1}, {"item": "fern", "x": 5, "z": 1, "follow": True}, {"item": "sofa", "x": 6, "z": 4, "follow": True})
    assert layout[0] == {"item": "pet-fox", "x": 1, "z": 1, "r": 0, "follow": True}
    assert "follow" not in layout[1] and "follow" not in layout[2] and "follow" not in layout[3]        # (a plant cannot walk; "false" is just left out)
    three = [{"item": p, "x": 1 + 2 * i, "z": 1, "follow": True} for i, p in enumerate(("pet-fox", "pet-cat", "pet-owl"))]
    assert [e.get("follow") for e in put(*three)] == [True, True, True]
    with pytest.raises(house.HouseError, match="three pets"):
        house.save_layout(three + [{"item": "pet-frog", "x": 7, "z": 1, "follow": True}])
    assert [e.get("follow") for e in house.get()["layout"]] == [True, True, True]                      # (refused whole: the old layout stays)
    assert put({"item": "pet-fox", "x": 1, "z": 1, "follow": "yes"}, {"item": "pet-cat", "x": 3, "z": 1, "follow": 1})[0].get("follow") is None      # (only a real true counts)
    assert house.view()["max_followers"] == house.MAX_FOLLOWERS == 3


def test_a_visitor_sees_the_pets_that_follow_the_owner():
    own(**{"pet-fox": 1})
    put({"item": "pet-fox", "x": 2, "z": 2, "follow": True})
    assert house.public_view()["layout"] == [{"item": "pet-fox", "x": 2, "z": 2, "r": 0, "follow": True}]
