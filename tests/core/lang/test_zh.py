"""The Chinese seed bank, the language-aware game pool, and clause-level spot-the-tell. Chinese rules (no model): scams are caught, genuine messages are not flagged, nothing is called safe that shouldn't be.
Sets are authored (tests/data/zh/dev.py, holdout.py); see their docstrings."""
import pytest

from core.domain.schemas import Verdict as V
from core.domain.tactics import valid
from core.game import pool as gp
from core.lang.text import detect
from core.pipelines.check import check_message
from core.storage import library
from tests.data.zh import dev as zh_set, holdout as zh_holdout


def test_chinese_seed_bank_is_well_formed():
    seeds = library.seed_examples("zh")
    assert len(seeds) >= 40 and len({e["id"] for e in seeds}) == len(seeds)
    assert sum(e["is_scam"] for e in seeds) >= 28 and sum(not e["is_scam"] for e in seeds) >= 12
    for e in seeds:
        assert detect(e["text"]) == "zh"
        if e["is_scam"]:
            assert e["tactics"] and all(valid(t) for t in e["tactics"]) and e["tell_phrase"] in e["text"] and e["tell"] and e["action"], e["id"]
        else:
            assert not e["tactics"] and not e["tell_phrase"]


def test_the_chinese_seed_bank_does_not_leak_into_the_evaluation_sets():
    texts = {e["text"] for e in library.seed_examples("zh")}
    assert not texts & {t for _, t in zh_holdout.SCAMS + zh_holdout.LEGIT + zh_set.SCAMS + zh_set.LEGIT}


def test_traditional_bank_keeps_every_phrase_findable():
    for e in library.seed_examples("zh-Hant"):
        assert detect(e["text"]) == "zh-Hant" and (not e["tell_phrase"] or e["tell_phrase"] in e["text"]) and "骗" not in e["text"] + e["tell"]
    assert sum(bool(e["tell_phrase"]) for e in library.seed_examples("zh-Hant") if e["is_scam"]) >= 28


def test_english_seed_bank_is_unchanged_by_default():
    assert len(library.seed_examples()) == 42 and all("一" > c or c > "鿿" for e in library.seed_examples() for c in e["text"])


def test_rules_alone_never_call_a_chinese_seed_scam_safe_and_flag_no_genuine_seed():
    seeds = library.seed_examples("zh")
    verdicts = [(e, check_message(e["text"], store=False, log=False).verdict) for e in seeds]
    assert not [e["id"] for e, v in verdicts if e["is_scam"] and v is V.SAFE]
    assert not [e["id"] for e, v in verdicts if not e["is_scam"] and v in (V.SCAM, V.LIKELY_SCAM)]  # includes the "check first" ones: not flagged, only not cleared
    caught = sum(v in (V.SCAM, V.LIKELY_SCAM) for e, v in verdicts if e["is_scam"])
    assert caught / sum(e["is_scam"] for e in seeds) >= 0.85, caught


def test_pool_is_language_specific_and_english_is_unchanged():
    zh = gp.build_pool("zh")
    assert zh and all(i.source in ("seed", "yours") for i in zh) and all(detect(i.text) == "zh" for i in zh if i.source == "seed")
    en = gp.build_pool()
    assert {i.source for i in en} >= {"seed", "bank"} and not any(detect(i.text) == "zh" for i in en)
    assert [i.truth for i in zh if "【中国工商银行】" in i.text] == ["safe"]


def test_chinese_messages_split_into_clauses_for_spot_the_tell():
    assert gp.words("【顺丰】请于24小时内点击链接，逾期将退回。") == ["【顺丰】请于24小时内点击链接，", "逾期将退回。"]
    assert gp.words("Pay within 24 hours now") == ["Pay", "within", "24", "hours", "now"]


@pytest.mark.parametrize("picked,expect", [([2], "correct"), ([2, 3], "correct"), ([0], "wrong"), ([0, 1, 2, 3], "partial"), ([], "wrong")])
def test_clause_level_tell_scoring(picked, expect):
    it = gp.Item("x", "您好，您的账户异常，请点击 http://a.top 验证，否则冻结。", "scam", ["lookalike-link"], tell_phrase="http://a.top")
    assert gp.words(it.text)[2].startswith("请点击") and gp.tell_score_clauses(it, picked) == expect


def test_the_chinese_bank_has_check_first_messages_so_a_chinese_round_can_use_all_three_answers():
    unsure = [e for e in library.seed_examples("zh") if e.get("truth") == "unsure"]
    assert len(unsure) >= 5 and all(not e["is_scam"] and not e["tactics"] and e["tell"] and e["action"] for e in unsure)
    pool = gp.build_pool("zh")
    assert sum(i.truth == "unsure" for i in pool if i.source == "seed") == len(unsure)
    assert not any(i.truth == "unsure" for i in gp.build_pool("en") if detect(i.text) == "zh")
    assert all(e.get("truth") != "unsure" for e in library.seed_examples())  # the English bank keeps its own "unsure" items in the authored bank


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


def test_chinese_personal_numbers_are_redacted_before_anything_is_stored_or_sent():
    from core.domain.privacy import redact, scrub_outgoing

    text = "我是王芳，手机13812345678，身份证11010519491231002X，银行卡6217000012345678901，邮箱wang@example.com，微信转账。"
    out = redact(text)
    assert "13812345678" not in out and "11010519491231002X" not in out and "6217000012345678901" not in out and "wang@example.com" not in out
    clean, n = scrub_outgoing(text)
    assert n >= 3 and "13812345678" not in clean and "11010519491231002X" not in clean
