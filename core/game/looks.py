"""Who you are in the game: your character. What other people see beside your name is your account's avatar (a look code); the house and the road use `character`, which
is always a human: the account's look if it has one, else the one saved with your game, else one made from your profile id (so you look the same every time)."""
from __future__ import annotations

from core.domain import characters
from core.game import state as gs
from core.storage import accounts


class LookError(ValueError):
    pass


def character(profile: str) -> str:
    acct = accounts.get(profile)
    if acct and characters.valid(acct["avatar"]):
        return acct["avatar"]
    saved = gs.get()["look"]
    return saved if characters.valid(saved) else characters.look_for(profile)


def has_character(profile: str) -> bool:
    acct = accounts.get(profile)
    return bool(acct and characters.valid(acct["avatar"])) or characters.valid(gs.get()["look"])


def set_character(profile: str, code: str) -> str:
    if not characters.valid(code):
        raise LookError("That isn't a character.")
    s = gs.get()
    s["look"] = code
    gs.save(s)
    if accounts.get(profile):
        accounts.update(profile, avatar=code)
    return code
