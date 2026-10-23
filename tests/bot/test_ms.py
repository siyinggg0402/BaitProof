"""The Telegram bot in Bahasa Melayu: choosing it, the welcome, a check, the help lines, family flows, quizzes and history."""
import re

from bot import handlers
from core.lang.text import detect

CJK = re.compile(r"[一-鿿]")
PRIZE = "Tahniah! Anda telah memenangi hadiah RM50,000. Sila klik pautan ini untuk menuntut dalam 24 jam http://hadiah-maybank.top/tuntut"
ENGLISH_SCAM = "Buy 4 gift cards and send me the numbers please."


def test_telegrams_language_code_and_the_lang_command_choose_malay(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert handlers.on_start(1, lang_hint="ms-MY").startswith("Hai! Saya Finn")
    assert "Hai! Saya Finn" in handlers.on_start(1, lang_hint="ms")
    for arg in ("ms", "bm", "malay", "MS"):
        assert handlers.on_lang(2, arg) == "Bahasa ditetapkan kepada Bahasa Melayu."
    assert "/lang ms" in handlers.on_lang(3, "klingon")


def test_the_welcome_in_malay_names_every_command():
    text = handlers.on_start(4, lang_hint="ms")
    for cmd in ("/quiz", "/challenge", "/link", "/history", "/score", "/report", "/family", "/safeword", "/lang"):
        assert cmd in text, cmd
    assert text.count("\n") == handlers.WELCOME.count("\n")  # the same shape as the English one
    assert "Bahasa Melayu" in text and "简体中文" in text  # the language menu names each language in itself


def test_a_chosen_malay_explains_even_an_english_message_in_malay(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_lang(11, "ms")
    out = handlers.on_text(11, ENGLISH_SCAM)
    first = out.splitlines()[0]
    assert first.startswith("🚨") and "PENIPUAN" in first and "Tanda pembongkar:" in out and "Apa yang perlu dibuat:" in out and "Ditambah pada latihan anda" in out
    assert "The giveaway" not in out and not CJK.search(out)


def test_a_malay_message_gets_a_malay_answer_without_choosing(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    out = handlers.on_text(12, PRIZE)
    assert out.startswith("🚨") and "PENIPUAN" in out.splitlines()[0] and "Tanda pembongkar:" in out
    assert "tel:" not in out and "1799" in out and "997" in out and "/report" in out  # a short pointer to the help lines, not the whole list
    assert "Hidup" not in out


def test_report_gives_the_official_lines_in_malay():
    text = handlers.on_report(13, lang_hint="ms")
    for want in ("1799", "go.gov.sg/scamreport", "1800-722-6688", "997", "semakmule.rmp.gov.my", "Singapura", "Oktober 2026", "Pegawai sebenar"):
        assert want in text, want
    assert not CJK.search(text) and "official line" not in text.lower()


def test_the_family_flow_is_in_malay(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_lang(14, "ms")
    handlers.on_lang(15, "ms")
    offer = handlers.on_family(14)
    code = re.search(r"/guard ([A-Z0-9]{6})", offer).group(1)
    assert "Amaran keluarga" in offer and "/family off" in offer
    joined = handlers.on_guard(15, code, who="Mei")
    assert "pembantu keluarga" in joined and "bukan mesej anda" not in joined
    (owner, note), *_ = handlers.take_alerts()
    assert owner == 14 and "Mei" in note and "pembantu keluarga anda" in note and "bukan mesej anda" in note
    assert handlers.on_family(14, "off").startswith("Selesai")
    assert "kata kunci" in handlers.on_safeword(14).lower()


def test_a_family_alert_reads_in_the_helpers_language(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.ATTEMPTS.clear()
    handlers.on_lang(16, "en")
    handlers.on_lang(17, "ms")
    code = re.search(r"/guard ([A-Z0-9]{6})", handlers.on_family(16)).group(1)
    handlers.on_guard(17, code, who="Aiman")
    handlers.take_alerts()
    handlers.on_text(16, ENGLISH_SCAM)
    (chat, text), = handlers.take_alerts()
    assert chat == 17
    assert "👪" in text and "Helah:" in text and "Gift cards" not in text and "send me the numbers" not in text  # the trick names, never the message
    assert not CJK.search(text)


def test_quiz_history_and_score_are_in_malay(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    handlers.on_lang(18, "ms")
    first = handlers.on_quiz(18)[0]
    assert "Kuiz pantas" in first.text and "1 daripada 5" in first.text and detect(first.text.split("\n\n")[1]) == "ms"
    labels = [b.label for row in first.buttons for b in (row if isinstance(row, (list, tuple)) else [row])]
    assert labels == ["🚨 Penipuan", "✅ Nampak okey", "🤔 Semak dahulu"]
    assert "Belum ada semakan" in handlers.on_history(19, lang_hint="ms")
    handlers.on_lang(20, "ms")
    handlers.on_text(20, ENGLISH_SCAM)
    assert "Semakan terkini anda" in handlers.on_history(20) and "Skor Baitproof anda" in handlers.on_score(20)
