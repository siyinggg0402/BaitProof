"""Family alerts (consent on both sides, never the message), the safe word, and the official help lines. No network, no model."""
import asyncio
from types import SimpleNamespace

import pytest

from bot import handlers, telegram_bot
from core.domain import helplines
from core.domain.schemas import CheckResult, TacticHit, Verdict
from core.storage import family

PARENT, HELPER, OTHER = 5001, 5002, 5003
SCAM_TEXT = "Hi Mum, I lost my phone. Please buy four gift cards and send me the numbers, my account is 12345678."


@pytest.fixture(autouse=True)
def fresh():
    family._sent.clear()
    handlers.take_alerts()
    handlers.ATTEMPTS.clear()


def result(verdict=Verdict.SCAM, tactics=("irreversible-payment", "urgency-pressure"), **kw):
    base = dict(verdict=verdict, headline="x", confidence="high", tell="The giveaway quotes " + SCAM_TEXT[:40], action="a", check_id="c1",
                tactics=[TacticHit(id=t, quote="q", why="w") for t in tactics])
    return CheckResult(**{**base, **kw})


def set_up_helper(monkeypatch, name="Mum"):
    code = handlers.on_family(PARENT, name).split("/guard ")[1].split()[0]
    return code, handlers.on_guard(HELPER, code, None, "Alex")


def test_the_protected_person_gets_a_code_and_the_helper_joins_by_consent(monkeypatch):
    code, joined = set_up_helper(monkeypatch)
    assert len(code) == 6 and "family helper for Mum" in joined and "never pass on what their messages say" in joined
    (chat, note), = handlers.take_alerts()  # the protected person is told, at once, who can now be told
    assert chat == PARENT and "Alex is now a family helper" in note and "never your messages" in note and "/family off" in note
    assert "helper" in handlers.on_family(PARENT, "Mum")  # asking again shows how many


def test_a_code_works_once_and_cannot_be_guessed_or_used_by_the_person_themselves(monkeypatch):
    code = handlers.on_family(PARENT, "Mum").split("/guard ")[1].split()[0]
    assert "didn't work" in handlers.on_guard(PARENT, code)  # you cannot be your own helper
    assert "family helper for" in handlers.on_guard(HELPER, code)
    assert "didn't work" in handlers.on_guard(OTHER, code)  # spent
    assert "didn't work" in handlers.on_guard(OTHER, "ZZZZZZ") and "didn't work" in handlers.on_guard(OTHER, "abc")
    for _ in range(6):
        out = handlers.on_guard(OTHER, "ZZZZZZ")
    assert "Too many tries" in out


def test_a_code_expires(monkeypatch):
    code = handlers.on_family(PARENT, "Mum").split("/guard ")[1].split()[0]
    monkeypatch.setattr(family.time, "time", lambda: 10 ** 10)
    assert "didn't work" in handlers.on_guard(HELPER, code)


def test_a_scam_sends_the_helper_the_tricks_and_never_the_message(monkeypatch):
    set_up_helper(monkeypatch)
    handlers.take_alerts()
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result())
    handlers.on_text(PARENT, SCAM_TEXT)
    (chat, note), = handlers.take_alerts()
    assert chat == HELPER and "Mum just checked a message that looks like a scam" in note and "/safeword" in note
    assert "Tricks:" in note
    for secret in ("gift cards", "12345678", "lost my phone", "The giveaway quotes"):  # none of the message, and none of the giveaway, which can quote it
        assert secret not in note


def test_only_scams_and_someone_who_may_have_been_fooled_raise_an_alert(monkeypatch):
    set_up_helper(monkeypatch)
    handlers.take_alerts()
    for v in (Verdict.SAFE, Verdict.UNSURE):
        monkeypatch.setattr(handlers, "check_message", lambda *a, v=v, **k: result(v))
        handlers.on_text(PARENT, "hello there")
        assert handlers.take_alerts() == []
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result(Verdict.VICTIM, tactics=()))
    handlers.on_text(PARENT, "I already sent the money")
    (_, note), = handlers.take_alerts()
    assert "may have already paid" in note and "call their bank" in note


def test_the_helpers_own_checks_and_strangers_raise_no_alert(monkeypatch):
    set_up_helper(monkeypatch)
    handlers.take_alerts()
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result())
    handlers.on_text(HELPER, SCAM_TEXT)
    handlers.on_text(OTHER, SCAM_TEXT)
    assert handlers.take_alerts() == []


def test_a_flurry_of_scams_does_not_become_a_flood(monkeypatch):
    set_up_helper(monkeypatch)
    handlers.take_alerts()
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result())
    for _ in range(10):
        handlers.on_text(PARENT, SCAM_TEXT)
    assert len(handlers.take_alerts()) == family.MAX_ALERTS_PER_HOUR


