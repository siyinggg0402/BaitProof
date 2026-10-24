"""Characters: a look is a short code of seven numbers (six, from before the faces, still work); it is validated everywhere it comes in, drawn as a flat portrait on the server, and who you are in the game is
your account's look, else the one saved with your game, else one made from your profile id."""
import random
import re

import pytest

from core.domain import characters as ch
from core.game import looks
from core.game import state as gs
from core.storage import accounts
from web import icons, portrait


@pytest.mark.parametrize("code, ok", [
    ("p.2.0.1.0.0.0", True), ("p.7.8.9.4.9.5", True), ("p.0.0.0.0.0.0", True),
    ("p.8.0.0.0.0.0", False), ("p.0.11.0.0.0.0", False), ("p.0.0.10.0.0.0", False), ("p.0.0.0.7.0.0", False), ("p.0.0.0.0.10.0", False), ("p.0.0.0.0.0.6", False),
    ("p.2.0.1.0.0.0.5", True), ("p.2.10.1.6.0.0.5", True), ("p.2.0.1.0.0.0.6", False), ("p.2.0.1.0.0.0.0.0", False),
    ("p.2.0.1.0.0", False), ("q.2.0.1.0.0.0", False), ("p.-1.0.1.0.0.0", False), ("p.a.0.1.0.0.0", False), ("", False), ("fox", False), (None, False), (7, False),
    (" p.2.0.1.0.0.0", False), ("p.2.0.1.0.0.0\n", False), ("P.2.0.1.0.0.0", False), ("p.2.0.1.0.0.0<script>", False),
])
def test_only_a_well_formed_look_in_range_is_a_look(code, ok):
    assert ch.valid(code) is ok and (ch.parse(code) is not None) is ok


def test_a_look_round_trips_and_the_tables_line_up():
    assert ch.parse("p.7.8.9.4.9.5") == {"skin": 7, "hair": 8, "hair_color": 9, "outfit": 4, "outfit_color": 9, "accessory": 5, "face": 0}      # (six numbers: rosy cheeks)
    assert ch.parse("p.7.10.9.6.9.5.4")["face"] == 4 and ch.make(7, 8, 9, 4, 9, 5) == "p.7.8.9.4.9.5" and ch.make(7, 8, 9, 4, 9, 5, 3) == "p.7.8.9.4.9.5.3" and ch.valid(ch.DEFAULT)
    assert ch.SIZES == (8, 11, 10, 7, 10, 6, 6) and len(ch.HAIR_NAMES) == 11 and len(ch.OUTFIT_NAMES) == 7 and len(ch.ACCESSORY_NAMES) == 6 and len(ch.FACE_NAMES) == 6
    assert ch.HAIR_STYLES[:9] == ("short", "bob", "long", "ponytail", "bun", "curly", "buzz", "bald", "tudung") and ch.OUTFIT_STYLES[:5] == ("tee", "hoodie", "shirt", "kurung", "jacket")   # (tables only grow at the end: a saved look keeps its look)
    assert set(ch.MASCULINE_HAIR) <= set(ch.HAIR_STYLES) and set(ch.MASCULINE_OUTFITS) <= set(ch.OUTFIT_STYLES) and ch.FACES[0] == "soft"
    assert all(re.fullmatch(r"#[0-9A-F]{6}", c) for c in (*ch.SKINS, *ch.HAIR_COLORS, *ch.OUTFIT_COLORS))
    assert "tudung" in ch.HAIR_STYLES and "songkok" in ch.ACCESSORIES and "kurung" in ch.OUTFIT_STYLES     # (for the families this is for)
    t = ch.tables()
    assert set(t) == {"skins", "hair", "hair_colors", "outfits", "outfit_colors", "accessories", "faces", "masculine_hair", "masculine_outfits"} and list(t["hair"]) == list(ch.HAIR_STYLES)


