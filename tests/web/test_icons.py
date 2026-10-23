"""The website draws icons and never uses emoji (the Telegram bot keeps its emoji: that is a chat). What is checked: no emoji in any template, script or stylesheet;
every icon a page or script asks for exists; the avatars, festivals and old emoji avatars all line up; and the pages that are served carry none."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.domain import seasons
from core.storage import accounts, db
from web import deps, icons, ui
from web.main import app

WEB = Path(__file__).resolve().parents[2] / "web"
SOURCES = sorted([*WEB.glob("templates/*.html"), *WEB.glob("static/js/*.js"), *WEB.glob("static/css/*.css"), WEB / "icons.py", WEB / "static" / "sw.js"])
EMOJI = ui._EMOJI
NOT_ICONS = {"lg", "xl", "off", "m-gold", "m-silver", "m-bronze", "fill"}   # (classes passed beside a name)


@pytest.fixture(autouse=True)
def public_site(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    deps.HITS.clear()
    deps.LOGIN_HITS.clear()


def visitor(lang="en"):
    c = TestClient(app)
    c.cookies.set("lang", lang)
    c.get("/")
    return c


def test_no_emoji_in_any_template_script_or_stylesheet():
    found = {f.name: EMOJI.findall(f.read_text()) for f in SOURCES}
    assert not {k: v for k, v in found.items() if v}, "draw an icon (web/icons.py) instead"


def names_asked_for():
    """Every icon name the templates and scripts ask for, by the few ways they do it."""
    asked = set()
    for f in SOURCES:
        if f.suffix not in (".html", ".js"):
            continue
        s = f.read_text()
        for call in re.findall(r"\bicon\(([^()]*)\)", s):
            asked |= set(re.findall(r""":\s*["']([\w-]+)["']""" if "{" in call else r"""["']([\w-]+)["']""", call))   # (a table of names: its values)
        asked |= set(re.findall(r'\bmode\("([\w-]+)"', s))
        asked |= set(re.findall(r'\bchoice\("\w+", "([\w-]+)"', s))
        asked |= set(re.findall(r'\bsignTexture\("([\w-]+)"', s))
        if f.name in ("game.js", "road.js"):   # (a title or a source line chosen by an if: ["icon name", t("text")])
            asked |= set(re.findall(r'[?:]\s*\[\s*"([\w-]+)",\s*t\(', s))
        for table in re.findall(r"\b(?:hatIcon|ICON) = \{([^}]*)\}", s):
            asked |= set(re.findall(r':\s*"([\w-]+)"', table))
        for call in re.findall(r"\b(?:tag|rankSpan)\(([^()]*)\)", s):
            asked |= set(re.findall(r'"([\w-]+)"', call)) & set(icons.ICONS)
    return asked - NOT_ICONS


def test_every_icon_the_site_asks_for_is_drawn():
    asked = names_asked_for()
    assert len(asked) > 30, "the scan should find the site's icons"
    assert not asked - set(icons.ICONS), f"not drawn: {sorted(asked - set(icons.ICONS))}"


def test_every_festival_has_its_own_icon():
    assert {icons_name for _, icons_name, _, _ in seasons.FESTIVALS.values()} <= set(icons.ICONS)
    assert len({n for _, n, _, _ in seasons.FESTIVALS.values()}) == len(seasons.FESTIVALS)


def test_the_avatars_line_up_and_old_emoji_avatars_still_work():
    assert set(accounts.AVATARS) == set(icons.AVATAR_IDS) and len(accounts.AVATARS) == 12
    assert all(f"av-{a}" in icons.ICONS for a in accounts.AVATARS)
    assert set(accounts.LEGACY_AVATARS.values()) <= set(accounts.AVATARS) and len(accounts.LEGACY_AVATARS) == 12
    assert 'data-av="fish"' in icons.avatar("🦊") and 'data-av="fox"' in icons.avatar("fox")   # (an emoji that was never converted shows the fish)
    c = visitor()
    assert c.post("/me/create", data={"nickname": "Aiman", "avatar": "🦊"}).status_code == 200      # a page left open from before the pictures
    assert accounts.get(c.cookies.get("bp"))["avatar"] == "fox"


def test_profiles_made_with_emoji_avatars_are_converted_when_the_database_opens():
    with db.connect(shared=True) as c:
        for i, avatar in enumerate(["🦊", "🐳", "🦁", "🤖"]):   # (the last is no avatar we ever offered)
            c.execute("INSERT INTO accounts(profile,pub,nickname,avatar,friend_code,key_hash,created) VALUES(?,?,?,?,?,?,?)",
                      (f"{i:032x}", f"pub{i}", f"Old{i}", avatar, f"CODE{i}", f"hash{i}", db.iso(db.now())))
    with db.connect(shared=True) as c:
        assert [r["avatar"] for r in c.execute("SELECT avatar FROM accounts ORDER BY profile")] == ["fox", "cat", "lion", "fish"]


def test_the_sprite_is_plain_paths_and_safe_for_a_strict_csp():
    sprite = str(icons.sprite())
    assert sprite.count("<symbol ") == len(icons.ICONS)
    assert "style=" not in sprite and "<script" not in sprite and "<use" not in sprite and "href" not in sprite
    assert all(re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s-]+", p.lstrip("~")) for paths in icons.ICONS.values() for p in paths), "path data only"
    assert 'aria-hidden="true"' in str(icons.icon("camera")) and '<use href="#i-camera"/>' in str(icons.icon("camera"))
    with pytest.raises(KeyError):
        icons.icon("nope")


def test_plain_removes_emoji_and_keeps_the_words_and_the_lines():
    assert ui.plain("🚨 SCAM. Don't pay") == "SCAM. Don't pay"
    assert ui.plain("👪 The Lims on Baitproof this week\nA minute of practice keeps everyone safer. 🐟") == "The Lims on Baitproof this week\nA minute of practice keeps everyone safer."
    assert ui.plain("Next →") == "Next →" and ui.plain("") == "" and ui.plain(None) == ""


PAGES = ["/", "/train", "/records", "/friends", "/road", "/link", "/me", "/signin", "/game", "/duel", "/family"]


@pytest.mark.parametrize("lang", ["en", "zh", "ms"])
def test_the_pages_carry_no_emoji(lang):
    c = visitor(lang)
    assert c.post("/me/create", data={"nickname": "Aiman", "avatar": "fox"}).status_code == 200
    seen = {}
    for path in PAGES:
        r = c.get(path)
        if r.status_code == 200:
            seen[path] = EMOJI.findall(r.text)
    assert len(seen) >= 8, seen.keys()
    assert not {k: v for k, v in seen.items() if v}


def test_a_result_and_its_read_aloud_text_carry_no_emoji():
    c = visitor()
    html = c.post("/check", data={"message": "Pay with gift cards today or you will be arrested. IRS notice."}).text
    assert 'id="result"' in html and "#i-lifebuoy" in html and "#i-thumb-up" in html and "#i-volume" in html
    assert not EMOJI.findall(html)
    assert 'data-say="SCAM' in html or 'data-say="' in html and not re.search(r'data-say="[^"]*[\U0001F000-\U0001FAFF]', html)
