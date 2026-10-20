"""Chinese rules (no model): scams are caught, genuine messages are not flagged, nothing is called safe that shouldn't be.
Sets are authored (tests/data/zh_set.py, zh_holdout.py); see their docstrings."""
import pytest

from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message
from tests.data import zh_holdout, zh_set

FLAGGED = (V.SCAM, V.LIKELY_SCAM)


def verdict(text):
    return check_message(text, store=False, log=False).verdict


@pytest.mark.parametrize("ds", [zh_set, zh_holdout], ids=["dev", "holdout"])
def test_rules_never_call_a_chinese_scam_safe_and_never_flag_genuine_messages(ds):
    safe = [i for i, t in ds.SCAMS if verdict(t) is V.SAFE]
    alarms = [i for i, t in ds.LEGIT if verdict(t) in FLAGGED]
    assert not safe, f"scams called safe: {safe}"
    assert not alarms, f"genuine messages flagged: {alarms}"


@pytest.mark.parametrize("ds,minimum", [(zh_set, 0.95), (zh_holdout, 0.85)], ids=["dev", "holdout"])
def test_rules_alone_catch_most_chinese_scams(ds, minimum):
    caught = sum(verdict(t) in FLAGGED for _, t in ds.SCAMS)
    assert caught / len(ds.SCAMS) >= minimum, f"{caught}/{len(ds.SCAMS)}"


@pytest.mark.parametrize("text", [
    "您的验证码为 639201，用于登录淘宝账号，10分钟内有效，请勿将验证码告知他人。",        # a warning not to share is not a request to share
    "国家反诈中心提醒：近期有不法分子冒充公检法人员实施诈骗，请勿向陌生人转账，切勿透露验证码。",  # quoting the police is not claiming to be them
    "【丰巢】您的快递已放入3号柜，取件码 872564，请于24小时内取走，超时将收取保管费。",       # a pickup window is not a scam deadline
    "【支付宝】你已成功向李华转账200.00元，如非本人操作，请立即联系支付宝客服95188。",         # Alipay is not the verb "to pay"; "已" marks it as done
    "【国家税务总局】个人所得税年度汇算已开始，请通过个人所得税APP办理，官方渠道不会通过短信链接要求您提供银行卡信息。",  # 汇算 is not 汇款
])
def test_real_looking_notices_that_share_words_with_scams_are_not_flagged(text):
    assert verdict(text) not in FLAGGED


@pytest.mark.parametrize("text", [
    "您好，我是XX市公安局民警，您涉嫌一起洗钱案件，请立即配合调查，将资金转入安全账户核查，不得告知任何人。",
    "【中華郵政】您的包裹因地址不全無法投遞，請點擊 http://post-tw-redelivery.top 補填資料，否則將退回。",   # Traditional script
    "【DBS】Your account is locked. 请点击 dbs-sg-verify.com 验证身份，24小时内未处理将永久冻结。",         # code-mixed
])
def test_typical_chinese_scams_are_flagged_in_both_scripts_and_mixed_text(text):
    assert verdict(text) in FLAGGED


def test_a_lookalike_chinese_bank_link_is_hard_evidence():
    r = check_message("【中国银行】您的账户异常，请登录 http://boc-secure-verify.com 验证", store=False, log=False)
    assert r.verdict is V.SCAM and any(e.source == "domain_check" for e in r.evidence)


def test_the_real_bank_link_is_not_called_a_lookalike():
    r = check_message("【工商银行】您的账单已出，详情见 https://www.icbc.com.cn", store=False, log=False)
    assert not any(e.source == "domain_check" and e.supports == "scam" for e in r.evidence)


def test_singapore_and_malaysia_banks_with_other_official_domains_are_recognised():
    r = check_message("DBS: your statement is ready at https://www.dbs.com.sg/personal", store=False, log=False)
    assert not any(e.source == "domain_check" and e.supports == "scam" and e.strength == "strong" for e in r.evidence)