def test_either_side_can_stop_it(monkeypatch):
    set_up_helper(monkeypatch)
    handlers.take_alerts()
    assert "won't get family alerts any more" in handlers.on_guard(HELPER, "off") and handlers.on_guard(HELPER, "off").startswith("You weren't")
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result())
    handlers.on_text(PARENT, SCAM_TEXT)
    assert handlers.take_alerts() == []
    set_up_helper(monkeypatch)
    handlers.take_alerts()
    assert "Nobody gets alerts" in handlers.on_family(PARENT, "off")
    (chat, note), = handlers.take_alerts()
    assert chat == HELPER and "no longer get family alerts about Mum" in note
    assert handlers.on_family(PARENT, "off").startswith("Nobody was getting")


def test_there_is_a_limit_to_helpers_and_the_name_is_only_a_plain_name(monkeypatch):
    for i in range(family.MAX_HELPERS):
        handlers.ATTEMPTS.clear()
        code = handlers.on_family(PARENT, "Mum <b>x</b> {who}").split("/guard ")[1].split()[0]
        assert "family helper for" in handlers.on_guard(6000 + i, code)
    handlers.ATTEMPTS.clear()
    code = handlers.on_family(PARENT, "Mum").split("/guard ")[1].split()[0]
    assert "most helpers" in handlers.on_guard(7000, code)
    assert family.clean_name("Mum <b>x</b> {who}") == "Mum b x b who" and len(family.clean_name("A" * 99)) == 24


def test_the_note_comes_in_the_helpers_language(monkeypatch):
    code = handlers.on_family(PARENT, "妈妈").split("/guard ")[1].split()[0]
    handlers.on_guard(HELPER, code, "zh")
    handlers.take_alerts()
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result())
    handlers.on_text(PARENT, SCAM_TEXT)
    (_, note), = handlers.take_alerts()
    assert "妈妈 刚检查了一条看起来像骗局的消息" in note and "套路：" in note and "暗号" in note


def test_the_connector_sends_the_note_after_answering_and_a_failed_note_breaks_nothing(monkeypatch):
    sent = []

    class Bot:
        async def send_message(self, chat_id, text):
            sent.append((chat_id, text))
            if chat_id == 9:
                raise RuntimeError("blocked")

    class Msg:
        def get_bot(self):
            return Bot()
    handlers.ALERTS.put((7, "hello"))
    handlers.ALERTS.put((9, "blocked one"))
    handlers.ALERTS.put((8, "after the failure"))
    asyncio.run(telegram_bot.send_alerts(SimpleNamespace(message=Msg())))
    assert [c for c, _ in sent] == [7, 9, 8] and handlers.take_alerts() == []
    asyncio.run(telegram_bot.send_alerts(SimpleNamespace(message=SimpleNamespace())))  # nothing to send, nothing to break


def test_the_safe_word_text_never_asks_for_the_word():
    en, zh = handlers.on_safeword(1), handlers.on_safeword(2, "zh")
    assert "No word, no money" in en and "Never type your safe word" in en and "暗号" in zh and "千万不要" in zh


# ---------------------------------------------------------------- the official help lines
def test_the_official_lines_are_the_checked_ones():
    t = helplines.text("en")
    for must in ("1799", "go.gov.sg/scamreport", "1800-722-6688", "997", "semakmule.rmp.gov.my", "Singapore", "Malaysia", "October 2026"):
        assert must in t, must
    assert "your bank straight away" in t and "never ask you to move money" in t


def test_the_help_text_is_translated_and_the_numbers_survive():
    zh = helplines.text("zh")
    assert "新加坡" in zh and "马来西亚" in zh and "1799" in zh and "997" in zh and "semakmule.rmp.gov.my" in zh and "2026年10月" in zh
    hant = helplines.text("zh-Hant")  # Traditional is derived from the Simplified text
    assert "已經付了錢" in hant and "新加坡" in hant and "1799" in hant
    assert "1799" in helplines.short("en") and "997" in helplines.short("zh")


def test_a_scam_reply_ends_with_the_short_help_line_and_a_victim_gets_the_whole_list(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result())
    assert "Singapore: call your bank, then 1799. Malaysia: call 997 now. More: /report" in handlers.on_text(8001, "x")
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result(Verdict.VICTIM, tactics=()))
    out = handlers.on_text(8002, "x")
    assert "1800-722-6688" in out and "semakmule.rmp.gov.my" in out
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: result(Verdict.SAFE, tactics=()))
    assert "1799" not in handlers.on_text(8003, "x")  # nothing to report: no noise
    assert "1800-722-6688" in handlers.on_report(8004) and "997" in handlers.on_report(8004, "zh")
