"""Answers in the user's language: reply language selection, fallbacks, Simplified/Traditional output, and that English is untouched."""
import pytest

from core.domain import i18n
from core.domain.i18n import from_accept_language, norm, to_traditional, tr
from core.domain.schemas import Verdict as V
from core.domain.tactics import TACTICS
from core.pipelines.check import check_message
from core.pipelines.check.pipeline import reply_language

PARCEL = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。"


@pytest.mark.parametrize("raw,lang", [("zh", "zh"), ("zh-CN", "zh"), ("zh_Hans", "zh"), ("zh-TW", "zh-Hant"), ("zh-HK", "zh-Hant"), ("zh-Hant", "zh-Hant"),
                                      ("en-GB", "en"), ("fr", "en"), (None, "en"), ("", "en")])
def test_language_codes_are_normalised(raw, lang):
    assert norm(raw) == lang


def test_accept_language_picks_the_first_supported_language():
    assert from_accept_language("zh-TW,zh;q=0.9,en;q=0.8") == "zh-Hant"
    assert from_accept_language("fr-FR,zh-CN;q=0.8") == "zh"
    assert from_accept_language("en-US,en;q=0.9") == "en"
    assert from_accept_language(None) == "en"


def test_every_tactic_has_a_chinese_explanation_and_a_missing_string_falls_back_to_english():
    for tid in TACTICS:
        for field in ("label", "blurb", "tell", "action"):
            assert i18n.tactic_text(tid, field, "zh", TACTICS) != TACTICS[tid][field]
    assert tr("a sentence nobody translated", "zh") == "a sentence nobody translated"
    assert tr("{n} separate red flags", "zh", n=3) == "3 个不同的红旗"
    assert tr("{n} separate red flags", "en", n=3) == "{n} separate red flags".format(n=3)


def test_traditional_is_derived_from_simplified_with_the_right_characters():
    assert to_traditional("这是骗局。符合骗局套路，不同的红旗，请回复") == "這是騙局。符合騙局套路，不同的紅旗，請回覆"
    assert to_traditional("账户已被冻结") == "帳戶已被凍結"


def test_reply_language_follows_the_user_then_the_message():
    assert reply_language(PARCEL, None) == "zh"
    assert reply_language("請點擊連結驗證您的帳戶", None) == "zh-Hant"
    assert reply_language(PARCEL, "en") == "en"                         # an English reader checking a Chinese message
    assert reply_language("Your parcel is on hold", "zh") == "zh"       # a Chinese reader checking an English message
    assert reply_language("Tahniah anda menang hadiah", None) == "en"   # languages we have no wording for answer in English


def test_a_chinese_message_gets_a_chinese_answer_and_an_english_one_when_asked():
    zh = check_message(PARCEL, store=False, log=False)
    assert zh.lang == "zh" and zh.message_lang == "zh" and zh.headline.startswith("🚨") and "骗局" in zh.headline
    assert any("链接" in e.claim or "骗局" in e.claim for e in zh.evidence)
    en = check_message(PARCEL, store=False, log=False, lang="en")
    assert en.lang == "en" and en.message_lang == "zh" and "SCAM" in en.headline
    assert any("is a known scam phrase" in e.claim for e in en.evidence) and not any("骗局用语" in e.claim for e in en.evidence)  # quotes stay Chinese, the wording is English


def test_a_traditional_message_gets_a_traditional_answer():
    r = check_message("【中華郵政】您的包裹因地址不全無法投遞，請點擊 http://post-tw-redelivery.top 補填資料，否則將退回。", store=False, log=False)
    assert r.lang == "zh-Hant" and "騙局" in r.headline and "骗" not in r.headline + r.tell + r.action


def test_english_answers_are_unchanged():
    r = check_message("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz/track", store=False, log=False)
    assert r.lang == "en" and r.verdict in (V.SCAM, V.LIKELY_SCAM) and "SCAM" in r.headline.upper()
    assert any(e.claim.startswith("The link ") for e in r.evidence)


def test_victim_support_and_the_cautious_fallback_are_translated():
    r = check_message("我被骗了，刚才把验证码告诉了对方", store=False, log=False)
    assert r.verdict is V.VICTIM and r.lang == "zh" and "不是你的错" in r.headline
