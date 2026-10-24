"""Tamil (தமிழ்) for the families in Singapore who read it: the language is recognised, every string the app shows has a Tamil version with the same blanks, the tricks are
explained in Tamil, and answers come out in Tamil. Tamil has its own rule pack (core/lang/ta.py), so a Tamil message is checked by phrase rules as well as the model and the
language-free checks (links, numbers); without the model the rules still catch the common scams, and they clear only what is plainly an ordinary message."""
import re

import pytest

from core.domain.schemas import Verdict as V
from core.domain.tactics import TACTICS
from core.lang import i18n
from core.lang.i18n import TA, TACTICS_TA, ZH, from_accept_language, norm, tactic_text, tr
from core.lang.text import RULES_LANGS, detect
from core.pipelines.check import check_message
from core.pipelines.check.pipeline import reply_language

TAMIL = re.compile(r"[஀-௿]")
CJK = re.compile(r"[一-鿿]")
BLANK = re.compile(r"\{[^{}]*\}")
MSG = "உங்கள் DBS கணக்கு முடக்கப்படும். உடனே இங்கே சரிபார்க்கவும்: http://dbs-verify.top/login"
PLAIN = "நாளை மாலை 5 மணிக்கு கோவிலில் சந்திப்போம். சாப்பாடு கொண்டு வருகிறேன்."


@pytest.mark.parametrize("raw", ["ta", "ta-SG", "ta_IN", "TA", "tamil", "Tamil", "tam"])
def test_tamil_codes_are_recognised(raw):
    assert norm(raw) == "ta"


def test_the_browser_can_ask_for_tamil_and_the_language_has_its_own_name():
    assert from_accept_language("ta-SG,ta;q=0.9,en;q=0.5") == "ta" and from_accept_language("en-SG,en;q=0.9,ta;q=0.5") == "en"
    assert i18n.LANGS[-1] == "ta" and i18n.NAMES["ta"] == "தமிழ்" and "Tamil" in i18n.PROMPT_NAMES["ta"]
    assert norm("xx") == "en" and norm("tab") == "en"          # (nothing else is taken for Tamil)


def test_every_string_has_a_tamil_version_and_none_is_an_orphan():
    assert not [k for k in ZH if k not in TA], "add a Tamil version in core/lang/i18n_ta.py"
    assert not [k for k in TA if k not in ZH], "a Tamil string whose English key matches nothing (a typo?)"


def test_tamil_keeps_the_blanks_and_line_breaks_of_the_english():
    bad = [k for k, v in TA.items() if sorted(BLANK.findall(k)) != sorted(BLANK.findall(v)) or k.count("\n") != v.count("\n")]
    assert not bad, bad[:5]


def test_tamil_is_written_in_tamil_not_left_in_english_or_chinese_or_malay():
    assert not [k for k, v in TA.items() if CJK.search(v)]
    words = lambda s: re.findall(r"[A-Za-z]{3,}", BLANK.sub(" ", s))
    english = [k for k, v in TA.items() if len(words(k)) >= 3 and not TAMIL.search(v)]
    assert not english, english[:5]
    same = {k for k, v in TA.items() if v == k}
    assert len(same) < 60, sorted(same)[:20]                    # (brands, numbers and symbols are written the same in every language; a long list means untranslated text)
    assert TA["Scam Road"] == "மோசடிச் சாலை" and TA["Link Hunt"] == "இணைப்பு வேட்டை" and TA["Your house"] == "உங்கள் வீடு"      # (the glossary every translator followed)


def test_the_emoji_of_the_chat_texts_are_kept():
    emoji = re.compile("[\U0001F000-\U0001FAFF☀-➿]")
    assert not [k for k, v in TA.items() if sorted(emoji.findall(k)) != sorted(emoji.findall(v))]


def test_every_tactic_is_explained_in_tamil():
    assert set(TACTICS_TA) == set(TACTICS)
    for tid, parts in TACTICS.items():
        for field in ("label", "blurb", "tell", "action"):
            got = tactic_text(tid, field, "ta", TACTICS)
            assert got and got != parts[field] and TAMIL.search(got) and not CJK.search(got), (tid, field)


