"""Link Hunt: four links that each claim to belong to a company; one is a fake. The right answer never leaves the server until you have chosen, the fakes are
made with the same tricks scam sites really use (an added word, a throwaway ending, look-alike letters, a real name buried in a longer address, a swapped letter,
a hyphen through the name), and every round trains the "fake website address" trick in the same personal model as the other games. Three wrong picks end the run."""
from __future__ import annotations

import random
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from core.domain.tactics import TACTICS
from core.game import engine
from core.game import state as gs
from core.lang.i18n import norm, tactic_text, tr
from core.storage import accounts, model, runs

LIVES = 3
POINTS = 100
TTL = 3600.0
TACTIC = "lookalike-link"
# a company and its real address; chosen for the places our players live, plus the big names scams imitate everywhere
BRANDS: list[tuple[str, str]] = [
    ("Maybank", "maybank2u.com.my"), ("CIMB Clicks", "cimbclicks.com.my"), ("Public Bank", "publicbank.com.my"), ("Shopee", "shopee.com.my"), ("Lazada", "lazada.sg"),
    ("Grab", "grab.com"), ("DBS", "dbs.com.sg"), ("POSB", "posb.com.sg"), ("SingPost", "singpost.com"), ("Singpass", "singpass.gov.sg"), ("IRAS", "iras.gov.sg"),
    ("CPF", "cpf.gov.sg"), ("Touch 'n Go", "touchngo.com.my"), ("Pos Laju", "poslaju.com.my"), ("TNB", "tnb.com.my"), ("LHDN", "hasil.gov.my"), ("JPJ", "jpj.gov.my"),
    ("PayPal", "paypal.com"), ("Netflix", "netflix.com"), ("DHL", "dhl.com"), ("Amazon", "amazon.com"), ("WhatsApp", "whatsapp.com"), ("Apple", "apple.com"),
    ("Google", "google.com"), ("Facebook", "facebook.com"), ("Telegram", "telegram.org"), ("TikTok", "tiktok.com"), ("Alipay", "alipay.com"), ("Spotify", "spotify.com"),
]
WORDS = ("secure", "login", "verify", "support", "update", "account", "help", "refund")
BAD_TLDS = ("top", "xyz", "click", "icu", "cc", "vip", "online", "site")
GLYPHS = {"m": "rn", "l": "1", "o": "0", "i": "l", "w": "vv", "a": "4", "e": "3"}
TRICKS = ("extra-word", "bad-tld", "lookalike-letters", "subdomain-trick", "swapped-letters", "hyphen-split")


class LinkError(ValueError):
    pass


def _stem(host: str) -> tuple[str, str]:
    """'maybank2u.com.my' -> ('maybank2u', 'com.my')"""
    first, _, rest = host.partition(".")
    return first, rest


def fake_of(host: str, rng: random.Random) -> tuple[str, str, dict]:
    """A fake address for this real one, the trick used, and the values the explanation needs."""
    stem, rest = _stem(host)
    trick = rng.choice(TRICKS)
    if trick == "extra-word":
        word = rng.choice(WORDS)
        return f"{stem}-{word}.{rest}", trick, {"word": word}
    if trick == "bad-tld":
        tld = rng.choice(BAD_TLDS)
        return f"{stem}.{tld}", trick, {"tld": tld}
    if trick == "lookalike-letters":
        spots = [(i, c) for i, c in enumerate(stem) if c in GLYPHS]
        if not spots:
            return fake_of(host, rng)
        i, c = rng.choice(spots)
        return f"{stem[:i]}{GLYPHS[c]}{stem[i + 1:]}.{rest}", trick, {}
    if trick == "subdomain-trick":
        word = rng.choice(WORDS)
        tail = f"{word}-{rng.randint(10, 99)}.{rng.choice(BAD_TLDS)}"
        return f"{host}.{tail}", trick, {"tail": tail}
    if trick == "swapped-letters":
        if len(stem) < 4:
            return fake_of(host, rng)
        i = rng.randrange(1, len(stem) - 1)
        swapped = stem[:i] + stem[i + 1] + stem[i] + stem[i + 2:]
        return (f"{swapped}.{rest}" if swapped != stem else f"{stem[:i]}{stem[i + 1:]}.{rest}"), trick, {}
    i = rng.randrange(2, max(3, len(stem) - 1)) if len(stem) > 4 else 2          # hyphen-split
    return f"{stem[:i]}-{stem[i:]}.{rest}", "hyphen-split", {}


@dataclass
class Hunt:
    id: str
    owner: str
    lang: str
    rng: random.Random
    lives: int = LIVES
    score: int = 0
    combo: int = 0
    best_combo: int = 0
    correct: int = 0
    wrong: int = 0
    xp: int = 0
    start_level: int = 1
    question: dict | None = None
    seen: list = field(default_factory=list)
    finished: bool = False
    summary: dict | None = None
    created: float = field(default_factory=time.time)

    @property
    def over(self) -> bool:
        return self.lives <= 0


_hunts: "OrderedDict[str, Hunt]" = OrderedDict()


def _store(h: Hunt) -> None:
    now = time.time()
    for k in [k for k, v in _hunts.items() if now - v.created > TTL]:
        _hunts.pop(k, None)
    while len(_hunts) >= 300:
        _hunts.popitem(last=False)
    _hunts[h.id] = h


