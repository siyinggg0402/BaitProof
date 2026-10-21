import re

from bot import handlers
from bot.handlers import on_callback, on_challenge
from core.lang.text import CJK
from core.pipelines import challenge
from core.storage import db, links

URL = "https://baitproof.example"


def count_challenges() -> int:
    with db.connect(shared=True) as c:
        return c.execute("SELECT COUNT(*) AS n FROM challenges").fetchone()["n"]


def test_challenge_gives_a_message_to_forward_with_a_link_that_opens_a_real_challenge(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL + "/")  # a trailing slash is fine
    intro, forward = on_challenge(300)
    assert "Forward the next message" in intro.text and not intro.buttons and not intro.preview
    assert forward.text.startswith("Can you spot the scam?") and "2 minutes" in forward.text and "no account" in forward.text
    assert forward.preview and not forward.buttons and len(forward.text) < 400  # short, and the site's card may unfurl
    cid = re.search(rf"{re.escape(URL)}/challenge/([0-9a-f]{{8}})(?!\w)", forward.text).group(1)
    assert forward.text.count("http") == 1 and f"{URL}//" not in forward.text
    items = challenge.get(cid)  # what the web page loads
    assert items and len(items) == 6 and {i["is_scam"] for i in items} == {True, False}
    assert count_challenges() == 1


def test_each_call_makes_a_new_challenge(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    first, second = on_challenge(301)[1].text, on_challenge(301)[1].text
    assert first != second and count_challenges() == 2


def test_without_baitproof_url_it_says_the_operator_must_set_it_and_makes_nothing():
    reply = on_challenge(302)
    assert len(reply) == 1 and "BAITPROOF_URL" in reply[0].text and "http" not in reply[0].text and reply[0].buttons == []
    assert count_challenges() == 0
    handlers.on_lang(303, "zh")
    zh = on_challenge(303)[0].text
    assert "BAITPROOF_URL" in zh and CJK.search(zh) and "Please ask" not in zh
    handlers.on_lang(304, "zh-Hant")
    assert "運營" in on_challenge(304)[0].text
    assert count_challenges() == 0 and handlers.RATE == {}  # a missing setting does not use up the chat's allowance


def test_challenge_is_in_the_chats_language(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")  # each chat has its own settings
    handlers.on_lang(305, "zh")
    intro, forward = on_challenge(305)
    assert "转发" in intro.text and forward.text.startswith("你能识破骗局吗？") and f"{URL}/challenge/" in forward.text and "2分钟" in forward.text
    cid = re.search(r"/challenge/([0-9a-f]{8})", forward.text).group(1)
    assert all(CJK.search(i["text"]) for i in challenge.get(cid))  # the messages are Chinese too
    handlers.on_lang(306, "zh-Hant")
    assert on_challenge(306)[1].text.startswith("你能識破騙局嗎？")
    assert on_challenge(307, "zh-hans")[1].text.startswith("你能识破骗局吗？")  # Telegram's own language, when the chat has not chosen


def test_challenges_are_rate_limited_per_chat_and_nothing_is_created_when_refused(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    for _ in range(5):
        assert len(on_challenge(308)) == 2
    refused = on_challenge(308)
    assert len(refused) == 1 and refused[0].text == "You've made a few challenges already. Please wait a bit before making another one." and "http" not in refused[0].text
    assert count_challenges() == 5
    assert len(on_challenge(309)) == 2  # another chat is fine
    handlers.on_lang(308, "zh")
    assert on_challenge(308)[0].text.startswith("你已经创建了好几个挑战了")


def test_the_challenge_button_works_like_the_command(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", URL)
    res = on_callback(310, handlers.CHALLENGE)
    assert res.toast == "" and len(res.replies) == 2 and f"{URL}/challenge/" in res.replies[1].text and not any(r.edit for r in res.replies)
    assert count_challenges() == 1


def test_a_linked_chats_own_scams_can_appear_in_its_challenge(monkeypatch):
    """The challenge is built from the chat's profile like the website's button: a scam it forwarded earlier may be one of the six."""
    monkeypatch.setenv("BAITPROOF_URL", URL)
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_check(311, "Buy 4 gift cards and send me the numbers please.")
    cid = re.search(r"/challenge/([0-9a-f]{8})", on_challenge(311)[1].text).group(1)
    assert any("gift cards" in i["text"] for i in challenge.get(cid))
    assert links.current_profile() != "local"