def test_tamil_text_is_filled_in_and_unknown_text_falls_back_to_english():
    assert tr("{n} separate red flags", "ta", n=3) == TA["{n} separate red flags"].format(n=3) and "3" in tr("{n} separate red flags", "ta", n=3)
    assert tr("a sentence nobody translated", "ta") == "a sentence nobody translated"
    assert tr("Read aloud", "ta") not in (tr("Read aloud", "ms"), tr("Read aloud", "zh"), "Read aloud")


def test_tamil_text_is_recognised_and_the_reply_follows_the_reader():
    assert detect(MSG) == "ta" and detect(PLAIN) == "ta" and "ta" in RULES_LANGS
    assert reply_language(MSG, None) == "ta" and reply_language(MSG, "en") == "en" and reply_language("Your parcel is on hold", "ta") == "ta"


def test_a_tamil_message_gets_a_tamil_answer_and_nothing_unrecognised_is_called_safe():
    r = check_message(MSG, store=False, log=False)
    assert r.lang == "ta" and r.message_lang == "ta" and r.verdict in (V.SCAM, V.LIKELY_SCAM, V.UNSURE)          # (the link is a lookalike of dbs.com: the link checks speak without a model)
    assert TAMIL.search(r.headline) and not CJK.search(r.headline + r.tell + r.action)
    plain = check_message(PLAIN, store=False, log=False)
    assert plain.lang == "ta" and plain.verdict is not V.SAFE and TAMIL.search(plain.headline)               # (no model here and nothing the rules recognise as an ordinary message type: "safe" is not earned)


def test_an_english_message_is_explained_in_tamil_when_asked():
    r = check_message("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz/track", store=False, log=False, lang="ta")
    assert r.lang == "ta" and r.message_lang == "en" and r.verdict in (V.SCAM, V.LIKELY_SCAM) and TAMIL.search(r.headline)
    assert TAMIL.search(r.action) and r.action in {v["action"] for v in TACTICS_TA.values()}                  # (the next step is our own written line for the trick, never the model's own Tamil)
    assert any("within 24 hours" in e.claim for e in r.evidence)                                              # (the sender's words stay as they were written)


def test_english_answers_are_untouched_by_tamil():
    r = check_message("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz/track", store=False, log=False)
    assert r.lang == "en" and "SCAM" in r.headline.upper() and not TAMIL.search(r.headline + r.tell + r.action)


# ---------------------------------------------------------------- the practice messages
def test_the_tamil_practice_bank_is_well_formed_and_written_in_tamil():
    from core.domain.tactics import valid
    from core.storage import library

    seeds = library.seed_examples("ta")
    assert len(seeds) >= 55 and len({e["id"] for e in seeds}) == len(seeds)
    assert sum(e["is_scam"] for e in seeds) >= 36 and sum(not e["is_scam"] for e in seeds) >= 16 and sum(e.get("truth") == "unsure" for e in seeds) >= 3
    used = set()
    for e in seeds:
        assert detect(e["text"]) == "ta" and e["lang"] == "ta" and e["tell"] and e["action"] and TAMIL.search(e["tell"]) and TAMIL.search(e["action"]) and not CJK.search(e["text"] + e["tell"] + e["action"]), e["id"]
        if e["is_scam"]:
            used |= set(e["tactics"])
            assert e["tactics"] and all(valid(t) for t in e["tactics"]) and e["tell_phrase"] and e["tell_phrase"] in e["text"], e["id"]
        else:
            assert not e["tactics"] and not e["tell_phrase"], e["id"]
    assert used == set(TACTICS)                                  # (every trick has a Tamil example)
    assert len({e["text"] for e in seeds}) == len(seeds)


def test_the_tamil_bank_is_not_the_other_banks_translated_word_for_word_and_does_not_leak_into_the_evaluation_sets():
    from core.storage import library

    texts = {e["text"] for e in library.seed_examples("ta")}
    assert not texts & {e["text"] for e in library.seed_examples("ms")} and not texts & {e["text"] for e in library.seed_examples("en")}
    assert all("http://" not in t or re.search(r"https?://[\w.-]+\.(?:top|xyz|click|help|shop|vip|cc|live|online|site|info|link|[a-z]{2,})", t) for t in texts)