def get(hunt_id: str, owner: str) -> Hunt:
    h = _hunts.get(hunt_id)
    if h is None or time.time() - h.created > TTL or h.owner != owner:
        raise LinkError("That round has expired. Start a new one.")
    return h


def _ask(h: Hunt) -> dict:
    """The next question: four companies (not asked lately), the real address of three of them, and a fake of the fourth. Answers stay here."""
    fresh = [b for b in BRANDS if b[0] not in h.seen[-8:]]
    four = h.rng.sample(fresh, 4)
    target = h.rng.randrange(4)
    options, answer = [], {}
    for i, (name, host) in enumerate(four):
        if i == target:
            fake, trick, vals = fake_of(host, h.rng)
            while fake in {b[1] for b in BRANDS}:
                fake, trick, vals = fake_of(host, h.rng)
            options.append({"brand": name, "host": fake})
            answer = {"index": i, "brand": name, "real": host, "fake": fake, "trick": trick, "values": vals}
        else:
            options.append({"brand": name, "host": host})
    h.seen.append(four[target][0])
    h.question = {"id": uuid.uuid4().hex[:8], "options": options, "answer": answer}
    return public(h.question)


def public(q: dict) -> dict:
    return {"id": q["id"], "options": q["options"]}


def start(owner: str, lang: str = "en", rng: random.Random | None = None) -> dict:
    h = Hunt(uuid.uuid4().hex[:12], owner, norm(lang), rng or random.Random(random.getrandbits(64)), start_level=gs.level_for(gs.get()["xp"]))
    first = _ask(h)
    _store(h)
    return {"hunt": h.id, "lives": h.lives, "question": first, "best": runs.best(owner, runs.LINK), "account": accounts.get(owner) is not None}


EXPLAIN = {
    "extra-word": "A real company doesn't add words like “{word}” to its address. {fake} is a fake: the real one is {real}.",
    "bad-tld": "{fake} ends in .{tld}, an ending scam sites love. The real address is {real}.",
    "lookalike-letters": "{fake} swaps in look-alike letters. Read it letter by letter: the real address is {real}.",
    "subdomain-trick": "In {fake} the company's name is only the beginning. The address really ends in {tail}. The real one is {real}.",
    "swapped-letters": "{fake} has a letter missing or swapped. The real address is {real}.",
    "hyphen-split": "{fake} splits the name with a hyphen. The real address is {real}.",
}


def explain(trick: str, vals: dict, fake: str, real: str, lang: str) -> str:
    return tr(EXPLAIN[trick], lang, fake=fake, real=real, **vals)


def answer(h: Hunt, question_id: str, choice: int, lang: str = "en") -> dict:
    if h.finished or h.over:
        raise LinkError("This round is over.")
    q = h.question
    if q is None or q["id"] != question_id:
        raise LinkError("That question isn't the current one.")
    if choice not in (0, 1, 2, 3):
        raise LinkError("Pick one of the four links.")
    a = q["answer"]
    right = choice == a["index"]
    gain = 0
    if right:
        gain = engine.XP_CORRECT + engine.XP_COMBO_STEP * min(h.combo, engine.XP_COMBO_CAP)
        h.combo += 1
        h.best_combo = max(h.best_combo, h.combo)
        h.correct += 1
        h.score += POINTS
    else:
        h.combo, h.wrong, h.lives = 0, h.wrong + 1, h.lives - 1
    h.xp += gain
    model.record_result(TACTIC, "correct" if right else "incorrect")
    s = gs.get()
    s["xp"] += gain
    gs.save(s)
    h.question = None
    nxt = None if h.over else _ask(h)
    return {"correct": right, "fake": a["index"], "real": a["real"], "brand": a["brand"], "tell": explain(a["trick"], a["values"], a["fake"], a["real"], lang), "xp": gain,
            "combo": h.combo, "lives": h.lives, "score": h.score, "over": h.over, "next": nxt, "trick": tactic_text(TACTIC, "label", lang, TACTICS)}


def finish(h: Hunt, lang: str = "en") -> dict:
    if h.summary is not None:
        return h.summary
    s = gs.get()
    before = runs.best(h.owner, runs.LINK)
    if h.correct or h.wrong:
        s["rounds"] += 1
        s["correct_total"] += h.correct
        gs.touch_streak(s)
        runs.record(h.owner, runs.LINK, h.score, h.correct)
    bonus = engine.XP_FINISH if h.correct >= 5 else 0
    s["xp"] += bonus
    h.xp += bonus
    want = ["first-round"] if (h.correct or h.wrong) else []
    if h.correct >= 10:
        want.append("link-10")
    new = [b for b in dict.fromkeys(want) if b not in s["badges"] and b in gs.BADGES]
    s["badges"] += new
    level = gs.level_for(s["xp"])
    gs.save(s)
    h.finished = True
    h.summary = {"score": h.score, "correct": h.correct, "wrong": h.wrong, "best_combo": h.best_combo, "xp_gained": h.xp, "level_up": level > h.start_level, "new_best": h.score > before and bool(h.score),
                 "personal_best": max(before, h.score), "badges_new": [{"id": b, "title": gs.badge_text(b, lang)[0], "desc": gs.badge_text(b, lang)[1]} for b in new],
                 "board": runs.board(h.owner, "week", runs.LINK)[:6] if accounts.get(h.owner) else [], "account": accounts.get(h.owner) is not None}
    return h.summary

