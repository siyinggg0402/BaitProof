"""The house through the website: your own room (buy, place, character), a friend's room (read-only, friends only), and that the page carries what the 3D room needs."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from core.domain import characters as ch
from core.game import house
from core.game import state as gs
from core.storage import accounts, db
from web import deps
from web.main import app

HEX32 = re.compile(r"\b[0-9a-f]{32}\b")


@pytest.fixture(autouse=True)
def public_site(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    deps.HITS.clear()
    deps.LOGIN_HITS.clear()
    accounts._TRIES.clear()


def visitor(lang="en"):
    c = TestClient(app)
    c.cookies.set("lang", lang)
    c.get("/")
    return c


def pid(c):
    return c.cookies.get("bp")


def sign_up(c, name):
    assert c.post("/me/create", data={"nickname": name, "avatar": ch.random_look()}).status_code == 200
    return accounts.get(pid(c))


def earn(c, xp):
    db.set_profile(pid(c))
    s = gs.get()
    s["xp"] = xp
    gs.save(s)
    db.set_profile(None)


def befriend(a, b):
    accounts.add_friend(pid(a), accounts.get(pid(b))["friend_code"])


# ---------------------------------------------------------------- your own house
def test_a_new_visitor_has_an_empty_room_a_character_and_nothing_to_spend():
    c = visitor()
    page = c.get("/house")
    assert page.status_code == 200 and "no-store" in page.headers["cache-control"] and 'id="house"' in page.text and 'id="shop"' in page.text and 'id="char-sheet"' in page.text
    assert 'data-visit=""' in page.text and "#i-star" in page.text and "#i-user" in page.text and "Your house" in page.text
    tables = json.loads(re.search(r'<script type="application/json" id="look-tables">(.*?)</script>', page.text).group(1))
    assert tables == json.loads(json.dumps(ch.tables()))                       # (the browser draws characters from the server's own tables)
    d = c.get("/api/house").json()
    assert d["balance"] == 0 and d["layout"] == [] and d["room"] == {"w": 12, "d": 10} and d["floor"] == "wood" and d["wall"] == "lilac" and d["visit"] is False
    assert ch.valid(d["look"]) and d["has_character"] is False and len(d["items"]) >= 60 and all(i["owned"] == 0 for i in d["items"])
    assert [c["id"] for c in d["categories"]] == ["plants", "furniture", "decor", "wall", "festival", "pets"] and not HEX32.search(json.dumps(d))


def test_you_buy_with_the_xp_you_earned_and_the_server_keeps_the_count():
    c = visitor()
    r = c.post("/api/house/buy", json={"item": "fern"})
    assert r.status_code == 400 and "enough XP" in r.json()["detail"]
    earn(c, 200)
    fern = house.CATALOG["fern"].price
    d = c.post("/api/house/buy", json={"item": "fern"}).json()
    assert d["balance"] == 200 - fern and {i["id"]: i["owned"] for i in d["items"]}["fern"] == 1
    assert c.post("/api/house/buy", json={"item": "nope"}).status_code == 400
    assert c.get("/api/house").json()["balance"] == 200 - fern
    assert visitor().get("/api/house").json()["balance"] == 0                  # nobody else's wallet moved


def test_a_layout_is_saved_checked_and_refused_whole_when_it_does_not_fit():
    c = visitor()
    earn(c, 1500)
    c.post("/api/house/buy", json={"item": "sofa"})
    c.post("/api/house/buy", json={"item": "fern"})
    ok = c.post("/api/house/layout", json={"layout": [{"item": "sofa", "x": 2, "z": 4, "r": 0}, {"item": "fern", "x": 8, "z": 1, "r": 0}]})
    assert ok.status_code == 200 and len(ok.json()["layout"]) == 2 and c.get("/api/house").json()["layout"][0] == {"item": "sofa", "x": 2, "z": 4, "r": 0}
    for bad in ([{"item": "sofa", "x": 11, "z": 4, "r": 0}], [{"item": "fern", "x": 2, "z": 4}, {"item": "fern", "x": 3, "z": 4}], [{"item": "piano", "x": 0, "z": 0}], [{"item": "fern", "x": 8, "z": 1}, {"item": "fern", "x": 8, "z": 1}]):
        r = c.post("/api/house/layout", json={"layout": bad})
        assert r.status_code == 400, bad
    assert len(c.get("/api/house").json()["layout"]) == 2                      # (the old room stays)
    assert c.post("/api/house/layout", json={"layout": "sofa"}).status_code == 422 and c.post("/api/house/layout", json={}).status_code == 422
    assert c.post("/api/house/layout", json={"layout": [{"item": "fern", "x": 0, "z": 0}] * 81}).status_code == 422      # (more than a house can hold is refused before it is read)
    assert c.post("/api/house/layout", json={"layout": []}).json()["layout"] == []


def test_floors_and_walls_are_bought_through_the_api_too():
    c = visitor()
    carpet = house.FLOORS["carpet"][1]
    earn(c, carpet + 20)
    d = c.post("/api/house/style", json={"part": "floor", "style": "carpet"}).json()
    assert d["floor"] == "carpet" and d["balance"] == 20 and {s["id"]: s["owned"] for s in d["styles"]["floor"]}["carpet"] is True
    assert c.post("/api/house/style", json={"part": "wall", "style": "charcoal"}).status_code == 400
    assert c.post("/api/house/style", json={"part": "roof", "style": "x"}).status_code == 400


def test_the_shop_and_its_errors_follow_the_language():
    c = visitor("zh")
    d = c.get("/api/house").json()
    assert {i["id"]: i["name"] for i in d["items"]}["sofa"] == "沙发" and d["categories"][1]["name"] == "家具"
    assert "XP 还不够" in c.post("/api/house/buy", json={"item": "fern"}).json()["detail"]
    page = c.get("/house").text
    assert "你的小屋" in page and "可用 XP" in page and "<span>My character</span>" not in page and "我的角色</span>" in page
    assert "Watak saya" in visitor("ms").get("/house").text


def test_your_character_is_saved_and_friends_see_it():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    sign_up(b, "Mei")
    befriend(a, b)
    d = a.post("/api/house/look", json={"look": "p.5.8.2.3.6.1"}).json()
    assert d["look"] == "p.5.8.2.3.6.1" and d["has_character"] is True and accounts.get(pid(a))["avatar"] == "p.5.8.2.3.6.1"
    assert a.post("/api/house/look", json={"look": "fox"}).status_code == 400 and a.post("/api/house/look", json={"look": "p.9.9.9.9.9.9"}).status_code == 400
    assert 'data-av="p.5.8.2.3.6.1"' in b.get("/friends").text


def test_a_visitor_without_a_profile_can_still_make_a_character():
    c = visitor()
    assert c.post("/api/house/look", json={"look": "p.1.1.1.1.1.1"}).json()["has_character"] is True and c.get("/api/house").json()["look"] == "p.1.1.1.1.1.1"


# ---------------------------------------------------------------- a friend's house
def test_a_friend_can_look_around_but_never_sees_points_or_the_cupboard():
    a, b = visitor(), visitor()
    me, friend = sign_up(a, "Aiman"), sign_up(b, "Mei")
    earn(b, 1500)
    b.post("/api/house/buy", json={"item": "fern"})
    b.post("/api/house/buy", json={"item": "sofa"})
    b.post("/api/house/layout", json={"layout": [{"item": "fern", "x": 3, "z": 3, "r": 0}]})
    b.post("/api/house/look", json={"look": "p.4.4.4.4.4.4"})
    assert a.get(f"/api/house/visit/{friend['pub']}").status_code == 404 and a.get(f"/house/visit/{friend['pub']}").status_code == 404   # not friends yet
    befriend(a, b)
    d = a.get(f"/api/house/visit/{friend['pub']}").json()
    assert d["visit"] is True and d["nickname"] == "Mei" and d["look"] == "p.4.4.4.4.4.4" and d["layout"] == [{"item": "fern", "x": 3, "z": 3, "r": 0}] and [i["id"] for i in d["items"]] == ["fern"]
    text = json.dumps(d)
    assert "balance" not in d and "sofa" not in text and "owned" not in text and not HEX32.search(text) and "price" not in text
    page = a.get(f"/house/visit/{friend['pub']}")
    assert page.status_code == 200 and f'data-visit="{friend["pub"]}"' in page.text and "Mei" in page.text and 'id="shop"' not in page.text and 'id="char-sheet"' not in page.text and not HEX32.search(page.text)
    assert b.get(f"/api/house/visit/{me['pub']}").json()["nickname"] == "Aiman"                      # (it goes both ways)
    own = a.get(f"/api/house/visit/{me['pub']}").json()                                              # you may visit yourself, as others see you
    assert own["visit"] is True and "balance" not in own
    assert a.get("/api/house/visit/not-a-pub").status_code == 404 and a.get("/api/house/visit/x" * 3).status_code == 404


def test_a_stranger_cannot_look_and_ending_a_friendship_closes_the_door():
    a, b, c = visitor(), visitor(), visitor()
    sign_up(a, "Aiman")
    friend = sign_up(b, "Mei")
    sign_up(c, "Lin")
    befriend(a, b)
    assert a.get(f"/api/house/visit/{friend['pub']}").status_code == 200 and c.get(f"/api/house/visit/{friend['pub']}").status_code == 404
    accounts.remove_friend(pid(a), friend["pub"])
    assert a.get(f"/api/house/visit/{friend['pub']}").status_code == 404


def test_the_house_works_for_a_single_person_on_their_own_computer(monkeypatch):
    monkeypatch.delenv("BAITPROOF_MULTIUSER", raising=False)
    c = TestClient(app)
    assert c.get("/house").status_code == 200 and c.get("/api/house").json()["balance"] == 0
    assert c.get("/api/house/visit/abc").status_code == 404


def test_the_pages_that_lead_to_the_house_say_so():
    a, b = visitor(), visitor()
    sign_up(a, "Aiman")
    friend = sign_up(b, "Mei")
    befriend(a, b)
    assert 'href="/house"' in a.get("/train").text and 'href="/house"' in a.get("/me").text
    assert f'href="/house/visit/{friend["pub"]}"' in a.get("/friends").text
