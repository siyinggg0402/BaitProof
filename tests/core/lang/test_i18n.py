"""Answers in the user's language: reply language selection, fallbacks, Simplified/Traditional output, and that English is untouched. Language detection, script-agnostic Chinese patterns, and link detection inside Chinese text."""
import pytest

from core.domain.schemas import Verdict as V
from core.domain.tactics import TACTICS
from core.lang import i18n
from core.lang.i18n import from_accept_language, norm, to_traditional, tr
from core.lang.text import Dual, Z, canon, detect, to_simplified
from core.pipelines.check import check_message
from core.pipelines.check.ingest import ingest
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
    assert reply_language("Tahniah anda menang hadiah", None) == "ms"   # a Malay message, no language chosen: answered in Malay
    assert reply_language("Bonjour, votre colis est en attente", None) == "en"  # languages we have no wording for answer in English


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


def test_traditional_wording_for_common_ui_words():
    assert to_traditional("5分钟内，请复制消息") == "5分鐘內，請複製訊息"


def test_chinese_tells_use_a_full_width_colon_before_the_fallback_explanation():
    r = check_message("请把验证码发给我，我帮你领取优惠券。", store=False, log=False)  # offline: the tell is built from the quote and the tactic's explanation
    assert "”：" in r.tell and ": " not in r.tell


@pytest.mark.parametrize("text,lang", [
    ("【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf.top 补全信息", "zh"),
    ("【中華郵政】您的包裹因地址不全無法投遞，請點擊 http://post-tw.top 補填資料", "zh-Hant"),
    ("Your parcel is on hold. Pay the $1.99 fee at dhl-fee.xyz", "en"),
    ("Tahniah! Anda telah memenangi hadiah RM50,000. Sila klik pautan ini untuk menuntut.", "ms"),
    ("Hi, is this Amy?", "en"),
    ("Visit www.example.com/a?b=1 now.", "en"),
    ("お客様の荷物は配達できません。こちらをクリック", "ja"),
    ("안녕하세요 계좌가 정지되었습니다", "ko"),
    ("Su cuenta ha sido bloqueada. Haga clic aquí para verificar su identidad con el banco", "other"),
    ("您的账户存在风险，请登录 www.boc-secure.com 验证 your account now", "zh"),
    ("Your OTP is 481920. 请勿泄露给他人。", "zh"),  # code-mixed: the Chinese rules run as well as the English ones
])
def test_language_detection(text, lang):
    assert detect(text) == lang


def test_one_simplified_pattern_matches_both_scripts():
    assert Z("验证码").search("请提供驗證碼")
    assert Z("[转汇]账").search("匯帳") and Z("账户").search("帳戶") and Z("账户").search("賬戶")
    assert canon("請點擊 驗證碼") == canon("请点击验证码")
    assert to_simplified("銀行") == "银行"


def test_the_chinese_twin_never_runs_on_english_text():
    d = Dual(r"\bapp\b", r"下载|app|vip")
    assert d.search("download our app") and not d.search("Use the vip lounge") and d.search("请下载")


@pytest.mark.parametrize("text,host", [
    ("请点击http://boc-secure-verify.com验证身份，否则冻结", "boc-secure-verify.com"),   # no spaces: the link must stop at the next Chinese character
    ("登录boc-secure.com验证", "boc-secure.com"),                                       # and a link may start right after one
    ("【顺丰】请点击 http://sf-express-cn.top/addr 补全，谢谢", "sf-express-cn.top"),
    ("点击：https://95598-pay.top。", "95598-pay.top"),
])
def test_links_are_found_inside_chinese_text(text, host):
    assert ingest(text).entities.hosts == [host]


def test_ordinary_words_with_a_dot_are_not_links():
    assert ingest("Mr.Myers said hi, see foo.company soon").entities.hosts == []
