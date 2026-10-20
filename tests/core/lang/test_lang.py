"""Language detection, script-agnostic Chinese patterns, and link detection inside Chinese text."""
import pytest

from core.domain.lang import Dual, Z, canon, detect, to_simplified
from core.pipelines.check.ingest import ingest


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