def test_the_games_deal_tamil_messages_and_no_scam_or_check_first_message_is_ever_called_safe():
    from core.game import pool as gp
    from core.storage import library

    items = [i for i in gp.build_pool("ta") if i.source == "seed"]
    assert len(items) >= 55 and {i.truth for i in items} == {"scam", "safe", "unsure"} and all(TAMIL.search(i.tell) for i in items)
    for e in library.seed_examples("ta"):
        verdict = check_message(e["text"], store=False, log=False).verdict
        if e["is_scam"] or e.get("truth") == "unsure":
            assert verdict is not V.SAFE, e["id"]                # (a plainly ordinary message may be cleared by the rules alone, a scam or a "check first" one never)


# ---------------------------------------------------------------- the Tamil rule pack
from tests.data.ta import dev as TA_DEV  # noqa: E402


def _rules_only(text):
    from scripts import common

    with common.offline(net=True):
        v = check_message(text, store=False, log=False).verdict
    return "scam" if v in (V.SCAM, V.LIKELY_SCAM) else v.value


def test_the_rules_alone_catch_the_common_tamil_scams_and_never_call_an_ordinary_message_a_scam():
    caught = [tag for tag, text in TA_DEV.SCAMS if _rules_only(text) == "scam"]
    alarms = [tag for tag, text in TA_DEV.LEGIT if _rules_only(text) == "scam"]
    assert len(caught) >= 23 and not alarms, (sorted({t for t, _ in TA_DEV.SCAMS} - set(caught)), alarms)       # (measured 25 of 25 and none; written against this set, so the holdout is tests/data/ta/holdout.py)


def test_the_seed_bank_scams_are_caught_by_the_rules_alone_too():
    from core.storage import library

    seeds = [e for e in library.seed_examples("ta") if e.get("truth") != "unsure"]
    caught = sum(_rules_only(e["text"]) == "scam" for e in seeds if e["is_scam"])
    alarms = [e["id"] for e in seeds if not e["is_scam"] and _rules_only(e["text"]) == "scam"]
    assert caught >= 38 and not alarms, (caught, alarms)                              # (measured 41 of 42 and none)


def test_a_dont_share_warning_is_not_a_request_and_a_request_is():
    from core.pipelines.check import ingest, intent

    def asks(text):
        return intent._heuristic(ingest.ingest(text)).asks

    assert "share_code" not in asks("உங்கள் OTP-ஐ யாரிடமும் பகிராதீர்கள். வங்கி ஊழியர்கள் ஒருபோதும் உங்கள் OTP-ஐ கேட்க மாட்டார்கள்.")      # "don't share" in the negative-imperative form
    assert "share_code" not in asks("உங்கள் OTP 482913. இதை யாரிடமும் பகிர வேண்டாம்.")                                                  # and in the "... வேண்டாம்" form
    assert "share_code" not in asks("உங்கள் வங்கி ஒருபோதும் உங்கள் PIN, OTP அல்லது கடவுச்சொல்லைக் கேட்காது.")                           # the word "கடவுச்சொல்லை" (password) holds "சொல்ல" ("tell") but is not a request
    assert "share_code" in asks("உங்களுக்கு வந்த OTP எண்ணை இப்போதே எங்களிடம் கூறுங்கள்.")
    assert "share_credentials" in asks("உங்கள் கார்டு எண்ணையும் CVV-யையும் உள்ளிடவும்.")
    assert "pay" not in asks("பணம் அனுப்பும் முன் ScamShield 1799 ஐ அழையுங்கள்.")                                                      # "before sending money" is advice
    assert "pay" in asks("இன்றே $300 கட்டணம் செலுத்துங்கள்.")


def test_an_organisation_next_to_the_word_verification_is_not_an_impersonation_and_a_blocked_account_is():
    from core.pipelines.check import knowledge

    def hits(text):
        from core.lang import text as L

        L.CURRENT.set("ta")
        return {tid for tid, pats in knowledge.RULES.items() for p in pats if p.search(text)}

    assert "impersonation-official" not in hits("உங்கள் Grab சரிபார்ப்புக் குறியீடு: 5821. இதை யாரிடமும் பகிர வேண்டாம்.")
    assert "impersonation-official" in hits("Maybank: உங்கள் கணக்கு முடக்கப்பட்டது, இணைப்பைத் தொடுங்கள்.") or "impersonation-official" in hits("DBS: உங்கள் கணக்கு முடக்கப்படும்.")
    assert "authority-spoofing" not in hits("ICA: உங்கள் அனுமதி அட்டை விண்ணப்பம் பெறப்பட்டது.")                 # (a bare agency name is not a threat)
