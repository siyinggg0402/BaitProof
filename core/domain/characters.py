"""A person's character: the little human that lives in their house, drives their car and shows beside their name. A look is a short code, "p.S.H.C.O.K.A.F", of seven
numbers: skin tone, hair style, hair colour, outfit style, outfit colour, accessory, face. The tables are here once; the web pages and the 3D scenes read them (the page
embeds them as JSON), so a code means the same thing everywhere. Every table only ever grows at the END, and the seventh number is optional (a six-number code, from before
the faces, means "rosy cheeks"), so a look somebody saved keeps looking the same. Profiles made before there were characters have an animal picture instead (core/storage/accounts.py)."""
from __future__ import annotations

import hashlib
import random
import re

SKINS = ("#FBE0C8", "#F5CFA8", "#E8B98A", "#D29B6B", "#B87B50", "#946038", "#6F4528", "#4A2E1B")                   # light to deep
HAIR_STYLES = ("short", "bob", "long", "ponytail", "bun", "curly", "buzz", "bald", "tudung", "sidepart", "spiky")
HAIR_COLORS = ("#1F1A1A", "#3B2A20", "#6B4A2F", "#A0522D", "#D8B66A", "#A7A7A7", "#7A5CD0", "#2BA3A3", "#E26BA6", "#2D3070")  # (a tudung takes the same colours)
OUTFIT_STYLES = ("tee", "hoodie", "shirt", "kurung", "jacket", "polo", "kurta")
OUTFIT_COLORS = ("#7A5CD0", "#E5546B", "#F08A4B", "#E3B23C", "#33B27C", "#3FA7E8", "#2D3070", "#F3F0FA", "#3B3B4F", "#E26BA6")
ACCESSORIES = ("none", "glasses", "round", "songkok", "cap", "flower")
FACES = ("soft", "plain", "stubble", "moustache", "goatee", "beard")                                        # soft = the rosy cheeks every character had; the rest drop the blush and give strong brows
NATURAL_HAIR = 6                                                                                           # the first six hair colours are natural; a beard or brows never take the others
MASCULINE_HAIR = ("short", "curly", "buzz", "bald", "sidepart", "spiky")                                    # (what a random look with facial hair is given)
MASCULINE_OUTFITS = ("tee", "hoodie", "shirt", "jacket", "polo", "kurta")
# what the options are called to people (English; the page translates them)
HAIR_NAMES = ("Short", "Bob", "Long", "Ponytail", "Bun", "Curly", "Buzz cut", "Bald", "Tudung", "Side part", "Spiky")
OUTFIT_NAMES = ("T-shirt", "Hoodie", "Shirt", "Baju kurung", "Jacket", "Polo", "Kurta")
ACCESSORY_NAMES = ("No accessory", "Glasses", "Round glasses", "Songkok", "Cap", "Flower")
FACE_NAMES = ("Rosy cheeks", "Plain", "Stubble", "Moustache", "Goatee", "Beard")
SIZES = (len(SKINS), len(HAIR_STYLES), len(HAIR_COLORS), len(OUTFIT_STYLES), len(OUTFIT_COLORS), len(ACCESSORIES), len(FACES))
FIELDS = ("skin", "hair", "hair_color", "outfit", "outfit_color", "accessory", "face")
_CODE = re.compile(r"p(?:\.\d{1,2}){6,7}")
DEFAULT = "p.2.0.1.0.0.0"


def parse(code: str) -> dict | None:
    """The numbers of a look code (the face is 0, rosy cheeks, when the code has only six), or None if it is not one."""
    if not isinstance(code, str) or not _CODE.fullmatch(code):
        return None
    nums = [int(x) for x in code.split(".")[1:]]
    nums += [0] * (len(SIZES) - len(nums))
    return dict(zip(FIELDS, nums)) if all(0 <= n < size for n, size in zip(nums, SIZES)) else None


def valid(code: str) -> bool:
    return parse(code) is not None


def make(skin: int, hair: int, hair_color: int, outfit: int, outfit_color: int, accessory: int, face: int | None = None) -> str:
    nums = (skin, hair, hair_color, outfit, outfit_color, accessory) + (() if face is None else (face,))
    return "p." + ".".join(str(n) for n in nums)


def random_look(rng: random.Random | None = None) -> str:
    """A look picked at random (a new profile starts with one). A songkok or a cap does not go on a tudung, and a beard is not paired with a baju kurung, a flower or long hair."""
    r = rng or random.SystemRandom()
    pick = [r.randrange(n) for n in SIZES]
    pick[6] = r.choice((0, 0, 1, 1, 2, 3, 4, 5))                       # about as many rosy and plain faces as faces with stubble, a moustache or a beard
    if pick[6] >= 2:
        if HAIR_STYLES[pick[1]] not in MASCULINE_HAIR:
            pick[1] = HAIR_STYLES.index(r.choice(MASCULINE_HAIR))
        if OUTFIT_STYLES[pick[3]] not in MASCULINE_OUTFITS:
            pick[3] = OUTFIT_STYLES.index(r.choice(MASCULINE_OUTFITS))
        if ACCESSORIES[pick[5]] == "flower":
            pick[5] = 0
    if HAIR_STYLES[pick[1]] == "tudung" and ACCESSORIES[pick[5]] in ("songkok", "cap"):
        pick[5] = 0
    return make(*pick)


def look_for(seed: str) -> str:
    """The same look every time for the same seed: what a person who has not made a character yet is shown."""
    return random_look(random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16)))


def tables() -> dict:
    """What the browser needs to draw a look: the colours, and the names of the styles (in the order of the numbers)."""
    return {"skins": SKINS, "hair": HAIR_STYLES, "hair_colors": HAIR_COLORS, "outfits": OUTFIT_STYLES, "outfit_colors": OUTFIT_COLORS, "accessories": ACCESSORIES, "faces": FACES, "masculine_hair": MASCULINE_HAIR, "masculine_outfits": MASCULINE_OUTFITS}
