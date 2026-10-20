"""The Chinese seed bank, the language-aware game pool, and clause-level spot-the-tell."""
import pytest

from core.domain.lang import detect
from core.domain.schemas import Verdict as V
from core.domain.tactics import valid
from core.game import pool as gp
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
    assert not [e["id"] for e, v in verdicts if not e["is_scam"] and v in (V.SCAM, V.LIKELY_SCAM)]
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
