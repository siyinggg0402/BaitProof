"""The language of the site decides what a person sees, never the language of a message they once checked: a scam checked in Spanish (or forwarded in Chinese)
must not turn up in the English game."""
import pytest

from core.game import pool
from core.lang import text
from core.pipelines.check import check_message
from core.storage import library

SPANISH = "Banco Santander: su cuenta ha sido bloqueada. Verifique ahora en http://santander-seguro.top/verificar o su cuenta será cerrada en 24 horas."
ENGLISH = "Your parcel is held at the depot. Pay the small fee today at http://parcel-fee-now.top or it will be sent back to the sender."
CHINESE = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。"
MALAY = "Pos Laju: bungkusan anda ditahan. Sila bayar yuran di http://poslaju-bayar.top sekarang atau ia akan dikembalikan."
INDONESIAN = "Paket kamu ditahan di gudang. Tolong bayar biaya kirim di http://paket-bayar.top sekarang, nanti dikembalikan ke pengirim."
TAMIL = "உங்கள் பார்சல் நிறுத்தப்பட்டுள்ளது. இன்றே http://parcel-fee-now.top இல் கட்டணம் செலுத்துங்கள், இல்லையெனில் திருப்பி அனுப்பப்படும்."
FRENCH = "Votre colis est bloqué à la douane. Payez les frais de livraison sur http://colis-frais.top avant demain, sinon il sera renvoyé à l'expéditeur."
GERMAN = "Ihr Paket wurde angehalten und ist nicht zugestellt worden. Bitte zahlen Sie die Gebühr sofort unter http://paket-gebuehr.top oder es geht zurück."


def store(*texts):
    for t in texts:
        assert library.add_user_example(t, ["urgency-pressure"], "", "A real company gives you time.", "Stop and check.")


def head(message):
    return message[:12]  # (the library keeps a redacted copy: links lose their http://, so messages are compared by how they start)


def shown(lang):
    return [head(i.text) for i in pool.build_pool(lang) if i.source == "yours"]


@pytest.mark.parametrize("site, expected", [("en", ENGLISH), ("zh", CHINESE), ("zh-Hant", CHINESE), ("ms", MALAY), ("ta", TAMIL)])
def test_each_site_shows_only_its_own_language(site, expected):
    store(SPANISH, ENGLISH, CHINESE, MALAY, TAMIL, FRENCH, GERMAN)
    assert shown(site) == [head(expected)]


def test_indonesian_counts_as_malay_and_only_there():
    store(INDONESIAN, ENGLISH)
    assert shown("ms") == [head(INDONESIAN)] and shown("en") == [head(ENGLISH)] and shown("ta") == []


def test_a_scam_in_an_unsupported_language_is_in_no_game_at_all():
    store(SPANISH, FRENCH, GERMAN)
    assert all(shown(lang) == [] for lang in ("en", "zh", "zh-Hant", "ms", "ta"))
    assert not any("Santander" in i.text for lang in ("en", "zh", "ms", "ta") for i in pool.build_pool(lang))


def test_the_explanation_is_in_the_sites_language_even_if_it_was_saved_in_another():
    assert library.add_user_example(ENGLISH, ["urgency-pressure"], "today", "正规公司会给你时间。", "先停下来。")  # an English message checked while the site was in Chinese
    [item] = [i for i in pool.build_pool("en") if i.source == "yours"]
    assert not text.CJK.search(item.tell + item.action)
    assert item.tell and item.action


def test_the_detector_never_guesses_english_for_text_it_cannot_read():
    assert text.detect_strict("") == "" and text.detect_strict("Hola") == "" and text.detect_strict("12345 :)") == ""
    assert text.detect_strict(SPANISH) == "other" and text.detect_strict(FRENCH) == "other" and text.detect_strict(GERMAN) == "other"
    assert text.detect_strict(ENGLISH) == "en" and text.detect_strict(MALAY) == "ms" and text.detect_strict(INDONESIAN) == "ms"
    assert text.detect_strict(CHINESE) == "zh" and text.detect_strict(TAMIL) == "ta"
    assert text.in_language(ENGLISH, "en") and not text.in_language(ENGLISH, "ms") and not text.in_language(SPANISH, "en") and not text.in_language("Hola", "en")
    assert text.detect("Hola") == "en"  # (the loose detector keeps its old behaviour: short means English)


def test_a_scam_checked_in_spanish_is_judged_but_never_kept_for_training():
    result = check_message(SPANISH, store=True, log=False)
    assert result.message_lang == "other" and not result.added_to_training
    assert library.user_examples() == []
    english = check_message("Your bank account is locked. Verify now at http://dbs-secure-login.top/verify or it will be closed in 24 hours.", store=True, log=False)
    assert english.added_to_training and library.user_examples()  # (English still feeds the library, as before)


def test_the_authored_bank_shows_only_english_even_though_it_holds_a_spanish_and_a_french_example():
    """The bank also teaches the model (it has one Spanish and one French scam in it); the English game used to deal them to people."""
    from core.ai import fewshot

    foreign = [b for b in fewshot.load_authored() if not text.in_language(b.text, "en")]
    assert foreign, "the bank is expected to hold non-English examples for the model"  # if this ever fails, the filter below is no longer needed
    dealt = {i.text for i in pool.build_pool("en")}
    assert not any(b.text in dealt for b in foreign)
    assert all(text.in_language(i.text, "en") for i in pool.build_pool("en") if i.source == "bank")