def test_a_random_look_is_always_valid_and_never_puts_a_cap_on_a_tudung():
    rng, seen = random.Random(3), set()
    for _ in range(600):
        code = ch.random_look(rng)
        look = ch.parse(code)
        assert look is not None
        if ch.HAIR_STYLES[look["hair"]] == "tudung":
            assert ch.ACCESSORIES[look["accessory"]] not in ("songkok", "cap")
        seen.add(look["hair"])
    assert seen == set(range(len(ch.HAIR_STYLES))) and ch.valid(ch.random_look())


def test_a_random_look_with_a_beard_is_a_man_s_look_and_the_faces_are_all_used():
    rng, faces, bearded = random.Random(5), set(), 0
    for _ in range(800):
        look = ch.parse(ch.random_look(rng))
        faces.add(look["face"])
        if look["face"] >= 2:
            bearded += 1
            assert ch.HAIR_STYLES[look["hair"]] in ch.MASCULINE_HAIR and ch.OUTFIT_STYLES[look["outfit"]] in ch.MASCULINE_OUTFITS and ch.ACCESSORIES[look["accessory"]] != "flower"
    assert faces == set(range(6)) and 200 < bearded < 500


def test_a_look_made_from_a_seed_is_always_the_same_one():
    assert ch.look_for("a" * 32) == ch.look_for("a" * 32) and ch.valid(ch.look_for("local"))
    assert len({ch.look_for(f"profile-{i}") for i in range(30)}) > 20


# ---------------------------------------------------------------- the flat portrait
def test_every_look_has_a_portrait_made_of_layers_that_exist():
    rng = random.Random(1)
    for _ in range(300):
        code = ch.random_look(rng)
        layers = portrait.layers_for(code)
        names = [n for n, _ in layers]
        assert set(names) <= set(portrait.LAYERS), code
        assert names.index("pt-body") < names.index("pt-neck") < names.index("pt-head") < names.index("pt-face")       # bottom first
        look = ch.parse(code)
        hair, acc = ch.HAIR_STYLES[look["hair"]], ch.ACCESSORIES[look["accessory"]]
        assert (f"pt-acc-{acc}" in names) == (acc != "none" and not (hair == "tudung" and acc in ("songkok", "cap")))
        assert (f"pt-hairf-{hair}" in names) == (hair != "bald") and any(n.startswith("pt-det-") for n in names)
        fills = dict(layers)
        assert fills["pt-head"] == ch.SKINS[look["skin"]] and fills["pt-body"] == ch.OUTFIT_COLORS[look["outfit_color"]] and fills["pt-face"] is None
    assert portrait.layers_for("fox") == [] and portrait.layers_for("p.9.9.9.9.9.9") == [] and portrait.layers_for("p.0.0.0.0.0.0.9") == []
    assert [n for n, _ in portrait.layers_for("p.2.0.1.0.0.0")].count("pt-blush") == 1 and "pt-blush" not in [n for n, _ in portrait.layers_for("p.2.9.1.5.0.0.5")]    # (rosy cheeks, or brows and a beard)
    assert {n for n in portrait.LAYERS if n.startswith("pt-det-")} == {f"pt-det-{o}" for o in ch.OUTFIT_STYLES}
    assert {n for n in portrait.LAYERS if n.startswith("pt-acc-")} == {f"pt-acc-{a}" for a in ch.ACCESSORIES if a != "none"}
    assert {n for n in portrait.LAYERS if n.startswith("pt-fh-")} == {f"pt-fh-{f}" for f in ch.FACES if f not in ("soft", "plain")} and {"pt-blush", "pt-brows"} <= set(portrait.LAYERS)
    assert {n[len("pt-hairf-"):] for n in portrait.LAYERS if n.startswith("pt-hairf-")} | {"bald"} == set(ch.HAIR_STYLES)


