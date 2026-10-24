"""The Telegram bot in Tamil (தமிழ்): choosing it, the welcome, a check, the help lines, the quiz and the family flow."""
import re

from bot import handlers
from core.lang import i18n

TAMIL = re.compile(r"[஀-௿]")
CJK = re.compile(r"[一-鿿]")
SCAM = "உங்கள் DBS கணக்கு முடக்கப்படும். உடனே இங்கே சரிபார்க்கவும்: http://dbs-verify.top/login"
ENGLISH_SCAM = "Buy 4 gift cards and send me the numbers please."


def test_telegrams_language_code_and_the_lang_command_choose_tamil(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert handlers.on_start(1, lang_hint="ta-IN").startswith("வணக்கம்! நான் Finn")
    assert "வணக்கம்! நான் Finn" in handlers.on_start(1, lang_hint="ta")
    for arg in ("ta", "tamil", "TA", "Tamil"):
        assert handlers.on_lang(2, arg) == "மொழி தமிழாக மாற்றப்பட்டது."
    assert "/lang ta" in handlers.on_lang(3, "klingon")


def test_the_welcome_in_tamil_names_every_command_and_the_language():
    text = handlers.on_start(4, lang_hint="ta")
    for cmd in ("/quiz", "/challenge", "/link", "/history", "/score", "/report", "/family", "/safeword", "/lang", "/lang ta"):
        assert cmd in text, cmd
    assert text.count("\n") == handlers.WELCOME.count("\n") and "தமிழ்" in text and not CJK.search(text)
    assert "/lang ta" in handlers.WELCOME and "/lang ta" in handlers.on_start(5, lang_hint="ms") and "/lang ta" in handlers.on_start(6, lang_hint="zh")


def test_a_chosen_tamil_explains_even_an_english_message_in_tamil(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_lang(11, "ta")
    out = handlers.on_text(11, ENGLISH_SCAM)
    first = out.splitlines()[0]
    assert first.startswith("🚨") and TAMIL.search(first) and "1799" in out and not CJK.search(out) and "The giveaway" not in out


def test_a_tamil_message_gets_a_tamil_answer_without_choosing_and_is_never_safe(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    out = handlers.on_text(12, SCAM)
    assert TAMIL.search(out.splitlines()[0]) and "tel:" not in out and "1799" in out and "/report" in out
    plain = handlers.on_text(13, "நாளை மாலை 5 மணிக்கு கோவிலில் சந்திப்போம். சாப்பாடு கொண்டு வருகிறேன்.")
    assert not plain.startswith("✅") and TAMIL.search(plain)


def test_report_gives_the_official_lines_in_tamil():
    text = handlers.on_report(14, lang_hint="ta")
    for want in ("1799", "go.gov.sg/scamreport", "1800-722-6688", "997", "semakmule.rmp.gov.my", "சிங்கப்பூர்"):
        assert want in text, want
    assert TAMIL.search(text) and not CJK.search(text) and "official line" not in text.lower()


def test_the_quiz_deals_tamil_practice_messages(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_lang(15, "ta")
    reply = handlers.on_quiz(15)
    text = reply.text if hasattr(reply, "text") else str(reply)
    assert TAMIL.search(text) and not CJK.search(text)


def test_the_language_menu_names_tamil_in_tamil_in_every_language():
    assert i18n.NAMES["ta"] == "தமிழ்"
    for lang in ("en", "ms"):
        assert "தமிழ்" in handlers.on_start(20, lang_hint=lang)
    assert "泰米尔文" in handlers.on_start(20, lang_hint="zh")      # (Chinese names each language the Chinese way)
