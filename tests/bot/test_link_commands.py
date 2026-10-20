
from bot import handlers
from core.storage import links


def test_start_with_a_code_links_and_start_alone_welcomes():
    assert handlers.on_start(1, "").startswith("Hi! I'm Baitproof") and "/link CODE" in handlers.WELCOME
    code = links.new_code("local")
    assert handlers.on_start(1, code).startswith("✅ Linked") and links.profile_for_chat(1) == "local"


def test_link_command_messages_are_helpful():
    assert "6-character code" in handlers.on_link(2, "")
    assert "didn't work" in handlers.on_link(2, "ABCDEF")


def test_guessing_codes_is_limited():
    handlers.ATTEMPTS.clear()
    replies = [handlers.on_link(3, "ABCDEF") for _ in range(7)]
    assert "didn't work" in replies[4] and "Too many tries" in replies[5] and "Too many tries" in replies[6]
    # even a correct code is refused while locked out, so brute force gains nothing
    assert "Too many tries" in handlers.on_link(3, links.new_code("local"))


def test_unlink_and_history_messages():
    handlers.ATTEMPTS.clear()
    handlers.on_link(4, links.new_code("local"))
    assert "Disconnected" in handlers.on_unlink(4) and "wasn't linked" in handlers.on_unlink(4)
    assert "No checks yet" in handlers.on_history(4)


def test_linked_replies_point_to_the_records_page_when_a_url_is_set(monkeypatch):
    monkeypatch.setenv("BAITPROOF_URL", "https://baitproof.example")
    handlers.ATTEMPTS.clear()
    assert "https://baitproof.example/records" in handlers.on_link(5, links.new_code("local"))
    assert "🗂 Saved to your records: https://baitproof.example/records" in handlers.on_text(5, "Buy 4 gift cards and send me the codes now.")