def test_the_sprite_carries_every_layer_and_a_portrait_uses_them_with_the_looks_colours():
    sprite = str(icons.sprite())
    assert all(f'<g id="{n}">' in sprite for n in portrait.LAYERS) and "style=" not in sprite and "<script" not in sprite
    svg = str(portrait.portrait("p.3.2.1.4.5.1"))
    assert svg.startswith('<svg class="pt"') and f'fill="{ch.SKINS[3]}"' in svg and f'fill="{ch.HAIR_COLORS[1]}"' in svg and f'fill="{ch.OUTFIT_COLORS[5]}"' in svg and "#pt-acc-glasses" in svg
    for g in re.findall(r'<g id="pt-[^>]*>(.*?)</g>', sprite):
        assert all(re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s-]+", d) for d in re.findall(r' d="([^"]*)"', g)), "path data only"
    assert 'data-av="p.3.2.1.4.5.1"' in str(icons.avatar("p.3.2.1.4.5.1")) and 'data-av="fish"' in str(icons.avatar("p.9.9.9.9.9.9")) and 'data-av="fox"' in str(icons.avatar("fox"))
    assert str(icons.avatar('p.1.1.1.1.1.1" onload="x')).count("onload") == 0      # (whatever is sent is never put in the page as markup)


# ---------------------------------------------------------------- who you are in the game
ME, MEI = "a" * 32, "b" * 32


def test_your_character_is_the_look_of_your_account_else_the_saved_one_else_one_made_from_your_id(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert looks.character(ME) == ch.look_for(ME) and not looks.has_character(ME)
    looks.set_character(ME, "p.1.2.3.4.5.0")
    assert looks.character(ME) == "p.1.2.3.4.5.0" and looks.has_character(ME) and accounts.get(ME) is None
    accounts.create(ME, "Aiman", "fox")                                         # an old animal avatar does not count as a character
    assert looks.character(ME) == "p.1.2.3.4.5.0"
    looks.set_character(ME, "p.2.2.2.2.2.2")                                    # saving one also changes what friends see
    assert accounts.get(ME)["avatar"] == "p.2.2.2.2.2.2" and looks.character(ME) == "p.2.2.2.2.2.2"
    with pytest.raises(looks.LookError):
        looks.set_character(ME, "fox")
    with pytest.raises(looks.LookError):
        looks.set_character(ME, "p.9.9.9.9.9.9")
    assert gs.get()["look"] == "p.2.2.2.2.2.2"


def test_a_new_account_starts_with_a_random_character_and_old_pictures_are_still_accepted():
    acct, _ = accounts.create(MEI, "Mei", "")
    assert ch.valid(acct["avatar"])
    other, _ = accounts.create("c" * 32, "Lin", "🦊")                           # an emoji from an old page becomes the fox
    assert other["avatar"] == "fox"
    third, _ = accounts.create("d" * 32, "Sam", "p.3.1.4.1.5.2")
    assert third["avatar"] == "p.3.1.4.1.5.2" and accounts.update("d" * 32, avatar="p.0.0.0.0.0.0")["avatar"] == "p.0.0.0.0.0.0"
    assert accounts.update("d" * 32, avatar="p.9.9.9.9.9.9")["avatar"] == "p.0.0.0.0.0.0" and accounts.update("d" * 32, avatar="")["avatar"] == "p.0.0.0.0.0.0"
    assert accounts.update("c" * 32, avatar="p.4.4.4.4.4.4")["avatar"] == "p.4.4.4.4.4.4"        # and a fox can become a person


def test_you_may_visit_your_own_house_and_a_friends_and_nobody_elses():
    for pid, name in ((ME, "Aiman"), (MEI, "Mei"), ("c" * 32, "Lin")):
        accounts.create(pid, name)
    pub = {n: accounts.get(p)["pub"] for p, n in ((ME, "Aiman"), (MEI, "Mei"), ("c" * 32, "Lin"))}
    assert accounts.visit_target(ME, pub["Aiman"])[0] == ME                       # your own
    assert accounts.visit_target(ME, pub["Mei"]) is None                          # not a friend yet
    accounts.add_friend(ME, accounts.get(MEI)["friend_code"])
    profile, card = accounts.visit_target(ME, pub["Mei"])
    assert profile == MEI and card["nickname"] == "Mei" and set(card) == {"pub", "nickname", "avatar"}
    assert accounts.visit_target(MEI, pub["Aiman"])[0] == ME and accounts.visit_target(ME, pub["Lin"]) is None and accounts.visit_target(ME, "nobody") is None
